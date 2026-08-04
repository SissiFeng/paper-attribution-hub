"""Review queue (v0.7 review loop).

The daily pipeline classifies papers automatically, but every paper that
sits in a borderline confidence band, was flipped by the learned model
relative to the rules, or has contradictory evidence is flagged for human
review. The queue surfaces those papers in priority order so reviewers
work the highest-value cases first.

Priority is computed as a weighted sum of small signals so it's
explainable in the UI. We deliberately avoid an ML ranker here — the
input set is small and reviewers want to see *why* a paper bubbled up.

Once a paper's classification is human_confirmed (either via /confirm or
/reviews/{id}), `needs_review` drops to False and it leaves the queue.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Author,
    HumanReview,
    Paper,
    PaperAuthor,
    PaperClassification,
    PaperEvidence,
)
from app.review_contract import infer_corpus_sources, normalize_corpus_sources
from app.services.staged_screening import (
    REVIEW_ROUTES,
    ROUTE_PRIORITY_FLOORS,
    apply_paper_screening,
    apply_staged_screening,
)

# Tunables — keep them small + interpretable.
_W_UNCERTAIN = 0.45
_W_LOW_CONF_AUTO = 0.30
_W_DISCOVERED_AUTO = 0.25
_W_DISQUALIFYING_BUT_HIGH = 0.40
_W_LEARNED_DISAGREES = 0.20
_W_NO_REVIEW_YET = 0.05
_W_NEEDS_FULLTEXT = 0.45
_W_AGE_DAYS = 0.01  # +0.01 per day since classification, capped at 0.10


@dataclass
class QueueItem:
    paper_id: str
    title: str
    abstract: str | None
    year: int | None
    venue: str | None
    doi: str | None
    authors: list[str]
    institutions: list[str]
    label: str
    confidence: float
    priority: float
    reasons: list[str]
    last_classified_at: datetime | None
    source: str | None
    provenance: str | None
    corpus_sources: list[str]
    full_text_url: str | None
    has_human_review: bool
    sdl_judgement: str | None
    ac_relevance_judgement: str | None
    ai_for_science_judgement: str | None
    review_status: str | None
    evidence_level: str | None
    judgement_basis: str | None
    screening_stage: str | None
    screening_route: str | None
    screening_reason: str | None
    review_assignee: str | None
    review_assigned_at: datetime | None
    review_assigned_by: str | None


# ---------------------------------------------------------------------------
# Priority scoring
# ---------------------------------------------------------------------------


def compute_priority(
    paper: Paper,
    cls: PaperClassification,
    *,
    has_review: bool,
    disqualifying_count: int,
    now: datetime | None = None,
) -> tuple[float, list[str]]:
    """Return (priority_in_0_1, reasons[]). Higher = surface sooner."""
    if cls is None:
        return 0.0, ["No classification yet — paper not processed."]
    if cls.human_confirmed:
        return 0.0, ["Already human-confirmed."]

    now = now or datetime.now(UTC)
    reasons: list[str] = []
    score = 0.0

    if paper.review and paper.review.review_status == "NEEDS_FULLTEXT":
        score += _W_NEEDS_FULLTEXT
        reasons.append(
            "The first-pass review found insufficient evidence; inspect the "
            "full text or supporting information."
        )

    if cls.label == "UNCERTAIN":
        score += _W_UNCERTAIN
        reasons.append("Label is UNCERTAIN — classifier could not decide; human adjudication required.")

    if (
        (paper.provenance or "").startswith("discovered_auto")
        and cls.label in {"CORE_RELEVANT", "RELATED_RELEVANT"}
        and cls.confidence < 0.75
    ):
        score += _W_LOW_CONF_AUTO
        reasons.append(
            f"Auto-discovered paper with low confidence ({cls.confidence:.0%}) — verify this isn't a false positive."
        )

    if (paper.provenance or "").startswith("discovered_auto") and not has_review:
        score += _W_DISCOVERED_AUTO
        reasons.append("Paper was ingested automatically by the discovery pipeline; first human review needed.")

    if disqualifying_count > 0 and cls.label in {
        "CORE_RELEVANT",
        "RELATED_RELEVANT",
    }:
        score += _W_DISQUALIFYING_BUT_HIGH
        reasons.append(
            f"{disqualifying_count} disqualifying evidence signal(s) recorded despite label '{cls.label}' "
            f"— evidence conflicts with the positive label; sanity check required."
        )

    if "learned-" in (cls.model_version or "") and "+judge" not in (
        cls.model_version or ""
    ):
        score += _W_LEARNED_DISAGREES
        reasons.append(
            f"Learned classifier (v: {cls.model_version}) overrode the rule-based score — verify the override is correct."
        )

    if not has_review:
        score += _W_NO_REVIEW_YET
        reasons.append(
            f"No human review recorded yet for this paper (label: {cls.label}, "
            f"confidence: {cls.confidence:.0%})."
        )

    if cls.last_classified_at:
        last = cls.last_classified_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        age = (now - last).days
        if age > 0:
            bump = min(_W_AGE_DAYS * age, 0.10)
            score += bump
            if bump >= 0.05:
                reasons.append(f"Classification is {age} days old — worth a fresh look.")

    # Always append the classifier's own reasons so reviewers see the evidence
    # that drove the label, even when no queue-specific trigger fired.
    classifier_reasons = [r for r in (cls.reasons or []) if r]
    if classifier_reasons:
        reasons.append("— Classification evidence —")
        reasons.extend(classifier_reasons[:6])

    return min(round(score, 3), 1.0), reasons


# ---------------------------------------------------------------------------
# Enqueue
# ---------------------------------------------------------------------------


_FLAG_THRESHOLD = 0.20


def refresh_queue(session: Session, *, threshold: float = _FLAG_THRESHOLD) -> int:
    """Walk all papers, compute priorities, persist `needs_review` flags.

    Returns the number of papers flagged."""
    now = datetime.now(UTC)
    apply_staged_screening(session, commit=False)
    disqualifying_counts = _disqualifying_counts(session)
    review_paper_ids = {
        pid for (pid,) in session.execute(select(HumanReview.paper_id)).all()
    }
    flagged = 0
    for paper in session.execute(select(Paper)).scalars():
        cls = paper.classification
        if cls is None:
            continue
        if cls.screening_route not in REVIEW_ROUTES:
            cls.needs_review = False
            cls.review_priority = 0.0
            continue
        last_classified_at = cls.last_classified_at
        if last_classified_at is not None:
            if last_classified_at.tzinfo is None:
                last_classified_at = last_classified_at.replace(tzinfo=UTC)
            if last_classified_at > now:
                cls.needs_review = False
                cls.review_priority = 0.0
                continue
        priority, _reasons = compute_priority(
            paper,
            cls,
            has_review=paper.id in review_paper_ids,
            disqualifying_count=disqualifying_counts.get(paper.id, 0),
            now=now,
        )
        priority = max(
            priority,
            ROUTE_PRIORITY_FLOORS[cls.screening_route],
        )
        cls.review_priority = priority
        cls.needs_review = priority >= threshold
        if cls.needs_review:
            flagged += 1
    session.commit()
    return flagged


def _disqualifying_counts(session: Session) -> dict[str, int]:
    out: dict[str, int] = {}
    rows = session.execute(
        select(PaperEvidence.paper_id, PaperEvidence.evidence_type)
    ).all()
    for paper_id, evidence_type in rows:
        if evidence_type == "disqualifying":
            out[paper_id] = out.get(paper_id, 0) + 1
    return out


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def list_queue(
    session: Session,
    *,
    limit: int = 50,
    offset: int = 0,
    include_confirmed: bool = False,
    assignee: str | None = None,
    unassigned_only: bool = False,
    paper_id: str | None = None,
) -> list[QueueItem]:
    stmt = (
        select(Paper, PaperClassification)
        .join(PaperClassification, PaperClassification.paper_id == Paper.id)
        .options(
            selectinload(Paper.authors)
            .selectinload(PaperAuthor.author)
            .selectinload(Author.institution),
            selectinload(Paper.review),
        )
    )
    if not include_confirmed:
        stmt = stmt.where(PaperClassification.human_confirmed.is_(False))
        stmt = stmt.where(PaperClassification.needs_review.is_(True))
        stmt = stmt.where(
            PaperClassification.screening_route.in_(REVIEW_ROUTES)
        )
    if paper_id:
        stmt = stmt.where(Paper.id == paper_id)
    normalized_assignee = (assignee or "").strip()
    if unassigned_only:
        stmt = stmt.where(PaperClassification.review_assignee.is_(None))
    elif normalized_assignee:
        stmt = stmt.where(
            PaperClassification.review_assignee == normalized_assignee
        )
    stmt = stmt.order_by(desc(PaperClassification.review_priority))
    stmt = stmt.offset(offset).limit(limit)

    review_paper_ids = {
        pid for (pid,) in session.execute(select(HumanReview.paper_id)).all()
    }
    disq = _disqualifying_counts(session)

    out: list[QueueItem] = []
    now = datetime.now(UTC)
    for paper, cls in session.execute(stmt).all():
        _, reasons = compute_priority(
            paper,
            cls,
            has_review=paper.id in review_paper_ids,
            disqualifying_count=disq.get(paper.id, 0),
            now=now,
        )
        author_names = [
            link.author.canonical_name
            for link in paper.authors
            if link.author is not None
        ]
        institutions: list[str] = []
        for link in paper.authors:
            institution = (
                link.affiliation_text
                or (
                    link.author.institution.canonical_name
                    if link.author is not None and link.author.institution is not None
                    else None
                )
            )
            if institution and institution not in institutions:
                institutions.append(institution)
        review = paper.review
        out.append(
            QueueItem(
                paper_id=paper.id,
                title=paper.title,
                abstract=paper.abstract,
                year=paper.year,
                venue=paper.venue,
                doi=paper.doi,
                authors=author_names,
                institutions=institutions,
                label=cls.label,
                confidence=cls.confidence,
                priority=cls.review_priority,
                reasons=reasons,
                last_classified_at=cls.last_classified_at,
                source=paper.source,
                provenance=paper.provenance,
                corpus_sources=normalize_corpus_sources(
                    paper.corpus_sources or []
                )
                or infer_corpus_sources(
                    provenance=paper.provenance,
                    source=paper.source,
                    retrieval_tier=paper.retrieval_tier,
                    ac_known_publication=paper.ac_known_publication,
                ),
                full_text_url=_full_text_url(paper),
                has_human_review=paper.id in review_paper_ids,
                sdl_judgement=review.sdl_judgement if review else None,
                ac_relevance_judgement=(
                    review.ac_relevance_judgement if review else None
                ),
                ai_for_science_judgement=(
                    review.ai_for_science_judgement if review else None
                ),
                review_status=review.review_status if review else None,
                evidence_level=review.evidence_level if review else None,
                judgement_basis=review.judgement_basis if review else None,
                screening_stage=cls.screening_stage,
                screening_route=cls.screening_route,
                screening_reason=cls.screening_reason,
                review_assignee=cls.review_assignee,
                review_assigned_at=cls.review_assigned_at,
                review_assigned_by=cls.review_assigned_by,
            )
        )
    return out


def _full_text_url(paper: Paper) -> str | None:
    metadata = paper.raw_metadata or {}
    for key in ("pdf_url", "full_text_url", "landing_page_url", "url"):
        value = metadata.get(key)
        if isinstance(value, str) and value.startswith(("https://", "http://")):
            return value
    if paper.doi:
        return f"https://doi.org/{paper.doi}"
    return None


def get_next(
    session: Session,
    *,
    assignee: str | None = None,
    unassigned_only: bool = False,
) -> QueueItem | None:
    items = list_queue(
        session,
        limit=1,
        assignee=assignee,
        unassigned_only=unassigned_only,
    )
    return items[0] if items else None


def queue_size(
    session: Session,
    *,
    assignee: str | None = None,
    unassigned_only: bool = False,
) -> int:
    stmt = select(PaperClassification).where(
        PaperClassification.needs_review.is_(True),
        PaperClassification.human_confirmed.is_(False),
        PaperClassification.screening_route.in_(REVIEW_ROUTES),
    )
    normalized_assignee = (assignee or "").strip()
    if unassigned_only:
        stmt = stmt.where(PaperClassification.review_assignee.is_(None))
    elif normalized_assignee:
        stmt = stmt.where(
            PaperClassification.review_assignee == normalized_assignee
        )
    cnt = session.execute(stmt).all()
    return len(cnt)


def assign_review(
    session: Session,
    paper_id: str,
    *,
    assignee: str | None,
    assigned_by: str | None = None,
) -> PaperClassification:
    """Claim, reassign, or release a queued review.

    A normal claim cannot overwrite another reviewer's active claim. Releasing
    the claim is represented by a null/blank assignee.
    """
    cls = session.execute(
        select(PaperClassification).where(
            PaperClassification.paper_id == paper_id
        )
    ).scalar_one_or_none()
    if cls is None:
        raise ValueError(f"Paper not found in classifications: {paper_id}")
    if cls.human_confirmed or not cls.needs_review:
        raise ValueError(f"Paper is not currently queued for review: {paper_id}")

    normalized_assignee = (assignee or "").strip() or None
    if (
        normalized_assignee
        and cls.review_assignee
        and cls.review_assignee != normalized_assignee
    ):
        raise RuntimeError(
            f"Paper is already assigned to {cls.review_assignee}"
        )

    cls.review_assignee = normalized_assignee
    cls.review_assigned_at = datetime.now(UTC) if normalized_assignee else None
    cls.review_assigned_by = (
        (assigned_by or "").strip() or normalized_assignee
        if normalized_assignee
        else None
    )
    session.commit()
    session.refresh(cls)
    return cls


# ---------------------------------------------------------------------------
# Confirm / skip
# ---------------------------------------------------------------------------


def confirm_classification(
    session: Session,
    paper_id: str,
    *,
    reviewer: str | None = None,
) -> PaperClassification:
    """Lock in the current label as reviewer-confirmed.

    No label change — this is the "yes the system was right" path. Pulls
    the paper out of the queue.
    """
    cls_id = _resolve_cls_id(session, paper_id)
    if cls_id is None:
        raise ValueError(f"No classification for paper {paper_id}")
    cls = session.get(PaperClassification, cls_id)
    if cls is None:
        raise ValueError(f"No classification for paper {paper_id}")
    previous_label = cls.label
    review = cls.paper.review
    if review is None:
        review = HumanReview(id=f"rev_{uuid.uuid4().hex[:12]}", paper_id=paper_id)
        cls.paper.review = review
        session.add(review)
    review.human_label = cls.label
    review.reviewer = reviewer
    review.notes = review.notes or "confirmed current classifier label"
    cls.human_confirmed = True
    cls.human_confirmed_at = datetime.now(UTC)
    cls.human_confirmed_by = reviewer
    cls.needs_review = False
    cls.review_priority = 0.0
    session.flush()

    if os.environ.get("PAS_ACTIVE_LEARNING", "1") == "1":
        try:
            from app.services.active_learning import on_review_submitted

            on_review_submitted(
                session,
                paper_id,
                new_label=cls.label,
                previous_label=previous_label,
                reviewer=reviewer,
                run_retraining=False,
                commit=False,
            )
        except Exception:
            # Review confirmation must not be blocked by training-side issues.
            pass
    apply_paper_screening(session, cls.paper, commit=False)
    session.commit()

    return cls


def skip_for_now(
    session: Session,
    paper_id: str,
    *,
    cooldown_days: int = 7,
) -> PaperClassification:
    """Push this paper to the back of the queue for `cooldown_days`.

    Implementation: bump last_classified_at forward so the age-bonus
    won't surface it again for a while, and clear needs_review.
    """
    cls_id = _resolve_cls_id(session, paper_id)
    if cls_id is None:
        raise ValueError(f"No classification for paper {paper_id}")
    cls = session.get(PaperClassification, cls_id)
    if cls is None:
        raise ValueError(f"No classification for paper {paper_id}")
    cls.needs_review = False
    cls.review_priority = 0.0
    cls.last_classified_at = datetime.now(UTC) + timedelta(days=cooldown_days)
    session.commit()
    return cls


def _resolve_cls_id(session: Session, paper_id: str) -> str:
    """Helper: get the classification id for a paper_id."""
    row = session.execute(
        select(PaperClassification.id).where(
            PaperClassification.paper_id == paper_id
        )
    ).scalar_one_or_none()
    return row
