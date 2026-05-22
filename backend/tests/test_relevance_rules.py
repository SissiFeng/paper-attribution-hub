from app.services.relevance_classifier import (
    LABEL_ADJACENT,
    LABEL_CORE,
    LABEL_EXCLUDE,
    LABEL_RELATED,
    LABEL_UNCERTAIN,
    _apply_rules,
)


def test_core_relevant_when_author_and_topic_strong():
    label, conf = _apply_rules(author_score=1.0, institution_score=1.0, topic_score=0.8)
    assert label == LABEL_CORE
    assert conf >= 0.85


def test_related_when_author_strong_topic_weak():
    label, _ = _apply_rules(author_score=1.0, institution_score=0.0, topic_score=0.2)
    assert label == LABEL_RELATED


def test_related_when_topic_strong_and_partner_institution():
    label, _ = _apply_rules(author_score=0.0, institution_score=1.0, topic_score=0.85)
    assert label == LABEL_RELATED


def test_adjacent_when_only_topic_signal():
    label, _ = _apply_rules(author_score=0.0, institution_score=0.0, topic_score=0.75)
    assert label == LABEL_ADJACENT


def test_uncertain_for_midrange_signal():
    label, _ = _apply_rules(author_score=0.0, institution_score=0.5, topic_score=0.45)
    assert label == LABEL_UNCERTAIN


def test_exclude_when_no_signal():
    label, _ = _apply_rules(author_score=0.0, institution_score=0.0, topic_score=0.0)
    assert label == LABEL_EXCLUDE


def test_end_to_end_classifies_sample_papers(seeded_session):
    from app.services.relevance_classifier import classify_all

    papers = classify_all(seeded_session)
    labels = {p.id: p.classification.label for p in papers if p.classification}
    # P001 has Alan Aspuru-Guzik + SDL topic.
    assert labels["P001"] == LABEL_CORE
    # P003 is generic GNN + no AC author + no UofT → should not be core.
    assert labels["P003"] in {LABEL_EXCLUDE, LABEL_ADJACENT, LABEL_UNCERTAIN}
    # P010 is unrelated climate review.
    assert labels["P010"] == LABEL_EXCLUDE
    # P006 has Curtis Berlinguette + UBC + SDL topic.
    assert labels["P006"] == LABEL_CORE
