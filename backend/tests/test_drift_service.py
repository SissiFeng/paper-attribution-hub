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
