"""Typed-entity signal (PaperEntity rows) in the rule classifier."""
from __future__ import annotations

from app.models import PaperEntity
from app.services.relevance_classifier import (
    LABEL_ADJACENT,
    LABEL_CORE,
    LABEL_EXCLUDE,
    LABEL_UNCERTAIN,
    _apply_rules,
    _entity_signal,
    classify_all,
)


def _entity(paper_id: str, entity_type: str, normalized: str) -> PaperEntity:
    return PaperEntity(
        id=f"ent_{paper_id}_{entity_type}_{normalized}".replace(" ", "_"),
        paper_id=paper_id,
        entity_type=entity_type,
        name=normalized,
        normalized_name=normalized,
    )


def test_entity_signal_formula():
    rows = [
        _entity("X", "method", "bayesian optimization"),
        _entity("X", "method", "flow chemistry"),
        _entity("X", "instrument", "Chemspeed"),
        _entity("X", "material", "perovskite"),
    ]
    score, summary = _entity_signal(rows)
    # 0.25*2 methods + 0.20*1 instrument + 0.10*1 material = 0.8
    assert score == 0.8
    assert summary["method"] == ["bayesian optimization", "flow chemistry"]
    assert summary["instrument_or_software"] == ["Chemspeed"]
    assert summary["material"] == ["perovskite"]
    # Empty input → zero score, no summary.
    assert _entity_signal([]) == (0.0, {})


def test_entity_only_caps_at_adjacent():
    label, conf = _apply_rules(
        author_score=0.0, institution_score=0.0, topic_score=0.0, entity_score=1.0
    )
    assert label == LABEL_ADJACENT
    assert conf >= 0.5
    # Weak entity evidence alone changes nothing.
    label, _ = _apply_rules(
        author_score=0.0, institution_score=0.0, topic_score=0.0, entity_score=0.3
    )
    assert label == LABEL_EXCLUDE


def test_entity_score_zero_is_identical_to_no_argument():
    grid = [
        (1.0, 1.0, 0.8),
        (1.0, 0.0, 0.2),
        (0.0, 1.0, 0.85),
        (0.0, 0.0, 0.75),
        (0.0, 0.5, 0.45),
        (0.0, 0.0, 0.0),
    ]
    for author, inst, topic in grid:
        baseline = _apply_rules(
            author_score=author, institution_score=inst, topic_score=topic
        )
        with_zero = _apply_rules(
            author_score=author,
            institution_score=inst,
            topic_score=topic,
            entity_score=0.0,
        )
        assert baseline == with_zero


def test_paper_with_method_and_instrument_entities_gets_score_and_reason(
    seeded_session,
):
    # P010 is an unrelated climate review (EXCLUDE with no other signal).
    seeded_session.add_all(
        [
            _entity("P010", "method", "bayesian optimization"),
            _entity("P010", "method", "flow chemistry"),
            _entity("P010", "instrument", "Chemspeed"),
        ]
    )
    seeded_session.commit()

    papers = classify_all(seeded_session)
    cls = {p.id: p.classification for p in papers if p.classification}["P010"]
    # entity_score = 0.25*2 + 0.20*1 = 0.7 → entity-only lift caps at ADJACENT.
    assert cls.label == LABEL_ADJACENT
    assert any("SDL method term(s): bayesian optimization" in r for r in cls.reasons)
    assert any("SDL instrument/software term(s): Chemspeed" in r for r in cls.reasons)


def test_zero_entity_behavior_unchanged(seeded_session):
    """With no PaperEntity rows, labels match the pre-entity-signal expectations
    locked in by test_relevance_rules.test_end_to_end_classifies_sample_papers."""
    papers = classify_all(seeded_session)
    labels = {p.id: p.classification.label for p in papers if p.classification}
    assert labels["P001"] == LABEL_CORE
    assert labels["P003"] in {LABEL_EXCLUDE, LABEL_ADJACENT, LABEL_UNCERTAIN}
    assert labels["P010"] == LABEL_EXCLUDE
    assert labels["P006"] == LABEL_CORE
    # No entity reason lines anywhere.
    for p in papers:
        if p.classification and p.classification.reasons:
            assert not any("SDL" in r and "term(s)" in r for r in p.classification.reasons)
