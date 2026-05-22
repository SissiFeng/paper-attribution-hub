"""Evidence-gap analysis (v0.7 review-loop UI).

Surfaces papers whose classification looks confident but is missing one or
more expected evidence types — the kind of paper a reviewer should sanity-
check before the system locks the label in.

Buckets:
  * core_missing_funding         — CORE/RELATED labels without funding_acknowledgement
  * core_missing_methods         — CORE/RELATED without sdl_methodology
  * adjacent_with_funding        — ADJACENT with funding evidence (under-promoted?)
  * disqualifying_vs_high_label  — high label but has disqualifying rows
  * low_confidence_auto_core     — auto-ingested CORE/RELATED below 0.75 conf

Each entry tells the reviewer *what* is missing (or contradicting) so they
can decide whether to confirm or downgrade.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Paper, PaperClassification, PaperEvidence

# Evidence types we expect strong papers to have.
_FUNDING = "funding_acknowledgement"
_METHODS = "sdl_methodology"
_FIGURE = "figure_caption_sdl"
_DISQUALIFYING = "disqualifying"

HIGH_LABELS = {"CORE_RELEVANT", "RELATED_RELEVANT"}


@dataclass
class GapEntry:
    paper_id: str
    title: str
    label: str
    confidence: float
    missing_types: list[str]
    present_types: list[str]
    reason: str


@dataclass
class GapBucket:
    bucket: str
    label: str
    description: str
    count: int
    entries: list[GapEntry] = field(default_factory=list)


@dataclass
class GapReport:
    total_papers_scanned: int
    buckets: list[GapBucket]


def build_evidence_gap_report(session: Session, *, sample_size: int = 12) -> GapReport:
    """`sample_size` = how many example papers to include per bucket. Counts
    are exact, but the API caps the list per bucket so payloads stay small."""
    # Build evidence index once.
    evidence_by_paper: dict[str, list[PaperEvidence]] = {}
    for ev in session.execute(select(PaperEvidence)).scalars():
        evidence_by_paper.setdefault(ev.paper_id, []).append(ev)

    papers = list(
        session.execute(
            select(Paper).join(
                PaperClassification, PaperClassification.paper_id == Paper.id
            )
        ).scalars()
    )

    buckets: dict[str, GapBucket] = {
        "core_missing_funding": GapBucket(
            bucket="core_missing_funding",
            label="High label · missing AC funding evidence",
            description=(
                "Papers labeled CORE/RELATED whose acknowledgements section "
                "doesn't carry an AC funding mention. Worth verifying."
            ),
            count=0,
        ),
        "core_missing_methods": GapBucket(
            bucket="core_missing_methods",
            label="High label · missing SDL methodology evidence",
            description=(
                "Papers labeled CORE/RELATED whose methods section "
                "doesn't reference SDL terminology."
            ),
            count=0,
        ),
        "adjacent_with_funding": GapBucket(
            bucket="adjacent_with_funding",
            label="ADJACENT · has funding evidence (under-promoted?)",
            description=(
                "ADJACENT papers that nonetheless carry AC funding "
                "acknowledgements. May deserve RELATED."
            ),
            count=0,
        ),
        "disqualifying_vs_high_label": GapBucket(
            bucket="disqualifying_vs_high_label",
            label="Contradiction · high label but disqualifying evidence",
            description=(
                "Papers with at least one LLM/active-learning disqualifying "
                "row but a CORE/RELATED label. Strong sanity-check signal."
            ),
            count=0,
        ),
        "low_confidence_auto_core": GapBucket(
            bucket="low_confidence_auto_core",
            label="Auto-ingested · low-confidence CORE/RELATED",
            description=(
                "Papers discovered automatically and given a high label "
                "with confidence below 0.75. Reviewer attention recommended."
            ),
            count=0,
        ),
    }

    for paper in papers:
        cls = paper.classification
        if cls is None:
            continue
        evs = evidence_by_paper.get(paper.id, [])
        present_types = sorted({e.evidence_type for e in evs})
        has_funding = any(e.evidence_type == _FUNDING and e.score > 0 for e in evs)
        has_methods = any(e.evidence_type == _METHODS for e in evs)
        has_disqualifying = any(e.evidence_type == _DISQUALIFYING for e in evs)

        # core_missing_funding
        if cls.label in HIGH_LABELS and not has_funding:
            _add_entry(
                buckets["core_missing_funding"],
                paper=paper,
                cls=cls,
                missing=[_FUNDING],
                present=present_types,
                reason=(
                    f"Labeled {cls.label} (conf {cls.confidence:.2f}) but no AC "
                    "funding evidence in the acknowledgements."
                ),
                sample_size=sample_size,
            )

        # core_missing_methods
        if cls.label in HIGH_LABELS and not has_methods:
            _add_entry(
                buckets["core_missing_methods"],
                paper=paper,
                cls=cls,
                missing=[_METHODS],
                present=present_types,
                reason=(
                    f"Labeled {cls.label} but the methods section never "
                    "references SDL methodology."
                ),
                sample_size=sample_size,
            )

        # adjacent_with_funding
        if cls.label == "ADJACENT" and has_funding:
            _add_entry(
                buckets["adjacent_with_funding"],
                paper=paper,
                cls=cls,
                missing=[],
                present=present_types,
                reason=(
                    "Carries AC funding acknowledgement but lands at ADJACENT — "
                    "possible under-promotion."
                ),
                sample_size=sample_size,
            )

        # disqualifying_vs_high_label
        if cls.label in HIGH_LABELS and has_disqualifying:
            _add_entry(
                buckets["disqualifying_vs_high_label"],
                paper=paper,
                cls=cls,
                missing=[],
                present=present_types,
                reason=(
                    "Disqualifying evidence is recorded but label is still "
                    f"{cls.label}. Reviewer should reconcile."
                ),
                sample_size=sample_size,
            )

        # low_confidence_auto_core
        if (
            cls.label in HIGH_LABELS
            and cls.confidence < 0.75
            and (paper.provenance or "").startswith("discovered_auto")
        ):
            _add_entry(
                buckets["low_confidence_auto_core"],
                paper=paper,
                cls=cls,
                missing=[],
                present=present_types,
                reason=(
                    f"Discovered automatically, labeled {cls.label} with "
                    f"confidence {cls.confidence:.2f} (< 0.75)."
                ),
                sample_size=sample_size,
            )

    return GapReport(
        total_papers_scanned=len(papers),
        buckets=list(buckets.values()),
    )


def _add_entry(
    bucket: GapBucket,
    *,
    paper: Paper,
    cls: PaperClassification,
    missing: list[str],
    present: list[str],
    reason: str,
    sample_size: int,
) -> None:
    bucket.count += 1
    if len(bucket.entries) < sample_size:
        bucket.entries.append(
            GapEntry(
                paper_id=paper.id,
                title=paper.title,
                label=cls.label,
                confidence=round(cls.confidence, 3),
                missing_types=missing,
                present_types=present,
                reason=reason,
            )
        )
