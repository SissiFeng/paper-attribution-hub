def test_multi_graph_uses_keyword_topics_when_classification_topics_missing(session):
    from app.models import Author, Institution, Paper, PaperAuthor, PaperClassification
    from app.services.filter_spec import PaperFilter
    from app.services.multi_graph import MultiGraphFilter, build_multi_graph

    inst = Institution(
        id="inst_ac",
        canonical_name="Acceleration Consortium",
        aliases=[],
        normalized_aliases=[],
        is_partner=True,
    )
    author = Author(
        id="auth_ac",
        canonical_name="AC Researcher",
        aliases=[],
        normalized_name="ac researcher",
        institution=inst,
        is_ac_member=True,
    )
    paper = Paper(
        id="p_ac",
        title="Closed-loop battery electrolyte discovery",
        year=2024,
        provenance="scopus_batch",
        keywords=["closed-loop optimization", "battery electrolyte"],
    )
    paper.authors.append(PaperAuthor(author=author, author_order=0))
    paper.classification = PaperClassification(
        id="cls_ac",
        label="CORE_RELEVANT",
        confidence=0.91,
        matched_topics=None,
        matched_people=[],
        matched_institutions=[],
        reasons=[],
        graph_signals=None,
    )
    session.add(paper)
    session.commit()

    graph = build_multi_graph(
        session,
        MultiGraphFilter(
            paper_filter=PaperFilter(labels=["CORE_RELEVANT"], year_from=2021, year_to=2026),
            node_types=["paper", "topic"],
            edge_types=["belongs_to_topic"],
        ),
    )

    topic_nodes = [n for n in graph.nodes if n.type == "topic"]
    assert {n.label for n in topic_nodes} == {
        "closed-loop optimization",
        "battery electrolyte",
    }
    assert len(graph.edges) == 2


def test_single_type_networks_and_country_projection_are_supported(session):
    from app.models import Author, Institution, Paper, PaperAuthor
    from app.services.multi_graph import MultiGraphFilter, build_multi_graph

    canada = Institution(
        id="inst_canada",
        canonical_name="Canadian Lab",
        aliases=[],
        normalized_aliases=[],
        country="Canada",
        is_partner=True,
    )
    japan = Institution(
        id="inst_japan",
        canonical_name="Japanese Lab",
        aliases=[],
        normalized_aliases=[],
        country="Japan",
        is_partner=False,
    )
    first = Author(
        id="author_canada",
        canonical_name="Canada Author",
        aliases=[],
        normalized_name="canada author",
        institution=canada,
    )
    second = Author(
        id="author_japan",
        canonical_name="Japan Author",
        aliases=[],
        normalized_name="japan author",
        institution=japan,
    )
    paper = Paper(id="paper_international", title="International SDL", year=2025)
    paper.authors.extend(
        [
            PaperAuthor(author=first, author_order=0),
            PaperAuthor(author=second, author_order=1),
        ]
    )
    session.add(paper)
    session.commit()

    authors = build_multi_graph(
        session,
        MultiGraphFilter(
            node_types=["author"],
            edge_types=["coauthored"],
        ),
    )
    institutions = build_multi_graph(
        session,
        MultiGraphFilter(
            node_types=["institution"],
            edge_types=["institution_collaboration"],
        ),
    )
    countries = build_multi_graph(
        session,
        MultiGraphFilter(
            node_types=["country"],
            edge_types=["country_collaboration"],
        ),
    )
    grouped = build_multi_graph(
        session,
        MultiGraphFilter(
            node_types=["author", "institution", "country"],
            edge_types=["affiliated_with"],
            group_by="by_country",
        ),
    )

    assert {node.type for node in authors.nodes} == {"author"}
    assert {edge.type for edge in authors.edges} == {"coauthored"}
    assert {node.type for node in institutions.nodes} == {"institution"}
    assert {edge.type for edge in institutions.edges} == {
        "institution_collaboration"
    }
    assert {node.label for node in countries.nodes} == {"Canada", "Japan"}
    assert len(countries.edges) == 1
    assert countries.edges[0].weight == 1.0
    assert countries.audit["included_papers"] == 1
    groups = {node.id: node.group for node in grouped.nodes}
    assert groups["country:Canada"] == "country:Canada"
    assert groups["institution:inst_canada"] == "country:Canada"
    assert groups["author:author_canada"] == "country:Canada"


def test_graph_thresholds_remove_low_support_and_dangling_nodes(session):
    from app.models import Author, Paper, PaperAuthor
    from app.services.multi_graph import MultiGraphFilter, build_multi_graph

    prolific = Author(
        id="author_prolific",
        canonical_name="Prolific",
        aliases=[],
        normalized_name="prolific",
    )
    occasional = Author(
        id="author_occasional",
        canonical_name="Occasional",
        aliases=[],
        normalized_name="occasional",
    )
    for index in range(2):
        paper = Paper(id=f"threshold_{index}", title=f"Threshold {index}", year=2025)
        paper.authors.append(PaperAuthor(author=prolific, author_order=0))
        if index == 0:
            paper.authors.append(PaperAuthor(author=occasional, author_order=1))
        session.add(paper)
    session.commit()

    graph = build_multi_graph(
        session,
        MultiGraphFilter(
            node_types=["author"],
            edge_types=["coauthored"],
            min_papers=2,
            top_n=1,
        ),
    )

    assert [node.label for node in graph.nodes] == ["Prolific"]
    assert graph.edges == []
    assert graph.audit["graph_filter"]["min_papers"] == 2


def test_minimum_degree_is_applied_as_an_iterative_core(session):
    from app.models import Author, Paper, PaperAuthor
    from app.services.multi_graph import MultiGraphFilter, build_multi_graph

    authors = [
        Author(
            id=f"degree_author_{index}",
            canonical_name=f"Degree {index}",
            aliases=[],
            normalized_name=f"degree {index}",
        )
        for index in range(3)
    ]
    first = Paper(id="degree_paper_first", title="Degree first")
    first.authors.extend(
        [
            PaperAuthor(author=authors[0], author_order=0),
            PaperAuthor(author=authors[1], author_order=1),
        ]
    )
    second = Paper(id="degree_paper_second", title="Degree second")
    second.authors.extend(
        [
            PaperAuthor(author=authors[1], author_order=0),
            PaperAuthor(author=authors[2], author_order=1),
        ]
    )
    session.add_all([first, second])
    session.commit()

    graph = build_multi_graph(
        session,
        MultiGraphFilter(
            node_types=["author"],
            edge_types=["coauthored"],
            min_degree=2,
        ),
    )

    assert graph.nodes == []
    assert graph.edges == []


def test_multi_graph_endpoint_rejects_unknown_axes_and_deduplicates_valid_axes(
    session,
):
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    invalid = client.get(
        "/analytics/multi-graph",
        params=[
            ("node_types", "paper"),
            ("node_types", "hostile"),
            ("edge_types", "cites"),
            ("edge_types", "invented"),
            ("group_by", "unknown"),
        ],
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"] == {
        "invalid_node_types": ["hostile"],
        "invalid_edge_types": ["invented"],
        "invalid_group_by": "unknown",
    }

    valid = client.get(
        "/analytics/multi-graph",
        params=[
            ("node_types", "paper"),
            ("node_types", "paper"),
            ("edge_types", "cites"),
            ("edge_types", "cites"),
            ("group_by", "none"),
        ],
    )
    assert valid.status_code == 200
    projection = valid.json()["audit"]["projection"]
    assert projection["node_types"] == ["paper"]
    assert projection["edge_types"] == ["cites"]
    assert valid.json()["audit"]["projection_fingerprint"]


def test_repeated_entities_count_distinct_papers_and_emit_one_edge(session):
    from app.models import Paper, PaperClassification, PaperProposition
    from app.services.multi_graph import MultiGraphFilter, build_multi_graph

    paper = Paper(id="duplicate_entity_paper", title="Duplicate entities")
    paper.classification = PaperClassification(
        id="duplicate_entity_cls",
        label="CORE_RELEVANT",
        confidence=0.9,
        matched_topics=[
            {"topic_id": "topic-duplicate", "name": "Duplicate", "score": 0.4},
            {"topic_id": "topic-duplicate", "name": "Duplicate", "score": 0.9},
        ],
        matched_people=[],
        matched_institutions=[],
        reasons=[],
        graph_signals=None,
    )
    propositions = [
        PaperProposition(
            id=f"duplicate_method_{index}",
            paper_id=paper.id,
            predicate="uses_method",
            object_value="Bayesian optimization",
            object_key="bayes-opt",
            claim_text="Uses Bayesian optimization.",
            confidence=confidence,
        )
        for index, confidence in enumerate((0.6, 0.8))
    ]
    session.add_all([paper, *propositions])
    session.commit()

    graph = build_multi_graph(
        session,
        MultiGraphFilter(
            node_types=["paper", "topic", "method"],
            edge_types=["belongs_to_topic", "uses_method"],
        ),
    )

    topic = next(node for node in graph.nodes if node.type == "topic")
    method = next(node for node in graph.nodes if node.type == "method")
    assert topic.metadata["paper_count"] == 1
    assert method.metadata["paper_count"] == 1
    topic_edges = [edge for edge in graph.edges if edge.type == "belongs_to_topic"]
    method_edges = [edge for edge in graph.edges if edge.type == "uses_method"]
    assert len(topic_edges) == 1 and topic_edges[0].weight == 0.9
    assert len(method_edges) == 1 and method_edges[0].weight == 0.8


def test_excluded_nodes_remove_incident_edges_and_are_audited(session):
    from app.models import Author, Paper, PaperAuthor
    from app.services.multi_graph import MultiGraphFilter, build_multi_graph

    authors = [
        Author(
            id=f"excluded-author-{index}",
            canonical_name=f"Excluded Author {index}",
            aliases=[],
            normalized_name=f"excluded author {index}",
        )
        for index in range(3)
    ]
    paper = Paper(id="excluded-node-paper", title="Excluded node paper")
    paper.authors.extend(
        PaperAuthor(author=author, author_order=index)
        for index, author in enumerate(authors)
    )
    session.add(paper)
    session.commit()

    graph = build_multi_graph(
        session,
        MultiGraphFilter(
            node_types=["author"],
            edge_types=["coauthored"],
            excluded_node_ids=["author:excluded-author-1"],
        ),
    )

    assert {node.id for node in graph.nodes} == {
        "author:excluded-author-0",
        "author:excluded-author-2",
    }
    assert all(
        "author:excluded-author-1" not in {edge.source, edge.target}
        for edge in graph.edges
    )
    assert graph.audit["projection"]["excluded_node_ids"] == [
        "author:excluded-author-1"
    ]
    assert graph.audit["projection"]["excluded_node_count"] == 1
