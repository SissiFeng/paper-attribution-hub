from __future__ import annotations

import pytest

from app.models import Author, Institution, Paper, PaperAuthor
from app.services.network_service import build_coauthor_graph, graph_to_payload


def test_network_payload_exposes_normalized_bridge_score(session):
    inst_ac = Institution(id="inst_ac", canonical_name="AC", aliases=[], normalized_aliases=[], is_partner=True)
    inst_ext = Institution(id="inst_ext", canonical_name="External", aliases=[], normalized_aliases=[])
    ac = Author(id="a_ac", canonical_name="AC PI", normalized_name="ac pi", is_ac_member=True, institution=inst_ac)
    bridge = Author(id="a_bridge", canonical_name="Bridge Author", normalized_name="bridge author", institution=inst_ext)
    other = Author(id="a_other", canonical_name="Other Author", normalized_name="other author", institution=inst_ext)
    p1 = Paper(id="p_bridge_1", title="SDL one", sdl_tags=["sdl-1"])
    p2 = Paper(id="p_bridge_2", title="SDL two", sdl_tags=["sdl-2"])
    p1.authors = [
        PaperAuthor(author=ac, author_order=1),
        PaperAuthor(author=bridge, author_order=2),
    ]
    p2.authors = [
        PaperAuthor(author=bridge, author_order=1),
        PaperAuthor(author=other, author_order=2),
    ]
    session.add_all([inst_ac, inst_ext, ac, bridge, other, p1, p2])
    session.commit()

    payload = graph_to_payload(build_coauthor_graph(session))

    bridge_node = next(n for n in payload["nodes"] if n["id"] == "a_bridge")
    assert bridge_node["cross_sdl_diversity"] > 0
    assert bridge_node["bridge_score"] > 0


def test_coauthor_endpoint_filters_nodes_and_audits_projection(session):
    from tests.admin_client import AdminTestClient as TestClient

    from app.main import app

    inst = Institution(
        id="network_filter_inst",
        canonical_name="Network Filter University",
        aliases=[],
        normalized_aliases=[],
    )
    frequent = Author(
        id="network_filter_frequent",
        canonical_name="Frequent Researcher",
        normalized_name="frequent researcher",
        institution=inst,
    )
    occasional = Author(
        id="network_filter_occasional",
        canonical_name="Occasional Researcher",
        normalized_name="occasional researcher",
        institution=inst,
    )
    for index in range(2):
        paper = Paper(id=f"network-filter-paper-{index}", title="Network filter")
        paper.authors.append(PaperAuthor(author=frequent, author_order=0))
        if index == 0:
            paper.authors.append(PaperAuthor(author=occasional, author_order=1))
        session.add(paper)
    session.commit()

    client = TestClient(app)
    baseline = client.get(
        "/network/coauthors",
        params={"only_relevant": False},
    )
    response = client.get(
        "/network/coauthors",
        params={
            "only_relevant": False,
            "min_papers": 2,
            "node_search": "Frequent",
            "node_institution_ids": inst.id,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert [node["id"] for node in body["nodes"]] == [frequent.id]
    assert body["audit"]["projection"]["min_papers"] == 2
    assert body["audit"]["projection"]["node_search"] == "Frequent"
    assert body["audit"]["projection"]["node_institution_ids"] == [inst.id]
    assert body["audit"]["algorithm"] == "coauthor_collaboration_network.v3"
    assert body["audit"]["projection"]["projection_applied_after_scoring"] is True
    assert body["audit"]["projection"]["score_universe_node_count"] == 2

    baseline_node = next(
        node for node in baseline.json()["nodes"] if node["id"] == frequent.id
    )
    projected_node = body["nodes"][0]
    assert projected_node["ppr_score"] == baseline_node["ppr_score"]
    assert projected_node["c_norm"] == baseline_node["c_norm"]
    assert projected_node["importance_score"] == baseline_node["importance_score"]
    assert (
        projected_node["importance_components"]
        == baseline_node["importance_components"]
    )


def test_coauthor_endpoint_distinguishes_filtered_and_corpus_paper_counts(session):
    from tests.admin_client import AdminTestClient as TestClient

    from app.main import app

    author = Author(
        id="paper-count-scope-author",
        canonical_name="Paper Count Scope Author",
        normalized_name="paper count scope author",
    )
    older = Paper(id="paper-count-scope-old", title="Older paper", year=2020)
    current = Paper(id="paper-count-scope-current", title="Current paper", year=2026)
    older.authors.append(PaperAuthor(author=author, author_order=0))
    current.authors.append(PaperAuthor(author=author, author_order=0))
    session.add_all([author, older, current])
    session.commit()

    response = TestClient(app).get(
        "/network/coauthors",
        params={
            "only_relevant": False,
            "year_from": 2026,
            "node_search": "Paper Count Scope",
        },
    )

    assert response.status_code == 200
    node = response.json()["nodes"][0]
    assert node["paper_count"] == 1
    assert node["corpus_paper_count"] == 2
    assert response.json()["audit"]["projection"]["score_universe_paper_count"] == 1
    definitions = response.json()["audit"]["metric_definitions"]
    assert "exact paper filter" in definitions["node_paper_count"]
    assert "display context only" in definitions["node_corpus_paper_count"]


@pytest.mark.parametrize(
    "query",
    [
        {"importance_profile": "made_up"},
        {"importance_weights": "unknown:1"},
        {"importance_weights": "recency:not-a-number"},
        {"importance_weights": "recency:nan"},
        {"importance_weights": "recency:-1"},
        {"importance_weights": "recency:0"},
        {"importance_weights": "recency"},
        {"importance_weights": "recency:1,recency:2"},
    ],
)
def test_coauthor_endpoint_rejects_invalid_importance_configuration(session, query):
    from tests.admin_client import AdminTestClient as TestClient

    from app.main import app

    response = TestClient(app).get(
        "/network/coauthors",
        params={"only_relevant": False, **query},
    )

    assert response.status_code == 422


def test_coauthor_audit_records_effective_normalized_weights(session):
    from tests.admin_client import AdminTestClient as TestClient

    from app.main import app

    response = TestClient(app).get(
        "/network/coauthors",
        params={
            "only_relevant": False,
            "importance_profile": "bridge_builders",
            "importance_weights": "ac_proximity:2,recency:2",
        },
    )

    assert response.status_code == 200
    projection = response.json()["audit"]["projection"]
    assert sum(projection["importance_weights"].values()) == pytest.approx(1.0)
    assert projection["score_formula"].startswith("importance_score = sum")
    assert projection["recency_as_of_year"] >= 2026


def test_coauthor_profile_changes_projection_not_evidence_scope(session):
    from tests.admin_client import AdminTestClient as TestClient

    from app.main import app

    client = TestClient(app)
    bridge = client.get(
        "/network/coauthors",
        params={"only_relevant": False, "importance_profile": "bridge_builders"},
    ).json()["audit"]
    emerging = client.get(
        "/network/coauthors",
        params={
            "only_relevant": False,
            "importance_profile": "emerging_connectors",
        },
    ).json()["audit"]

    assert bridge["filter_fingerprint"] == emerging["filter_fingerprint"]
    assert bridge["paper_set_sha256"] == emerging["paper_set_sha256"]
    assert bridge["projection_fingerprint"] != emerging["projection_fingerprint"]
