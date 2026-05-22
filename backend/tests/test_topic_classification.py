from sqlalchemy import select

from app.models import Topic
from app.services.topic_classifier import TopicClassifier


def test_sdl_paper_hits_core(seeded_session):
    topics = list(seeded_session.execute(select(Topic)).scalars())
    classifier = TopicClassifier(topics)
    score, matches = classifier.classify(
        "Autonomous closed-loop discovery of organic laser materials",
        "We present a self-driving laboratory combined with Bayesian optimization...",
        "self-driving lab; Bayesian optimization",
    )
    assert score >= 0.5
    assert any(m.topic_id == "self_driving_labs" and m.is_core for m in matches)


def test_unrelated_paper_low_score(seeded_session):
    topics = list(seeded_session.execute(select(Topic)).scalars())
    classifier = TopicClassifier(topics)
    score, matches = classifier.classify(
        "A review of climate models",
        "A broad review of climate modeling approaches.",
        "",
    )
    assert score < 0.3
    assert all(m.is_core is False for m in matches)


def test_adjacent_only_paper(seeded_session):
    topics = list(seeded_session.execute(select(Topic)).scalars())
    classifier = TopicClassifier(topics)
    score, matches = classifier.classify(
        "Graph neural networks for protein folding",
        "We propose a graph neural network architecture for protein folding.",
        "graph neural networks; deep learning",
    )
    # Only adjacent hits → score should stay capped low.
    assert score <= 0.5
    assert any(not m.is_core for m in matches)
