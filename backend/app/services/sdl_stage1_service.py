"""Frozen, AC-independent sampling and labels for the SDL Stage 1 pilot."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classification_labels import LABEL_ADJACENT, LABEL_EXCLUDE, LABEL_SDL_FIELD
from app.models import HumanReview, Paper
from app.services.zotero_ingestion_service import validate_stage1_corpus

DEFAULT_VALIDATION_COUNT = 60
DEFAULT_FROZEN_TEST_COUNT = 80
DEFAULT_TRAIN_ROUND_COUNTS = (60, 60, 60)
DEFAULT_SPLIT_SEED = "sdl-stage1-v1"

Stage1Role = Literal["train", "validation", "frozen_test", "pool"]

_SDL_JUDGEMENT_TO_LABEL = {
    "CONFIRMED_SDL": LABEL_SDL_FIELD,
    "PROBABLE_SDL": LABEL_SDL_FIELD,
    "SDL_ADJACENT": LABEL_ADJACENT,
    "NOT_SDL": LABEL_EXCLUDE,
}


def prepare_stage1_batches(
    session: Session,
    *,
    validation_count: int = DEFAULT_VALIDATION_COUNT,
    frozen_test_count: int = DEFAULT_FROZEN_TEST_COUNT,
    train_round_counts: tuple[int, ...] = DEFAULT_TRAIN_ROUND_COUNTS,
    seed: str = DEFAULT_SPLIT_SEED,
    expected_total: int | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Freeze deterministic, disjoint review batches over the Tier 1 corpus.

    The hash ordering is reproducible but does not use authors, institutions,
    AC membership, classifier scores, or human labels. The frozen-test IDs are
    selected at the same time as the training IDs so later rounds cannot move
    papers between roles.
    """
    validate_stage1_corpus(session)
    _validate_counts(validation_count, frozen_test_count, train_round_counts)
    papers = list(session.execute(select(Paper).order_by(Paper.id)).scalars())
    if expected_total is not None and len(papers) != expected_total:
        raise ValueError(
            f"SDL Stage 1 expected {expected_total} unique Tier 1 papers, "
            f"found {len(papers)}"
        )
    selected_count = (
        validation_count + frozen_test_count + sum(train_round_counts)
    )
    if len(papers) < selected_count:
        raise ValueError(
            f"SDL Stage 1 needs at least {selected_count} papers for the "
            f"configured batches, found {len(papers)}"
        )

    corpus_sha256 = _corpus_hash(papers)
    manifest_id = _manifest_id(
        corpus_sha256=corpus_sha256,
        seed=seed,
        validation_count=validation_count,
        frozen_test_count=frozen_test_count,
        train_round_counts=train_round_counts,
    )
    ordered = sorted(
        papers,
        key=lambda paper: (
            hashlib.sha256(f"{seed}:{paper.id}".encode()).hexdigest(),
            paper.id,
        ),
    )

    assignments: list[dict[str, Any]] = []
    cursor = 0

    def assign(role: Stage1Role, count: int, *, round_number: int | None) -> None:
        nonlocal cursor
        for ordinal, paper in enumerate(ordered[cursor : cursor + count], start=1):
            assignments.append(
                _assignment_record(
                    paper,
                    role=role,
                    round_number=round_number,
                    ordinal=ordinal,
                )
            )
        cursor += count

    assign("validation", validation_count, round_number=None)
    assign("frozen_test", frozen_test_count, round_number=None)
    for round_number, count in enumerate(train_round_counts, start=1):
        assign("train", count, round_number=round_number)
    assign("pool", len(ordered) - cursor, round_number=None)

    if persist:
        by_paper_id = {row["paper_id"]: row for row in assignments}
        for paper in papers:
            assignment = by_paper_id[paper.id]
            raw = dict(paper.raw_metadata or {})
            raw["sdl_stage1_split"] = {
                "manifest_id": manifest_id,
                "corpus_sha256": corpus_sha256,
                "seed": seed,
                "role": assignment["role"],
                "round": assignment["round"],
                "ordinal": assignment["ordinal"],
            }
            paper.raw_metadata = raw
        session.flush()

    role_counts = {
        role: sum(1 for row in assignments if row["role"] == role)
        for role in ("train", "validation", "frozen_test", "pool")
    }
    round_counts = {
        str(round_number): sum(
            1
            for row in assignments
            if row["role"] == "train" and row["round"] == round_number
        )
        for round_number in range(1, len(train_round_counts) + 1)
    }
    return {
        "schema_version": 1,
        "kind": "sdl_stage1_split_manifest",
        "manifest_id": manifest_id,
        "created_at": datetime.now(UTC).isoformat(),
        "corpus_policy": {
            "source": "zotero",
            "retrieval_tier": "tier1",
            "corpus_source": "STRICT_SDL_KEYWORD",
            "ac_signals_allowed": False,
        },
        "corpus_sha256": corpus_sha256,
        "unique_papers": len(papers),
        "seed": seed,
        "role_counts": role_counts,
        "train_round_counts": round_counts,
        "frozen_test_policy": "release_once_after_model_selection",
        "assignments": assignments,
    }


def stage1_assignment(paper: Paper) -> dict[str, Any] | None:
    value = dict((paper.raw_metadata or {}).get("sdl_stage1_split") or {})
    return value or None


def stage1_assignment_ids(
    session: Session,
    *,
    roles: set[Stage1Role],
) -> set[str]:
    validate_stage1_corpus(session)
    ids: set[str] = set()
    for paper in session.execute(select(Paper)).scalars():
        assignment = stage1_assignment(paper)
        if assignment and assignment.get("role") in roles:
            ids.add(paper.id)
    return ids


def stage1_label_map(
    session: Session,
    *,
    role: Literal["train", "validation", "frozen_test"],
    through_round: int | None = None,
) -> dict[str, str]:
    """Return only completed strict-SDL labels for one frozen split role."""
    validate_stage1_corpus(session)
    labels: dict[str, str] = {}
    papers = {
        paper.id: paper for paper in session.execute(select(Paper)).scalars()
    }
    for review in session.execute(select(HumanReview)).scalars():
        paper = papers.get(review.paper_id)
        if paper is None:
            continue
        assignment = stage1_assignment(paper)
        if not assignment or assignment.get("role") != role:
            continue
        if (
            role == "train"
            and through_round is not None
            and int(assignment.get("round") or 0) > through_round
        ):
            continue
        if (
            review.review_status != "COMPLETED"
            or review.judgement_basis != "STRICT_SDL"
            or review.ac_relevance_judgement is not None
            or review.human_label is not None
        ):
            continue
        label = _SDL_JUDGEMENT_TO_LABEL.get(review.sdl_judgement or "")
        if label is not None:
            labels[paper.id] = label
    return labels


def stage1_label_rows(
    session: Session,
    *,
    role: Literal["train", "validation", "frozen_test"],
    through_round: int | None = None,
) -> list[dict[str, str]]:
    """Build auditable label rows without exposing any other split's labels."""
    labels = stage1_label_map(
        session,
        role=role,
        through_round=through_round,
    )
    rows: list[dict[str, str]] = []
    for paper_id in sorted(labels):
        paper = session.get(Paper, paper_id)
        review = paper.review if paper else None
        assignment = stage1_assignment(paper) if paper else None
        rows.append(
            {
                "paper_id": paper_id,
                "gold_label": labels[paper_id],
                "gold_topics": "",
                "notes": review.rationale or review.notes or "" if review else "",
                "label_scope": "STRICT_SDL",
                "annotation_source": "human_strict_sdl",
                "evidence_level": review.evidence_level or "UNKNOWN" if review else "UNKNOWN",
                "split_role": role,
                "train_round": (
                    str(assignment.get("round"))
                    if assignment and assignment.get("round") is not None
                    else ""
                ),
                "manifest_id": str((assignment or {}).get("manifest_id") or ""),
            }
        )
    return rows


def _validate_counts(
    validation_count: int,
    frozen_test_count: int,
    train_round_counts: tuple[int, ...],
) -> None:
    if validation_count <= 0 or frozen_test_count <= 0:
        raise ValueError("validation and frozen-test counts must be positive")
    if not train_round_counts or any(count <= 0 for count in train_round_counts):
        raise ValueError("at least one positive training-round count is required")


def _corpus_hash(papers: list[Paper]) -> str:
    rows: list[dict[str, Any]] = []
    for paper in papers:
        zotero = dict((paper.raw_metadata or {}).get("zotero") or {})
        rows.append(
            {
                "paper_id": paper.id,
                "doi": paper.doi,
                "item_key": zotero.get("primary_item_key"),
                "item_version": zotero.get("primary_item_version"),
                "collection_keys": zotero.get("collection_keys"),
            }
        )
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _manifest_id(
    *,
    corpus_sha256: str,
    seed: str,
    validation_count: int,
    frozen_test_count: int,
    train_round_counts: tuple[int, ...],
) -> str:
    payload = json.dumps(
        {
            "corpus_sha256": corpus_sha256,
            "seed": seed,
            "validation_count": validation_count,
            "frozen_test_count": frozen_test_count,
            "train_round_counts": train_round_counts,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sdl_stage1_" + hashlib.sha256(payload.encode()).hexdigest()[:16]


def _assignment_record(
    paper: Paper,
    *,
    role: Stage1Role,
    round_number: int | None,
    ordinal: int,
) -> dict[str, Any]:
    zotero = dict((paper.raw_metadata or {}).get("zotero") or {})
    return {
        "paper_id": paper.id,
        "zotero_item_key": zotero.get("primary_item_key"),
        "year": paper.year,
        "role": role,
        "round": round_number,
        "ordinal": ordinal,
    }
