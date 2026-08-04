from __future__ import annotations

import pytest

from app.models import PaperEvidence
from app.services.attribution_evidence_scoring import score_attribution_evidence
from app.services.relevance_classifier import (
    LABEL_ADJACENT,
    LABEL_CORE,
    LABEL_RELATED,
    _apply_attribution_evidence_decision,
)


def _score(**overrides):
    inputs = {
        "evidence_rows": [],
        "author_score": 0.0,
        "institution_score": 0.0,
        "topic_score": 0.0,
        "network_score": 0.0,
        "citation_score": 0.0,
        "has_funding_evidence": False,
        "has_second_degree": False,
        "cites_ac_core": False,
        "has_core_topic_match": False,
    }
    inputs.update(overrides)
    return score_attribution_evidence(**inputs)


def test_aet_classifier_authority_is_default_off():
    from app.config import settings

    assert settings.attribution_evidence_classifier_enabled is False


def test_independent_topic_affiliation_and_collaboration_paths_promote_core():
    signals = _score(
        institution_score=1.0,
        topic_score=1.0,
        network_score=0.69,
        has_second_degree=True,
        has_core_topic_match=True,
    )

    label, confidence, reason = _apply_attribution_evidence_decision(
        LABEL_RELATED, 0.68, signals
    )

    assert signals.score == pytest.approx(0.52)
    assert {path.evidence_type for path in signals.paths if path.weight > 0} == {
        "ac_affiliation",
        "topic_relevance",
        "collaborator_link",
    }
    assert all(
        path.path_id.startswith(f"aet-path:{signals.generation_id}:")
        for path in signals.paths
    )
    assert label == LABEL_CORE
    assert confidence >= 0.85
    assert reason == "AET_CORROBORATED_CORE"


def test_collaboration_without_sdl_path_caps_at_adjacent():
    signals = _score(
        institution_score=1.0,
        network_score=0.98,
        has_second_degree=True,
    )

    label, confidence, reason = _apply_attribution_evidence_decision(
        "EXCLUDE", 0.2, signals
    )

    assert signals.score == pytest.approx(0.4)
    assert label == LABEL_ADJACENT
    assert confidence >= 0.55
    assert reason == "AET_COLLABORATION_ONLY"


def test_negative_path_blocks_positive_promotion_and_is_auditable():
    negative = PaperEvidence(
        id="ev_negative",
        paper_id="P_TEST",
        evidence_type="disqualifying",
        evidence_source="llm_judge",
        evidence_text="The optimization method is background only.",
        score=-0.4,
    )
    signals = _score(
        evidence_rows=[negative],
        institution_score=1.0,
        topic_score=0.8,
        has_core_topic_match=True,
    )

    label, _, reason = _apply_attribution_evidence_decision(
        LABEL_RELATED, 0.68, signals
    )

    assert signals.conflicting is True
    assert signals.negative_score == pytest.approx(0.25)
    negative_path = next(
        path for path in signals.paths if path.source_evidence_id == "ev_negative"
    )
    assert signals.negative_path_ids == [negative_path.path_id]
    assert negative_path.quote == "The optimization method is background only."
    assert label == LABEL_ADJACENT
    assert reason == "AET_STRONG_NEGATIVE"


@pytest.mark.parametrize(
    "overrides",
    [
        {
            "institution_score": 1.0,
            "topic_score": 1.0,
            "has_core_topic_match": True,
        },
        {
            "topic_score": 1.0,
            "network_score": 0.9,
            "has_core_topic_match": True,
            "has_second_degree": True,
        },
    ],
)
def test_partial_corroboration_does_not_promote_core(overrides):
    signals = _score(**overrides)

    label, _, reason = _apply_attribution_evidence_decision(
        LABEL_RELATED, 0.68, signals
    )

    assert label == LABEL_RELATED
    assert reason is None


def test_positive_background_path_keeps_polarity_but_contributes_no_weight():
    background = PaperEvidence(
        id="ev_background",
        paper_id="P_TEST",
        evidence_type="sdl_methodology",
        evidence_source="introduction",
        evidence_text="The SDL method is discussed as prior work.",
        score=0.7,
        extra={
            "attribution_evidence": {
                "contract_version": "aet-evidence-meta-v0.1",
                "polarity": "positive",
                "centrality": "background_only",
            }
        },
    )

    signals = _score(evidence_rows=[background])
    path = signals.paths[0]

    assert path.polarity == "positive"
    assert path.centrality == "background_only"
    assert path.raw_score == pytest.approx(0.7)
    assert path.weight == 0.0
    assert signals.negative_score == 0.0


def test_negative_funding_row_does_not_create_hidden_strong_ac_signal():
    funding = PaperEvidence(
        id="ev_negative_funding",
        paper_id="P_TEST",
        evidence_type="funding_acknowledgement",
        evidence_source="acknowledgements",
        evidence_text="The paper explicitly denies receiving AC support.",
        score=-0.4,
    )

    signals = _score(
        evidence_rows=[funding],
        has_funding_evidence=True,
    )
    label, _, reason = _apply_attribution_evidence_decision(
        LABEL_RELATED, 0.68, signals
    )

    assert signals.has_strong_ac_evidence is False
    assert signals.positive_score == 0.0
    assert signals.negative_score == pytest.approx(0.25)
    assert label == LABEL_ADJACENT
    assert reason == "AET_STRONG_NEGATIVE"
