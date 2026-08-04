from __future__ import annotations

import networkx as nx

from app.models import (
    AcCorePaper,
    Author,
    Institution,
    Paper,
    PaperAuthor,
    PaperReference,
)
from app.services.network_service import build_coauthor_graph, graph_to_payload
from app.services.node_importance_service import AUTHOR_DIMENSIONS, compute_author_importance


def test_author_importance_components_sum_to_score():
    result = compute_author_importance(
        metrics={
            "ac_proximity": 0.8,
            "relationship_strength": 0.6,
            "excess_centrality": 0.5,
            "cross_sdl_diversity": 0.7,
            "citation_affinity": 0.0,
            "recency": 0.3,
        },
        profile="bridge_builders",
    )

    total = round(
        sum(c["contribution"] for c in result.components.values()),
        4,
    )
    assert result.score == total
    assert [axis["key"] for axis in result.radar_axes] == AUTHOR_DIMENSIONS
    assert result.explanation


def test_author_importance_weight_override_changes_score():
    metrics = {
        "ac_proximity": 0.1,
        "relationship_strength": 0.1,
        "excess_centrality": 0.1,
        "cross_sdl_diversity": 0.1,
        "citation_affinity": 0.0,
        "recency": 1.0,
    }

    default = compute_author_importance(metrics=metrics, profile="bridge_builders")
    custom = compute_author_importance(
        metrics=metrics,
        profile="bridge_builders",
        weights_override={"recency": 1.0},
    )

    assert custom.score > default.score
    assert custom.weights["recency"] > default.weights["recency"]


def test_network_payload_exposes_explainable_importance(session):
    inst_ac = Institution(
        id="inst_ac",
        canonical_name="AC",
        aliases=[],
        normalized_aliases=[],
        is_partner=True,
    )
    inst_ext = Institution(
        id="inst_ext",
        canonical_name="External",
        aliases=[],
        normalized_aliases=[],
    )
    ac = Author(
        id="a_ac",
        canonical_name="AC PI",
        normalized_name="ac pi",
        is_ac_member=True,
        institution=inst_ac,
    )
    bridge = Author(
        id="a_bridge",
        canonical_name="Bridge Author",
        normalized_name="bridge author",
        institution=inst_ext,
    )
    p1 = Paper(id="p_bridge_1", title="SDL one", year=2025, sdl_tags=["sdl-1"])
    p2 = Paper(id="p_bridge_2", title="SDL two", year=2026, sdl_tags=["sdl-2"])
    p1.authors = [
        PaperAuthor(author=ac, author_order=1),
        PaperAuthor(author=bridge, author_order=2),
    ]
    p2.authors = [
        PaperAuthor(author=bridge, author_order=1),
    ]
    session.add_all([inst_ac, inst_ext, ac, bridge, p1, p2])
    session.commit()

    payload = graph_to_payload(
        build_coauthor_graph(session),
        importance_profile="bridge_builders",
    )

    bridge_node = next(n for n in payload["nodes"] if n["id"] == "a_bridge")
    assert bridge_node["importance_profile"] == "bridge_builders"
    assert set(bridge_node["importance_components"]) == set(AUTHOR_DIMENSIONS)
    assert [axis["key"] for axis in bridge_node["importance_radar_axes"]] == AUTHOR_DIMENSIONS
    assert 0.0 <= bridge_node["importance_score"] <= 1.0
    assert bridge_node["importance_explanation"]


def test_citation_affinity_counts_distinct_filtered_papers(session):
    author = Author(
        id="citation-affinity-author",
        canonical_name="Citation Affinity Author",
        normalized_name="citation affinity author",
    )
    cited_core = AcCorePaper(
        id="citation-affinity-core",
        title="Curated AC core",
    )
    citing = Paper(id="citation-affinity-p1", title="Cites AC core", year=2025)
    other = Paper(id="citation-affinity-p2", title="Does not cite AC core", year=2025)
    citing.authors.append(PaperAuthor(author=author, author_order=0))
    other.authors.append(PaperAuthor(author=author, author_order=0))
    session.add_all([author, cited_core, citing, other])
    session.flush()
    session.add_all(
        [
            PaperReference(
                id="citation-affinity-ref-1",
                citing_paper_id=citing.id,
                cited_ac_core_id=cited_core.id,
                raw_text="First parser match",
            ),
            PaperReference(
                id="citation-affinity-ref-2",
                citing_paper_id=citing.id,
                cited_ac_core_id=cited_core.id,
                raw_text="Duplicate parser match",
            ),
        ]
    )
    session.commit()

    payload = graph_to_payload(
        build_coauthor_graph(session),
        importance_profile="ac_attribution",
    )
    node = next(item for item in payload["nodes"] if item["id"] == author.id)

    assert node["paper_count"] == 2
    assert node["ac_core_citing_paper_count"] == 1
    assert node["citation_affinity"] == 0.5
    assert node["reference_evidence_paper_count"] == 1
    assert node["citation_reference_coverage"] == 0.5
    assert node["importance_components"]["citation_affinity"]["value"] == 0.5


def test_importance_rank_has_stable_author_id_tie_breaker():
    graph = nx.Graph()
    for author_id in ["z-author", "a-author", "m-author"]:
        graph.add_node(
            author_id,
            label=author_id,
            is_ac_member=False,
            paper_count=1,
            corpus_paper_count=1,
        )

    payload = graph_to_payload(graph)
    ranks = {node["id"]: node["importance_rank"] for node in payload["nodes"]}

    assert ranks == {"z-author": 3, "a-author": 1, "m-author": 2}
