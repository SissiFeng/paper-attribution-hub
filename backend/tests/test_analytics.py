from app.services.analytics_service import (
    institution_network,
    institution_topic_label_sankey,
    label_breakdown,
    topic_over_time,
)
from app.services.filter_spec import PaperFilter


def _setup(session):
    from app.services.relevance_classifier import classify_all

    classify_all(session)


def test_sankey_has_three_layers(fulltext_seeded_session):
    _setup(fulltext_seeded_session)
    data = institution_topic_label_sankey(fulltext_seeded_session, PaperFilter())
    layers = {n.layer for n in data.nodes}
    assert {"institution", "topic", "label"} <= layers
    # Links should always flow inst → topic and topic → label.
    inst_to_topic = [
        l for l in data.links
        if l.source.startswith("inst:") and l.target.startswith("topic:")
    ]
    topic_to_label = [
        l for l in data.links
        if l.source.startswith("topic:") and l.target.startswith("label:")
    ]
    assert inst_to_topic
    assert topic_to_label


def test_timeline_by_topic_has_years(fulltext_seeded_session):
    _setup(fulltext_seeded_session)
    series = topic_over_time(fulltext_seeded_session, PaperFilter(), by="topic")
    assert series
    all_years = {y for s in series for y, _ in s.data}
    assert 2023 in all_years or 2024 in all_years


def test_timeline_by_label(fulltext_seeded_session):
    _setup(fulltext_seeded_session)
    series = topic_over_time(fulltext_seeded_session, PaperFilter(), by="label")
    series_names = {s.name for s in series}
    assert "CORE_RELEVANT" in series_names


def test_institution_network_partner_filter(fulltext_seeded_session):
    _setup(fulltext_seeded_session)
    nodes, edges = institution_network(
        fulltext_seeded_session, PaperFilter(partner_only=True)
    )
    assert nodes
    assert all(n.is_partner for n in nodes)
    # Edges only connect AC-partner institutions to each other in this view.
    assert all(
        any(n.id == e.source for n in nodes) and any(n.id == e.target for n in nodes)
        for e in edges
    )


def test_label_breakdown_respects_filter(fulltext_seeded_session):
    _setup(fulltext_seeded_session)
    all_counts = label_breakdown(fulltext_seeded_session, PaperFilter())
    filtered = label_breakdown(
        fulltext_seeded_session, PaperFilter(year_from=2024)
    )
    assert sum(filtered.values()) <= sum(all_counts.values())
