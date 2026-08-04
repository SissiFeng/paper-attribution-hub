"""Real section-ablation scorer: filter a paper's extracted evidence by section.

Measures which section carries which claim's evidence without re-running the
(churning) classifier — it reads the already-persisted PaperEvidence rows.
"""

from __future__ import annotations

from app.models import Paper, PaperEvidence
from app.services.eval_harness.evidence_scorer import (
    available_sections,
    build_evidence_section_scorer,
    run_paper_section_ablation,
)


def _seed(session):
    session.add(Paper(id="P1", title="t", abstract="a", year=2024))
    session.add_all(
        [
            PaperEvidence(
                id="e1", paper_id="P1", evidence_type="sdl_methodology",
                evidence_source="methods", evidence_text="closed-loop", score=0.4,
            ),
            PaperEvidence(
                id="e2", paper_id="P1", evidence_type="funding_acknowledgement",
                evidence_source="acknowledgements", evidence_text="AC funding", score=0.6,
            ),
        ]
    )
    session.flush()


def test_available_sections_includes_abstract_and_evidence_sources(session):
    _seed(session)
    sections = available_sections(session, "P1")
    assert "abstract" in sections
    assert "methods" in sections
    assert "acknowledgements" in sections


def test_scorer_filters_evidence_by_section(session):
    _seed(session)
    scorer = build_evidence_section_scorer(session, "P1")

    abstract_only = scorer(frozenset({"abstract"}))
    assert abstract_only.label == "INDETERMINATE"
    assert abstract_only.evidence_types == ()

    with_ack = scorer(frozenset({"abstract", "acknowledgements"}))
    assert with_ack.label == "SUPPORTED"
    assert "funding_acknowledgement" in with_ack.evidence_types
    assert with_ack.confidence > 0


def test_run_paper_section_ablation_shows_acknowledgement_information_gain(session):
    _seed(session)
    report = run_paper_section_ablation(session, "P1")
    gains = {g.variant: g for g in report.information_gain}

    # Adding acknowledgements flips the label away from the abstract-only baseline.
    assert gains["abstract_acknowledgements"].label_changed is True
    assert gains["abstract_acknowledgements"].confidence_delta > 0
    # The full run surfaces both evidence types somewhere in its outcomes.
    all_types = {t for o in report.outcomes for t in o.result.evidence_types}
    assert {"sdl_methodology", "funding_acknowledgement"} <= all_types
