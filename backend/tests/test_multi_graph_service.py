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
