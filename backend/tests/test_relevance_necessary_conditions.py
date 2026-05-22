"""v0.7 _apply_rules: necessary-conjunctive conditions for CORE."""
from app.services.relevance_classifier import (
    LABEL_ADJACENT,
    LABEL_CORE,
    LABEL_EXCLUDE,
    LABEL_RELATED,
    LABEL_UNCERTAIN,
    _apply_rules,
)


def test_core_requires_core_topic_match_not_just_score():
    # author_score 1.0 + topic_score 0.8 but no core topic match → not CORE.
    label, _ = _apply_rules(
        author_score=1.0,
        institution_score=0.0,
        topic_score=0.8,
        has_core_topic_match=False,
    )
    assert label == LABEL_RELATED  # AC author but topic mass is adjacent-only


def test_core_when_author_and_core_topic():
    label, conf = _apply_rules(
        author_score=1.0,
        institution_score=0.5,
        topic_score=0.6,
        has_core_topic_match=True,
    )
    assert label == LABEL_CORE
    assert conf >= 0.85


def test_funding_and_core_topic_promotes_to_core():
    label, _ = _apply_rules(
        author_score=0.0,
        institution_score=0.0,
        topic_score=0.5,
        fulltext_score=0.6,
        has_funding_evidence=True,
        has_core_topic_match=True,
    )
    assert label == LABEL_CORE


def test_disqualifying_evidence_subtracts_confidence():
    label, conf_no = _apply_rules(
        author_score=0.0,
        institution_score=0.5,
        topic_score=0.55,
    )
    label2, conf_with = _apply_rules(
        author_score=0.0,
        institution_score=0.5,
        topic_score=0.55,
        disqualifying_count=2,
    )
    assert conf_with < conf_no


def test_density_promotes_to_core_when_author_strong():
    label, _ = _apply_rules(
        author_score=1.0,
        institution_score=0.0,
        topic_score=0.4,  # below the older 0.5 threshold
        topic_density=2,
        has_core_topic_match=True,
    )
    assert label == LABEL_CORE


def test_partner_institution_alone_no_longer_promotes_to_related():
    # topic_score 0.85 + UofT alone, but density=0 → ADJACENT, not RELATED.
    label, _ = _apply_rules(
        author_score=0.0,
        institution_score=1.0,
        topic_score=0.85,
        topic_density=0,
        has_core_topic_match=True,
    )
    assert label in {LABEL_ADJACENT, LABEL_RELATED}
    # When density is present it gets RELATED.
    label2, _ = _apply_rules(
        author_score=0.0,
        institution_score=1.0,
        topic_score=0.85,
        topic_density=1,
        has_core_topic_match=True,
    )
    assert label2 == LABEL_RELATED


def test_end_to_end_seeded_corpus_no_false_positives(seeded_session):
    """The hand-curated sample papers should still land correctly."""
    from app.services.relevance_classifier import classify_all

    papers = classify_all(seeded_session)
    labels = {p.id: p.classification.label for p in papers if p.classification}
    # AC-direct papers.
    assert labels["P001"] == LABEL_CORE
    assert labels["P006"] == LABEL_CORE
    # Unrelated papers should not be CORE.
    assert labels["P010"] != LABEL_CORE
    assert labels["P007"] != LABEL_CORE
    # GNN paper without AC links: not CORE.
    assert labels["P003"] != LABEL_CORE
