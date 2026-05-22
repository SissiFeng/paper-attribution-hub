"""v0.7 topic classifier behavior: boundaries, negation, blacklist, density."""
from sqlalchemy import select

from app.models import Topic
from app.services.topic_classifier import TopicClassifier


def test_self_driving_car_does_not_fire_sdl(seeded_session):
    topics = list(seeded_session.execute(select(Topic)).scalars())
    classifier = TopicClassifier(topics)
    # The phrase 'self-driving car' is on the SDL blacklist, so even though
    # 'self-driving' looks tempting we must not score the topic.
    result = classifier.classify_detailed(
        "Review of self-driving car perception systems",
        "We survey self-driving car LIDAR pipelines.",
        "",
    )
    sdl = next(
        (m for m in result.matches if m.topic_id == "self_driving_labs"), None
    )
    assert sdl is not None
    assert sdl.score == 0.0
    assert sdl.blacklist_hits  # blacklist explanation is preserved


def test_negated_sdl_drops_topic(seeded_session):
    topics = list(seeded_session.execute(select(Topic)).scalars())
    classifier = TopicClassifier(topics)
    result = classifier.classify_detailed(
        "Surrogate models for chemistry",
        "No autonomous platform is described in this work. "
        "We do not use a self-driving lab.",
        "",
    )
    sdl = next(
        (m for m in result.matches if m.topic_id == "self_driving_labs"), None
    )
    assert sdl is None or sdl.score == 0.0


def test_topic_density_counts_paragraph_cooccurrence(seeded_session):
    topics = list(seeded_session.execute(select(Topic)).scalars())
    classifier = TopicClassifier(topics)
    # Two keywords in the same paragraph.
    result = classifier.classify_detailed(
        "Closed-loop discovery",
        (
            "We present a self-driving lab combined with Bayesian optimization "
            "to discover materials in a closed-loop campaign."
        ),
        "",
    )
    assert result.topic_density >= 1


def test_legitimate_sdl_paper_still_scores(seeded_session):
    topics = list(seeded_session.execute(select(Topic)).scalars())
    classifier = TopicClassifier(topics)
    result = classifier.classify_detailed(
        "Autonomous closed-loop discovery of organic laser materials",
        "We present a self-driving laboratory combined with Bayesian optimization.",
        "self-driving lab; Bayesian optimization",
    )
    assert result.combined_score >= 0.5


def test_word_boundary_blocks_transformer_substring(seeded_session):
    topics = list(seeded_session.execute(select(Topic)).scalars())
    classifier = TopicClassifier(topics)
    # 'transformer' is an adjacent keyword, but it shouldn't match
    # 'transformerless'.
    result = classifier.classify_detailed(
        "Transformerless DC-DC converters",
        "We analyze transformerless converter topologies.",
        "",
    )
    gen_ml = next(
        (m for m in result.matches if m.topic_id == "generic_ml"), None
    )
    assert gen_ml is None or gen_ml.score == 0.0
