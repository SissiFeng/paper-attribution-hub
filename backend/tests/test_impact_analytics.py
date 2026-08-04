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


def test_impact_emerging_first_year_ignores_only_temporal_bounds(session):
    from app.models import Author, Institution, Paper, PaperAuthor

    institution = Institution(
        id="established_institution",
        canonical_name="Established Institution",
        aliases=[],
        normalized_aliases=[],
    )
    author = Author(
        id="established_author",
        canonical_name="Established Author",
        aliases=[],
        normalized_name="established author",
        institution=institution,
    )
    current = Paper(id="established_2024", title="Current work", year=2024)
    current.authors.append(PaperAuthor(author=author, author_order=0))
    session.add(current)
    session.commit()

    filt = PaperFilter(year_from=2024, year_to=2024)
    before = build_impact_report(session, filt)
    before_history = before.audit["dependencies"]["emerging_history"]
    assert "established_institution" in {
        entity.id for entity in before.emerging_institutions
    }
    assert before_history["filter"]["year_from"] is None
    assert before_history["filter"]["year_to"] is None

    older = Paper(id="established_2020", title="Older work", year=2020)
    older.authors.append(PaperAuthor(author=author, author_order=0))
    session.add(older)
    session.commit()

    after = build_impact_report(session, filt)
    after_history = after.audit["dependencies"]["emerging_history"]

    assert "established_institution" not in {
        entity.id for entity in after.emerging_institutions
    }
    assert "established_author" not in {
        entity.id for entity in after.emerging_authors
    }
    assert before.audit["paper_set_sha256"] == after.audit["paper_set_sha256"]
    assert before_history["paper_set_sha256"] != after_history["paper_set_sha256"]
    assert after.audit["included_papers"] == 1
    assert after.audit["algorithm"] == "research_impact.v4"


def test_impact_institution_support_counts_distinct_papers(session):
    from app.models import Author, Institution, Paper, PaperAuthor

    institution = Institution(
        id="multi_author_institution",
        canonical_name="Multi-author Institution",
        aliases=[],
        normalized_aliases=[],
    )
    authors = [
        Author(
            id=f"multi_author_{index}",
            canonical_name=f"Multi Author {index}",
            aliases=[],
            normalized_name=f"multi author {index}",
            institution=institution,
        )
        for index in range(3)
    ]
    paper = Paper(id="multi_author_paper", title="One shared paper", year=2024)
    paper.authors.extend(
        PaperAuthor(author=author, author_order=index)
        for index, author in enumerate(authors)
    )
    session.add(paper)
    session.commit()

    report = build_impact_report(session, PaperFilter(year_from=2024, year_to=2024))

    entity = next(
        item
        for item in report.emerging_institutions
        if item.id == "multi_author_institution"
    )
    assert entity.paper_count == 1


def test_impact_themes_use_stable_topic_identity_and_tie_order(session):
    from app.models import Paper, PaperClassification

    def add_paper(paper_id: str, year: int, topic_id: str, name: str) -> None:
        paper = Paper(id=paper_id, title=paper_id, year=year)
        paper.classification = PaperClassification(
            id=f"{paper_id}_classification",
            label="CORE_RELEVANT",
            confidence=0.9,
            matched_topics=[
                {
                    "topic_id": topic_id,
                    "name": name,
                    "score": 0.9,
                    "is_core": True,
                }
            ],
            matched_people=[],
            matched_institutions=[],
            reasons=[],
            graph_signals=None,
        )
        session.add(paper)

    add_paper("same_old", 2023, "same-topic", "Old Name")
    add_paper("same_new", 2024, "same-topic", "Renamed")
    for topic_id in ("topic-b", "topic-a"):
        add_paper(f"{topic_id}_old", 2023, topic_id, topic_id)
        add_paper(f"{topic_id}_new", 2024, topic_id, topic_id)
    session.commit()

    first = build_impact_report(
        session, PaperFilter(year_from=2023, year_to=2024)
    )
    second = build_impact_report(
        session, PaperFilter(year_from=2023, year_to=2024)
    )

    assert [theme.topic_id for theme in first.top_growing_themes] == [
        "same-topic",
        "topic-a",
        "topic-b",
    ]
    assert [theme.topic_id for theme in second.top_growing_themes] == [
        "same-topic",
        "topic-a",
        "topic-b",
    ]
    renamed = first.top_growing_themes[0]
    assert renamed.name == "Old Name"
    assert renamed.value_then == 1
    assert renamed.value_now == 1
    assert renamed.delta_pct == 0.0


def test_impact_normalizes_external_citations_by_field_year_and_audits_baseline(
    session,
):
    from datetime import UTC, datetime

    from app.models import Author, Institution, Paper, PaperAuthor

    institution = Institution(
        id="citation-index-inst",
        canonical_name="Citation Index Lab",
        aliases=[],
        normalized_aliases=[],
    )
    author = Author(
        id="citation-index-author",
        canonical_name="Citation Index Author",
        aliases=[],
        normalized_name="citation index author",
        institution=institution,
    )
    now = datetime(2026, 8, 2, tzinfo=UTC)
    selected = Paper(
        id="citation-index-selected",
        title="Selected citations",
        year=2024,
        research_tags=["Chemistry"],
        citation_count=20,
        citation_count_source="openalex",
        citation_count_updated_at=now,
    )
    selected.authors.append(PaperAuthor(author=author, author_order=0))
    baseline = Paper(
        id="citation-index-baseline",
        title="Baseline citations",
        year=2024,
        research_tags=["Chemistry"],
        citation_count=0,
        citation_count_source="openalex",
        citation_count_updated_at=now,
    )
    session.add_all([selected, baseline])
    session.commit()

    report = build_impact_report(
        session,
        PaperFilter(institution_ids=[institution.id]),
    )
    metric = report.normalized_citation_impact

    assert metric.normalized_index == 2.0
    assert metric.covered_papers == 1
    assert metric.total_papers == 1
    assert metric.coverage == 1.0
    assert metric.source_breakdown == {"openalex": 1}
    assert metric.by_institution[0].normalized_index == 2.0
    dependency = report.audit["dependencies"]["citation_baseline"]
    assert dependency["included_papers"] == 2
    assert dependency["snapshot_coverage"]["covered_papers"] == 2
    assert dependency["snapshot_coverage"]["covered_paper_set_sha256"]
