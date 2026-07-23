"""A real section-ablation scorer backed by persisted evidence.

For a paper that already has extracted ``PaperEvidence`` rows, each ablation
variant is scored by keeping only the evidence whose source section is in the
variant. This answers "which section carries which claim's evidence" without
re-running the production classifier, so it stays decoupled from the evolving
scoring code it is meant to measure.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PaperEvidence
from app.services.eval_harness.section_ablation import (
    ScoreResult,
    SectionGain,
    VariantOutcome,
    build_ablation_variants,
    information_gain,
    run_ablation,
)

_ABSTRACT = "abstract"


def available_sections(session: Session, paper_id: str) -> set[str]:
    """Abstract plus every distinct evidence source section for the paper."""
    sources = session.execute(
        select(PaperEvidence.evidence_source).where(
            PaperEvidence.paper_id == paper_id
        )
    ).scalars()
    return {_ABSTRACT} | {s for s in sources if s}


def build_evidence_section_scorer(
    session: Session, paper_id: str
) -> Callable[[frozenset[str]], ScoreResult]:
    rows = list(
        session.execute(
            select(PaperEvidence).where(PaperEvidence.paper_id == paper_id)
        ).scalars()
    )

    def scorer(section_types: frozenset[str]) -> ScoreResult:
        kept = [
            r for r in rows if r.evidence_source in section_types and (r.score or 0) > 0
        ]
        evidence_types = tuple(sorted({r.evidence_type for r in kept}))
        confidence = min(1.0, sum(r.score for r in kept))
        label = "SUPPORTED" if kept else "INDETERMINATE"
        return ScoreResult(
            label=label, confidence=round(confidence, 3), evidence_types=evidence_types
        )

    return scorer


@dataclass(frozen=True)
class PaperAblationReport:
    paper_id: str
    outcomes: list[VariantOutcome]
    information_gain: list[SectionGain]


def run_paper_section_ablation(
    session: Session, paper_id: str
) -> PaperAblationReport:
    variants = build_ablation_variants(available_sections(session, paper_id))
    scorer = build_evidence_section_scorer(session, paper_id)
    outcomes = run_ablation(variants, scorer)
    return PaperAblationReport(
        paper_id=paper_id,
        outcomes=outcomes,
        information_gain=information_gain(outcomes),
    )
