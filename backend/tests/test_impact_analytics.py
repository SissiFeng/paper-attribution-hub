"""Tests for v0.6 impact aggregations."""
from app.services.analytics_service import build_impact_report
from app.services.filter_spec import PaperFilter


def _setup(session):
    from app.services.relevance_classifier import classify_all

    classify_all(session)


def test_impact_yoy_attributed_counts_only_core_and_related(fulltext_seeded_session):
    _setup(fulltext_seeded_session)
    report = build_impact_report(fulltext_seeded_session, PaperFilter())
    pts = report.yoy_attributed.points
    assert pts
    total = sum(p.value for p in pts)
    # Sample data has 5 CORE + 1 RELATED -> 6 attributed.
    assert total == 6


def test_impact_yoy_by_label_separates_labels(fulltext_seeded_session):
    _setup(fulltext_seeded_session)
    report = build_impact_report(fulltext_seeded_session, PaperFilter())
    label_series = {s.name: s for s in report.yoy_by_label}
    assert "CORE_RELEVANT" in label_series
    assert "EXCLUDE" in label_series


def test_impact_window_filter_narrows_results(fulltext_seeded_session):
    _setup(fulltext_seeded_session)
    full = build_impact_report(fulltext_seeded_session, PaperFilter())
    windowed = build_impact_report(
        fulltext_seeded_session, PaperFilter(year_from=2024, year_to=2024)
    )
    full_total = sum(p.value for p in full.yoy_attributed.points)
    windowed_total = sum(p.value for p in windowed.yoy_attributed.points)
    assert windowed_total <= full_total
    assert windowed.window_from == 2024
    assert windowed.window_to == 2024


def test_impact_emerging_institutions_listed_within_window(fulltext_seeded_session):
    _setup(fulltext_seeded_session)
    report = build_impact_report(
        fulltext_seeded_session, PaperFilter(year_from=2024)
    )
    # Some emerging institutions should appear when restricting to >= 2024.
    assert report.emerging_institutions
    assert all(e.first_year >= 2024 for e in report.emerging_institutions)


def test_impact_top_growing_themes_returns_themes(fulltext_seeded_session):
    _setup(fulltext_seeded_session)
    report = build_impact_report(fulltext_seeded_session, PaperFilter())
    # Sample data has SDL papers in 2023-2024 -> some theme should surface.
    assert report.top_growing_themes
    assert all(t.name for t in report.top_growing_themes)
