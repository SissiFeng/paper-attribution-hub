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

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import HumanReview, Paper, PaperClassification, PaperEvidence

# Tunables — keep them small + interpretable.
_W_UNCERTAIN = 0.45
_W_LOW_CONF_AUTO = 0.30
_W_DISCOVERED_AUTO = 0.25
_W_DISQUALIFYING_BUT_HIGH = 0.40
_W_LEARNED_DISAGREES = 0.20
_W_NO_REVIEW_YET = 0.05
_W_AGE_DAYS = 0.01  # +0.01 per day since classification, capped at 0.10


@dataclass
class QueueItem:
    paper_id: str
    title: str
    label: str
    confidence: float
    priority: float
    reasons: list[str]
    last_classified_at: datetime | None
    provenance: str | None
    has_human_review: bool


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
        return 0.0, ["no classification yet"]
    if cls.human_confirmed:
        return 0.0, ["already human-confirmed"]

    now = now or datetime.now(UTC)
    reasons: list[str] = []
    score = 0.0

    if cls.label == "UNCERTAIN":
        score += _W_UNCERTAIN
        reasons.append("Label is UNCERTAIN — needs adjudication.")

    if (
        (paper.provenance or "").startswith("discovered_auto")
        and cls.label in {"CORE_RELEVANT", "RELATED_RELEVANT"}
        and cls.confidence < 0.75
    ):
        score += _W_LOW_CONF_AUTO
        reasons.append(
            f"Auto-ingested by discovery with low confidence ({cls.confidence:.2f})."
        )

    if (paper.provenance or "").startswith("discovered_auto") and not has_review:
        score += _W_DISCOVERED_AUTO
        reasons.append("Discovered automatically; reviewer should verify.")

    if disqualifying_count > 0 and cls.label in {
        "CORE_RELEVANT",
        "RELATED_RELEVANT",
    }:
        score += _W_DISQUALIFYING_BUT_HIGH
        reasons.append(
            f"{disqualifying_count} disqualifying evidence row(s) recorded "
            f"despite label {cls.label} — sanity check."
        )

    if "learned-" in (cls.model_version or "") and "+judge" not in (
        cls.model_version or ""
    ):
        # Learned model touched the label without the judge agreeing.
        score += _W_LEARNED_DISAGREES
        reasons.append("Learned classifier overrode the rules — verify.")

    if not has_review:
        score += _W_NO_REVIEW_YET

    if cls.last_classified_at:
        last = cls.last_classified_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        age = (now - last).days
        if age > 0:
            bump = min(_W_AGE_DAYS * age, 0.10)
            score += bump
            if bump >= 0.05:
                reasons.append(f"Classified {age} days ago; due for re-look.")

    return min(round(score, 3), 1.0), reasons


# ---------------------------------------------------------------------------
# Enqueue
# ---------------------------------------------------------------------------


_FLAG_THRESHOLD = 0.20


def refresh_queue(session: Session, *, threshold: float = _FLAG_THRESHOLD) -> int:
    """Walk all papers, compute priorities, persist `needs_review` flags.

    Returns the number of papers flagged."""
    now = datetime.now(UTC)
    disqualifying_counts = _disqualifying_counts(session)
    review_paper_ids = {
        pid for (pid,) in session.execute(select(HumanReview.paper_id)).all()
    }
    flagged = 0
    for paper in session.execute(select(Paper)).scalars():
        cls = paper.classification
        if cls is None or cls.human_confirmed:
            if cls is not None and cls.needs_review and cls.human_confirmed:
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
) -> list[QueueItem]:
    stmt = (
        select(Paper, PaperClassification)
        .join(PaperClassification, PaperClassification.paper_id == Paper.id)
    )
    if not include_confirmed:
        stmt = stmt.where(PaperClassification.human_confirmed.is_(False))
        stmt = stmt.where(PaperClassification.needs_review.is_(True))
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
        out.append(
            QueueItem(
                paper_id=paper.id,
                title=paper.title,
                label=cls.label,
                confidence=cls.confidence,
                priority=cls.review_priority,
                reasons=reasons,
                last_classified_at=cls.last_classified_at,
                provenance=paper.provenance,
                has_human_review=paper.id in review_paper_ids,
            )
        )
    return out


def get_next(session: Session) -> QueueItem | None:
    items = list_queue(session, limit=1)
    return items[0] if items else None


def queue_size(session: Session) -> int:
    cnt = session.execute(
        select(PaperClassification).where(
            PaperClassification.needs_review.is_(True),
            PaperClassification.human_confirmed.is_(False),
        )
    ).all()
    return len(cnt)


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
    cls.human_confirmed = True
    cls.human_confirmed_at = datetime.now(UTC)
    cls.human_confirmed_by = reviewer
    cls.needs_review = False
    cls.review_priority = 0.0
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
