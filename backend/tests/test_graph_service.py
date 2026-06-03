"""Test the v0.3 graph signal computation against the seeded sample data."""
from app.services.graph_service import (
    build_citation_graph,
    build_institution_graph,
    compute_graph_signals,
)


def test_second_degree_detected_for_p011(fulltext_seeded_session):
    """P011 has Jane Doe, who appears on P001 with Aspuru-Guzik (AC member)."""
    signals = compute_graph_signals(fulltext_seeded_session)
    p011 = signals["P011"]
    assert p011.network_score > 0
    assert any(
        p.ac_author_name == "Alan Aspuru-Guzik" for p in p011.second_degree_paths
    )
    path_keys = {
        (p.via_author_id, p.ac_author_id, tuple(p.shared_papers))
        for p in p011.second_degree_paths
    }
    assert len(path_keys) == len(p011.second_degree_paths)


def test_p003_cites_ac_core(fulltext_seeded_session):
    signals = compute_graph_signals(fulltext_seeded_session)
    p003 = signals["P003"]
    assert p003.citation_score > 0
    cited_titles = {s.cited_ac_core_title for s in p003.citation_signals}
    assert any("ChemOS" in t for t in cited_titles)


def test_papers_with_ac_authors_get_network_score_1(fulltext_seeded_session):
    signals = compute_graph_signals(fulltext_seeded_session)
    # P001 has Aspuru-Guzik directly → network_score should be 1.0
    assert signals["P001"].network_score == 1.0


def test_papers_without_signal_score_zero(fulltext_seeded_session):
    signals = compute_graph_signals(fulltext_seeded_session)
    # P010 (climate review) has none of the signals.
    p010 = signals["P010"]
    assert p010.network_score == 0.0
    assert p010.citation_score == 0.0
    assert p010.second_degree_paths == []


def test_institution_graph_includes_uoft_edges(fulltext_seeded_session):
    g = build_institution_graph(fulltext_seeded_session)
    # UofT canonical name should be a node.
    uoft_nodes = [
        node_id for node_id, data in g.nodes(data=True)
        if data.get("label") == "University of Toronto"
    ]
    assert uoft_nodes


def test_citation_graph_has_ac_core_edges(fulltext_seeded_session):
    cg = build_citation_graph(fulltext_seeded_session)
    # At least one edge to an ac_core node from a corpus paper.
    ac_edges = [
        (u, v) for u, v, d in cg.edges(data=True) if d.get("kind") == "ac_core"
    ]
    assert ac_edges
