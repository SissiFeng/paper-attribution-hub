from app.services.drift_service import _cosine, build_drift_report
from app.services.filter_spec import PaperFilter


def _setup(session):
    from app.services.relevance_classifier import classify_all

    classify_all(session)


def test_cosine_identical_vectors_returns_one():
    v = {"a": 0.5, "b": 0.5}
    assert abs(_cosine(v, v) - 1.0) < 1e-9


def test_cosine_orthogonal_vectors_returns_zero():
    a = {"x": 1.0}
    b = {"y": 1.0}
    assert _cosine(a, b) == 0.0


def test_cosine_empty_returns_zero():
    assert _cosine({}, {"x": 1.0}) == 0.0


def test_drift_report_has_per_year_breakdown(fulltext_seeded_session):
    _setup(fulltext_seeded_session)
    report = build_drift_report(fulltext_seeded_session, PaperFilter())
    assert report.per_year
    # Each per-year entry should have at least the structure we expect.
    for y in report.per_year:
        assert y.year > 1900
        assert y.total_papers >= 0


def test_drift_report_threshold_respected(fulltext_seeded_session):
    _setup(fulltext_seeded_session)
    strict = build_drift_report(
        fulltext_seeded_session, PaperFilter(), drift_threshold=0.99
    )
    lax = build_drift_report(
        fulltext_seeded_session, PaperFilter(), drift_threshold=0.0
    )
    # A higher threshold should never produce FEWER drift events than a lower one.
    assert len(strict.drift_events) >= len(lax.drift_events)


def test_drift_uses_distinct_papers_for_topics_and_year_total(session):
    from app.models import Paper, PaperClassification

    first = Paper(id="drift_distinct_first", title="First drift paper", year=2024)
    first.classification = PaperClassification(
        id="drift_distinct_first_cls",
        label="CORE_RELEVANT",
        confidence=0.9,
        matched_topics=[
            {"topic_id": "topic-a", "name": "Topic A", "score": 0.9},
            {"topic_id": "topic-a", "name": "Topic A", "score": 0.8},
            {"topic_id": "topic-b", "name": "Topic B", "score": 0.9},
        ],
        matched_people=[],
        matched_institutions=[],
        reasons=[],
        graph_signals=None,
    )
    second = Paper(id="drift_distinct_second", title="Second drift paper", year=2024)
    second.classification = PaperClassification(
        id="drift_distinct_second_cls",
        label="CORE_RELEVANT",
        confidence=0.9,
        matched_topics=[
            {"topic_id": "topic-b", "name": "Topic B", "score": 0.9}
        ],
        matched_people=[],
        matched_institutions=[],
        reasons=[],
        graph_signals=None,
    )
    session.add_all([first, second])
    session.commit()

    report = build_drift_report(
        session,
        PaperFilter(),
        drift_threshold=0.8,
        top_n_per_year=7,
    )

    year = report.per_year[0]
    topics = {topic.topic_id: topic for topic in year.top_topics}
    assert year.total_papers == 2
    assert topics["topic-a"].paper_count == 1
    assert topics["topic-a"].share == 0.5
    assert topics["topic-b"].paper_count == 2
    assert topics["topic-b"].share == 1.0
    assert report.audit["included_papers"] == 2
    assert report.audit["projection"] == {
        "drift_threshold": 0.8,
        "top_n_per_year": 7,
    }


def test_drift_top_n_ties_sort_by_stable_topic_id(session):
    from app.models import Paper, PaperClassification

    for topic_id in ("topic-b", "topic-a"):
        paper = Paper(id=f"drift_{topic_id}", title=topic_id, year=2024)
        paper.classification = PaperClassification(
            id=f"drift_{topic_id}_classification",
            label="CORE_RELEVANT",
            confidence=0.9,
            matched_topics=[
                {"topic_id": topic_id, "name": topic_id, "score": 0.9}
            ],
            matched_people=[],
            matched_institutions=[],
            reasons=[],
            graph_signals=None,
        )
        session.add(paper)
    session.commit()

    report = build_drift_report(session, PaperFilter(), top_n_per_year=1)

    assert [topic.topic_id for topic in report.per_year[0].top_topics] == [
        "topic-a"
    ]


def test_drift_topic_alias_display_is_deterministic(session):
    from app.models import Paper, PaperClassification

    for index, name in enumerate(("Zulu Name", "Alpha Name")):
        paper = Paper(id=f"drift_alias_{index}", title=name, year=2024)
        paper.classification = PaperClassification(
            id=f"drift_alias_{index}_classification",
            label="CORE_RELEVANT",
            confidence=0.9,
            matched_topics=[
                {"topic_id": "topic-alias", "name": name, "score": 0.9}
            ],
            matched_people=[],
            matched_institutions=[],
            reasons=[],
            graph_signals=None,
        )
        session.add(paper)
    session.commit()

    report = build_drift_report(session, PaperFilter())

    assert report.per_year[0].top_topics[0].name == "Alpha Name"
