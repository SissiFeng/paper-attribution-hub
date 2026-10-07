from __future__ import annotations

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import HumanReview, Paper


STAGE1_NOT_READY_DETAIL = (
    "Tier 1 full-text acquisition and model validation are still in progress. "
    "Derived review and analytics views have not been promoted."
)


def derived_views_available(session: Session) -> bool:
    """Return whether review/classification-derived views may be exposed."""
    if not settings.sdl_stage1_only:
        return True
    if not settings.sdl_stage1_derived_views_enabled:
        return False
    metadata_papers, fulltexts_imported = _corpus_counts(session)
    return (
        metadata_papers > 0
        and fulltexts_imported == metadata_papers
    )


def descriptive_analytics_available(session: Session) -> bool:
    """Return whether full-text-backed descriptive views may be exposed."""
    if not settings.sdl_stage1_only:
        return True
    if not settings.sdl_stage1_descriptive_analytics_enabled:
        return False
    metadata_papers, fulltexts_imported = _corpus_counts(session)
    return metadata_papers > 0 and fulltexts_imported == metadata_papers


def build_stage1_readiness(session: Session) -> dict:
    metadata_papers, fulltexts_imported = _corpus_counts(session)
    split_summary = _split_summary(session)
    ready = derived_views_available(session)
    descriptive_ready = descriptive_analytics_available(session)
    if ready:
        phase = "classification_pilot"
        reason = (
            "The complete Tier 1 pilot corpus has rule-based classifications "
            "and derived analysis enabled. Human labels, supervised training, "
            "and frozen-test validation are still pending."
        )
    elif fulltexts_imported < metadata_papers:
        phase = "acquiring_fulltexts"
        reason = STAGE1_NOT_READY_DETAIL
    elif descriptive_ready:
        phase = "analysis_preview"
        reason = (
            "Verified Tier 1 full texts are available for descriptive analysis. "
            "Classifier-derived review and attribution views remain quarantined."
        )
    else:
        phase = "awaiting_promotion"
        reason = (
            "The Tier 1 full-text corpus is complete, but derived review and "
            "analytics views have not been explicitly promoted."
        )
    return {
        "stage1_only": settings.sdl_stage1_only,
        "phase": phase,
        "derived_views_enabled": ready,
        "descriptive_analytics_enabled": descriptive_ready,
        "metadata_papers": metadata_papers,
        "fulltexts_imported": fulltexts_imported,
        **split_summary,
        "reason": reason,
    }


def _corpus_counts(session: Session) -> tuple[int, int]:
    metadata_papers = session.scalar(select(func.count(Paper.id))) or 0
    fulltexts_imported = (
        session.scalar(
            select(func.count(Paper.id)).where(
                Paper.full_text_available.is_(True)
            )
        )
        or 0
    )
    return metadata_papers, fulltexts_imported


def _split_summary(session: Session) -> dict:
    if not settings.sdl_stage1_only:
        return {
            "split_manifest_id": None,
            "split_role_counts": {},
            "train_round_counts": {},
            "completed_label_counts": {},
        }

    from app.services.sdl_stage1_service import stage1_assignment

    assignments: dict[str, dict] = {}
    manifest_ids: set[str] = set()
    role_counts: Counter[str] = Counter()
    train_round_counts: Counter[str] = Counter()
    for paper in session.scalars(select(Paper)):
        assignment = stage1_assignment(paper)
        if not assignment:
            continue
        assignments[paper.id] = assignment
        if assignment.get("manifest_id"):
            manifest_ids.add(str(assignment["manifest_id"]))
        role = str(assignment.get("role") or "")
        if role:
            role_counts[role] += 1
        if role == "train" and assignment.get("round") is not None:
            train_round_counts[str(int(assignment["round"]))] += 1

    completed: Counter[str] = Counter()
    for review in session.scalars(select(HumanReview)):
        assignment = assignments.get(review.paper_id)
        if (
            not assignment
            or review.review_status != "COMPLETED"
            or review.judgement_basis != "STRICT_SDL"
            or review.ac_relevance_judgement is not None
            or review.human_label is not None
        ):
            continue
        role = str(assignment.get("role") or "")
        if role:
            completed[role] += 1
        if role == "train" and assignment.get("round") is not None:
            completed[f"train_round_{int(assignment['round'])}"] += 1

    return {
        "split_manifest_id": (
            next(iter(manifest_ids)) if len(manifest_ids) == 1 else None
        ),
        "split_role_counts": dict(sorted(role_counts.items())),
        "train_round_counts": dict(
            sorted(train_round_counts.items(), key=lambda item: int(item[0]))
        ),
        "completed_label_counts": dict(sorted(completed.items())),
    }
