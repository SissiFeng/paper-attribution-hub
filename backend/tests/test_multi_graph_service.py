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


def test_stage1_institution_graph_uses_fulltext_affiliation_mentions(
    session,
    monkeypatch,
):
    from app.config import settings
    from app.models import Paper, PaperEntity
    from app.services.multi_graph import MultiGraphFilter, build_multi_graph

    monkeypatch.setattr(settings, "sdl_stage1_only", True)
    papers = [
        Paper(
            id="stage1_inst_paper_1",
            title="Stage 1 institution one",
            full_text_available=True,
        ),
        Paper(
            id="stage1_inst_paper_2",
            title="Stage 1 institution two",
            full_text_available=True,
        ),
    ]
    session.add_all(papers)
    session.flush()
    session.add_all(
        [
            PaperEntity(
                id="stage1_uoft_1",
                paper_id=papers[0].id,
                entity_type="institution",
                name="University of Toronto",
                normalized_name="University of Toronto",
                confidence=0.95,
                extractor="frontmatter_affiliation_v1",
            ),
            PaperEntity(
                id="stage1_ubc_1",
                paper_id=papers[0].id,
                entity_type="institution",
                name="University of British Columbia",
                normalized_name="University of British Columbia",
                confidence=0.91,
                extractor="frontmatter_affiliation_v1",
            ),
            PaperEntity(
                id="stage1_uoft_2",
                paper_id=papers[1].id,
                entity_type="institution",
                name="University of Toronto",
                normalized_name="University of Toronto",
                confidence=0.93,
                extractor="frontmatter_affiliation_v1",
            ),
        ]
    )
    session.commit()

    graph = build_multi_graph(
        session,
        MultiGraphFilter(
            node_types=["paper", "institution"],
            edge_types=["published_by"],
            group_by="by_institution",
        ),
    )

    institutions = {
        node.label: node for node in graph.nodes if node.type == "institution"
    }
    assert set(institutions) == {
        "University of British Columbia",
        "University of Toronto",
    }
    assert institutions["University of Toronto"].metadata["paper_count"] == 2
    assert institutions["University of Toronto"].metadata["source"] == (
        "zotero_tier1_markdown_frontmatter_candidate"
    )
    assert institutions["University of Toronto"].metadata[
        "resolution_status"
    ] == "candidate"
    assert institutions["University of Toronto"].metadata[
        "author_affiliation_resolved"
    ] is False
    assert len(graph.edges) == 3
    assert all(
        edge.metadata["relationship_scope"]
        == "paper_level_affiliation_mention"
        for edge in graph.edges
    )
    paper_nodes = [node for node in graph.nodes if node.type == "paper"]
    assert all(node.group is not None for node in paper_nodes)

    collaboration = build_multi_graph(
        session,
        MultiGraphFilter(
            node_types=["institution"],
            edge_types=["institution_collaboration"],
        ),
    )
    assert len(collaboration.edges) == 1
    assert collaboration.edges[0].weight == 1.0
    assert collaboration.edges[0].metadata["relationship_scope"] == (
        "paper_level_affiliation_cooccurrence"
    )


def test_stage1_graph_includes_all_extracted_entity_types_with_evidence(
    session,
    monkeypatch,
):
    from app.config import settings
    from app.models import Paper, PaperEntity
    from app.services.multi_graph import MultiGraphFilter, build_multi_graph

    monkeypatch.setattr(settings, "sdl_stage1_only", True)
    paper = Paper(
        id="stage1_scientific_entities",
        title="Tier 1 scientific entities",
        year=2025,
        full_text_available=True,
    )
    session.add(paper)
    session.flush()
    entity_specs = [
        ("method", "Bayesian optimization", "property_prediction"),
        ("material", "lithium metal", None),
        ("instrument", "mass spectrometer", None),
        ("software", "Python", None),
    ]
    for index, (entity_type, name, stage) in enumerate(entity_specs):
        session.add(
            PaperEntity(
                id=f"stage1_entity_{index}",
                paper_id=paper.id,
                entity_type=entity_type,
                name=name,
                normalized_name=name,
                evidence_chunk_id=None,
                section="Methods",
                confidence=0.86 + index / 100,
                extractor="vocabulary_v1",
                stage=stage,
                usage_snippet=f"Evidence for {name}.",
            )
        )
    session.commit()

    graph = build_multi_graph(
        session,
        MultiGraphFilter(
            node_types=[
                "paper",
                "method",
                "material",
                "instrument",
                "software",
            ],
            edge_types=[
                "uses_method",
                "mentions_material",
                "mentions_instrument",
                "mentions_software",
            ],
            group_by="by_entity_type",
        ),
    )

    assert {node.type for node in graph.nodes} == {
        "paper",
        "method",
        "material",
        "instrument",
        "software",
    }
    assert {edge.type for edge in graph.edges} == {
        "uses_method",
        "mentions_material",
        "mentions_instrument",
        "mentions_software",
    }
    assert all(node.group == f"entity-type:{node.type}" for node in graph.nodes)
    method = next(node for node in graph.nodes if node.type == "method")
    assert method.metadata["stage_counts"] == {"property_prediction": 1}
    material_edge = next(
        edge for edge in graph.edges if edge.type == "mentions_material"
    )
    assert material_edge.metadata["paper_id"] == paper.id
    assert material_edge.metadata["section"] == "Methods"
    assert material_edge.metadata["usage_snippet"] == (
        "Evidence for lithium metal."
    )
    assert material_edge.metadata["relationship_scope"] == (
        "paper_level_fulltext_entity_mention"
    )
    assert "material" in graph.available_node_types
    assert "mentions_material" in graph.available_edge_types
    assert "by_entity_type" in graph.available_group_keys


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


def test_top_n_caps_entities_without_removing_tier1_paper_nodes(session):
    from app.models import Author, Paper, PaperAuthor
    from app.services.multi_graph import MultiGraphFilter, build_multi_graph

    author = Author(
        id="top_n_author",
        canonical_name="Top N Author",
        aliases=[],
        normalized_name="top n author",
    )
    connected = Paper(id="top_n_connected", title="Connected Tier 1 paper")
    connected.authors.append(PaperAuthor(author=author, author_order=0))
    isolated = Paper(id="top_n_isolated", title="Isolated Tier 1 paper")
    session.add_all([connected, isolated])
    session.commit()

    graph = build_multi_graph(
        session,
        MultiGraphFilter(
            node_types=["author", "paper"],
            edge_types=["authored"],
            top_n=1,
        ),
    )

    assert {node.id for node in graph.nodes if node.type == "paper"} == {
        "paper:top_n_connected",
        "paper:top_n_isolated",
    }
    assert graph.audit["projection"]["raw_node_counts_by_type"] == {
        "author": 1,
        "paper": 2,
    }
    assert graph.audit["projection"]["visible_node_counts_by_type"] == {
        "author": 1,
        "paper": 2,
    }


def test_author_graph_keeps_first_four_and_last_listed_without_claiming_corresponding(
    session,
):
    from app.models import Author, Paper, PaperAuthor
    from app.services.multi_graph import MultiGraphFilter, build_multi_graph

    authors = [
        Author(
            id=f"ordered-author-{index}",
            canonical_name=f"Ordered Author {index}",
            aliases=[],
            normalized_name=f"ordered author {index}",
        )
        for index in range(8)
    ]
    paper = Paper(id="ordered-author-paper", title="Ordered author paper")
    paper.authors.extend(
        PaperAuthor(author=author, author_order=index)
        for index, author in enumerate(authors)
    )
    session.add(paper)
    session.commit()

    graph = build_multi_graph(
        session,
        MultiGraphFilter(
            node_types=["author", "paper"],
            edge_types=["authored"],
        ),
    )

    author_nodes = {
        node.id: node for node in graph.nodes if node.type == "author"
    }
    assert set(author_nodes) == {
        "author:ordered-author-0",
        "author:ordered-author-1",
        "author:ordered-author-2",
        "author:ordered-author-3",
        "author:ordered-author-7",
    }
    edges_by_author = {
        edge.source: edge for edge in graph.edges if edge.type == "authored"
    }
    assert edges_by_author["author:ordered-author-0"].metadata[
        "author_position"
    ] == "first"
    assert edges_by_author["author:ordered-author-7"].metadata[
        "author_position"
    ] == "last_listed"
    assert all(
        edge.metadata["corresponding_author_confirmed"] is False
        and edge.metadata["corresponding_author_evidence_available"] is False
        for edge in edges_by_author.values()
    )
    assert author_nodes["author:ordered-author-7"].metadata[
        "last_listed_author_paper_count"
    ] == 1
    assert graph.audit["projection"]["raw_node_counts_by_type"] == {
        "author": 5,
        "paper": 1,
    }


def test_author_graph_prefers_pdf_confirmed_corresponding_author_over_last_listed(
    session,
):
    from app.models import Author, Paper, PaperAuthor
    from app.services.multi_graph import MultiGraphFilter, build_multi_graph

    authors = [
        Author(
            id=f"confirmed-author-{index}",
            canonical_name=f"Confirmed Author {index}",
            aliases=[],
            normalized_name=f"confirmed author {index}",
        )
        for index in range(8)
    ]
    paper = Paper(
        id="confirmed-author-paper",
        title="Confirmed corresponding author",
        raw_metadata={
            "corresponding_author_evidence": {
                "extractor": "pdf_frontmatter_corresponding_author_v1",
                "evidence_available": True,
                "authors": [
                    {
                        "author_id": "confirmed-author-6",
                        "author_name": "Confirmed Author 6",
                        "author_order": 6,
                    }
                ],
            }
        },
    )
    paper.authors.extend(
        PaperAuthor(author=author, author_order=index)
        for index, author in enumerate(authors)
    )
    session.add(paper)
    session.commit()

    graph = build_multi_graph(
        session,
        MultiGraphFilter(
            node_types=["author", "paper"],
            edge_types=["authored"],
        ),
    )

    author_ids = {
        node.id for node in graph.nodes if node.type == "author"
    }
    assert author_ids == {
        "author:confirmed-author-0",
        "author:confirmed-author-1",
        "author:confirmed-author-2",
        "author:confirmed-author-3",
        "author:confirmed-author-6",
    }
    corresponding_edge = next(
        edge
        for edge in graph.edges
        if edge.source == "author:confirmed-author-6"
    )
    assert corresponding_edge.metadata[
        "corresponding_author_confirmed"
    ] is True
    assert corresponding_edge.metadata[
        "corresponding_author_evidence_available"
    ] is True
    assert corresponding_edge.metadata[
        "corresponding_author_evidence_source"
    ] == "pdf_frontmatter_corresponding_author_v1"
    corresponding_node = next(
        node
        for node in graph.nodes
        if node.id == "author:confirmed-author-6"
    )
    assert corresponding_node.metadata[
        "corresponding_author_paper_count"
    ] == 1


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
    from tests.admin_client import AdminTestClient as TestClient

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
