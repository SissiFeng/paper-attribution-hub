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
        link
        for link in data.links
        if link.source.startswith("inst:") and link.target.startswith("topic:")
    ]
    topic_to_label = [
        link
        for link in data.links
        if link.source.startswith("topic:") and link.target.startswith("label:")
    ]
    assert inst_to_topic
    assert topic_to_label


def test_sankey_topic_label_counts_distinct_papers_across_affiliations(session):
    from app.models import (
        Author,
        Institution,
        Paper,
        PaperAuthor,
        PaperClassification,
    )

    institutions = [
        Institution(
            id=f"sankey_inst_{index}",
            canonical_name=f"Sankey Institution {index}",
            aliases=[],
            normalized_aliases=[],
        )
        for index in range(2)
    ]
    authors = [
        Author(
            id=f"sankey_author_{index}",
            canonical_name=f"Sankey Author {index}",
            aliases=[],
            normalized_name=f"sankey author {index}",
            institution=institution,
        )
        for index, institution in enumerate(institutions)
    ]
    paper = Paper(id="sankey_multi_affiliation", title="Sankey paper", year=2025)
    paper.authors.extend(
        PaperAuthor(author=author, author_order=index)
        for index, author in enumerate(authors)
    )
    paper.classification = PaperClassification(
        id="sankey_multi_affiliation_cls",
        label="CORE_RELEVANT",
        confidence=0.95,
        matched_topics=[
            {"topic_id": "topic-sankey", "name": "Sankey Topic", "score": 0.9}
        ],
        matched_people=[],
        matched_institutions=[],
        reasons=[],
        graph_signals=None,
    )
    session.add(paper)
    session.commit()

    data = institution_topic_label_sankey(session, PaperFilter())
    institution_links = [
        link for link in data.links if link.source.startswith("inst:")
    ]
    topic_label_links = [
        link for link in data.links if link.source == "topic:topic-sankey"
    ]

    assert len(institution_links) == 2
    assert {link.value for link in institution_links} == {1}
    assert len(topic_label_links) == 1
    assert topic_label_links[0].value == 1


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


def test_timeline_country_and_institution_use_distinct_filtered_papers(
    fulltext_seeded_session,
):
    _setup(fulltext_seeded_session)
    filt = PaperFilter(year_from=2024, year_to=2024)

    country = topic_over_time(
        fulltext_seeded_session,
        filt,
        by="country",
    )
    institution = topic_over_time(
        fulltext_seeded_session,
        filt,
        by="institution",
    )

    assert country
    assert institution
    assert all(year == 2024 for series in country for year, _ in series.data)
    assert all(
        year == 2024 for series in institution for year, _ in series.data
    )


def test_stage1_analytics_use_markdown_affiliation_entities(
    session,
    monkeypatch,
):
    from app.config import settings
    from app.models import Paper, PaperClassification, PaperEntity

    monkeypatch.setattr(settings, "sdl_stage1_only", True)
    papers = [
        Paper(id="stage1_analytics_1", title="Stage 1 one", year=2024),
        Paper(id="stage1_analytics_2", title="Stage 1 two", year=2025),
    ]
    for index, paper in enumerate(papers, start=1):
        paper.classification = PaperClassification(
            id=f"stage1_analytics_cls_{index}",
            label="SDL_FIELD_RELEVANT",
            confidence=0.9,
            matched_topics=[
                {
                    "topic_id": "self-driving-labs",
                    "name": "Self Driving Labs",
                    "score": 0.9,
                }
            ],
            matched_people=[],
            matched_institutions=[],
            reasons=[],
        )
    session.add_all(papers)
    session.flush()
    session.add_all(
        [
            PaperEntity(
                id="stage1_analytics_uoft_1",
                paper_id=papers[0].id,
                entity_type="institution",
                name="University of Toronto",
                normalized_name="University of Toronto",
                confidence=0.95,
            ),
            PaperEntity(
                id="stage1_analytics_ubc_1",
                paper_id=papers[0].id,
                entity_type="institution",
                name="University of British Columbia",
                normalized_name="University of British Columbia",
                confidence=0.95,
            ),
            PaperEntity(
                id="stage1_analytics_uoft_2",
                paper_id=papers[1].id,
                entity_type="institution",
                name="University of Toronto",
                normalized_name="University of Toronto",
                confidence=0.95,
            ),
        ]
    )
    session.commit()

    timeline = topic_over_time(session, PaperFilter(), by="institution")
    sankey = institution_topic_label_sankey(session, PaperFilter())
    nodes, edges = institution_network(session, PaperFilter())

    timeline_counts = {
        series.name: sum(count for _year, count in series.data)
        for series in timeline
    }
    assert timeline_counts["University of Toronto"] == 2
    assert {node.label for node in nodes} == {
        "University of British Columbia",
        "University of Toronto",
    }
    assert len(edges) == 1
    assert edges[0].weight == 1
    assert {node.layer for node in sankey.nodes} == {
        "institution",
        "topic",
        "label",
    }


def test_timeline_field_is_distinct_and_top_n_is_deterministic(session):
    from app.models import Paper, PaperClassification

    for index, fields in enumerate(
        (["Chemistry", "Chemistry"], ["Physics"], ["Chemistry"]),
        start=1,
    ):
        paper = Paper(
            id=f"timeline-field-{index}",
            title=f"Timeline field {index}",
            year=2025,
            research_tags=fields,
        )
        paper.classification = PaperClassification(
            id=f"timeline-field-cls-{index}",
            label="CORE_RELEVANT",
            confidence=0.9,
            matched_people=[],
            matched_institutions=[],
            matched_topics=[],
            reasons=[],
            graph_signals=None,
        )
        session.add(paper)
    session.commit()

    series = topic_over_time(
        session,
        PaperFilter(),
        by="field",
        top_n=1,
    )

    assert [(item.name, item.data) for item in series] == [
        ("Chemistry", [(2025, 2)])
    ]


def test_timeline_endpoint_audits_field_top_n(session):
    from tests.admin_client import AdminTestClient as TestClient

    from app.main import app
    from app.models import Paper, PaperClassification

    paper = Paper(
        id="timeline-field-api",
        title="Timeline field API",
        year=2025,
        research_tags=["Materials"],
    )
    paper.classification = PaperClassification(
        id="timeline-field-api-cls",
        label="CORE_RELEVANT",
        confidence=0.9,
        matched_people=[],
        matched_institutions=[],
        matched_topics=[],
        reasons=[],
        graph_signals=None,
    )
    session.add(paper)
    session.commit()

    response = TestClient(app).get(
        "/analytics/timeline",
        params={"by": "field", "top_n": 3, "labels": "CORE_RELEVANT"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["by"] == "field"
    assert body["top_n"] == 3
    assert body["audit"]["projection"] == {"by": "field", "top_n": 3}


def test_analysis_endpoints_expose_same_filter_audit(
    fulltext_seeded_session,
):
    from tests.admin_client import AdminTestClient as TestClient

    from app.main import app

    _setup(fulltext_seeded_session)
    client = TestClient(app)
    query = "year_from=2024&year_to=2024&labels=CORE_RELEVANT"

    scope = client.get(f"/analytics/scope?{query}").json()
    timeline = client.get(f"/analytics/timeline?by=country&{query}").json()
    network = client.get(f"/analytics/institution-network?{query}").json()
    geography = client.get(f"/analytics/geographic?{query}").json()
    sankey = client.get(f"/analytics/sankey?{query}").json()
    impact = client.get(f"/analytics/impact?{query}").json()
    drift = client.get(
        f"/analytics/drift?drift_threshold=0.8&top_n_per_year=7&{query}"
    ).json()
    graph = client.get(
        f"/analytics/multi-graph?node_types=country&"
        f"edge_types=country_collaboration&{query}"
    ).json()

    fingerprints = {
        scope["filter_fingerprint"],
        timeline["audit"]["filter_fingerprint"],
        network["audit"]["filter_fingerprint"],
        geography["audit"]["filter_fingerprint"],
        graph["audit"]["filter_fingerprint"],
        sankey["audit"]["filter_fingerprint"],
        impact["audit"]["filter_fingerprint"],
        drift["audit"]["filter_fingerprint"],
    }
    included_counts = {
        scope["included_papers"],
        timeline["audit"]["included_papers"],
        network["audit"]["included_papers"],
        geography["audit"]["included_papers"],
        graph["audit"]["included_papers"],
        sankey["audit"]["included_papers"],
        impact["audit"]["included_papers"],
        drift["audit"]["included_papers"],
    }

    assert len(fingerprints) == 1
    assert len(included_counts) == 1
    assert scope["metric_definitions"]
    assert scope["filter_semantics"]["between_dimensions"] == "AND"
    assert sankey["audit"]["projection"] == {
        "layers": ["institution", "label", "topic"],
        "top_institutions": 100,
        "top_topics": 50,
    }
    assert sankey["audit"]["projection_fingerprint"]
    assert impact["audit"]["algorithm"] == "research_impact.v4"
    assert "citation_baseline" in impact["audit"]["dependencies"]
    assert drift["audit"]["projection"] == {
        "drift_threshold": 0.8,
        "top_n_per_year": 7,
    }
    assert drift["audit"]["projection_fingerprint"]


def test_filter_options_are_persisted_and_typed(fulltext_seeded_session):
    from tests.admin_client import AdminTestClient as TestClient

    from app.main import app

    response = TestClient(app).get("/analytics/filter-options")

    assert response.status_code == 200
    body = response.json()
    assert body["years"] == sorted(body["years"])
    assert body["institutions"]
    assert all(
        {"id", "name", "country", "is_partner"} <= set(institution)
        for institution in body["institutions"]
    )


def test_geographic_collaboration_arcs_are_undirected(fulltext_seeded_session):
    from app.services.geographic_service import build_geographic_payload

    payload = build_geographic_payload(fulltext_seeded_session, PaperFilter())
    pairs = {(arc["from"], arc["to"]) for arc in payload["arcs"]}

    assert all((target, source) not in pairs for source, target in pairs)


def test_geographic_center_projection_keeps_only_incident_arcs(session):
    from app.models import Author, Institution, Paper, PaperAuthor
    from app.services.geographic_service import build_geographic_payload

    countries = ["Canada", "Japan", "Germany"]
    authors = []
    for index, country in enumerate(countries):
        institution = Institution(
            id=f"geo-center-inst-{index}",
            canonical_name=f"Geo Center {country}",
            aliases=[],
            normalized_aliases=[],
            country=country,
            is_partner=index == 0,
        )
        authors.append(
            Author(
                id=f"geo-center-author-{index}",
                canonical_name=f"Geo Center Author {index}",
                aliases=[],
                normalized_name=f"geo center author {index}",
                institution=institution,
            )
        )
    for index, pair in enumerate(((0, 1), (0, 2), (1, 2))):
        paper = Paper(id=f"geo-center-paper-{index}", title="Geo center")
        paper.authors.extend(
            PaperAuthor(author=authors[author_index], author_order=order)
            for order, author_index in enumerate(pair)
        )
        session.add(paper)
    session.commit()

    payload = build_geographic_payload(
        session,
        PaperFilter(),
        center_country="Japan",
    )

    assert payload["center_country"] == "Japan"
    assert all(
        "Japan" in {arc["from"], arc["to"]} for arc in payload["arcs"]
    )
    assert {tuple((arc["from"], arc["to"])) for arc in payload["arcs"]} == {
        ("Japan", "Canada"),
        ("Japan", "Germany"),
    }
    projection = payload["audit"]["projection"]
    assert projection["center_type"] == "country"
    assert projection["center_id"] == "Japan"
    assert projection["arc_scope"] == "all_center_incident_collaborations"


def _seed_center_growth(session):
    from app.models import Author, Institution, Paper, PaperAuthor

    institutions = {
        "uoft": Institution(
            id="geo-growth-uoft",
            canonical_name="University of Toronto",
            aliases=["UofT"],
            normalized_aliases=["uoft"],
            country="Canada",
            is_partner=True,
        ),
        "china": Institution(
            id="geo-growth-china",
            canonical_name="China Growth University",
            aliases=[],
            normalized_aliases=[],
            country="China",
        ),
        "japan": Institution(
            id="geo-growth-japan",
            canonical_name="Japan Growth University",
            aliases=[],
            normalized_aliases=[],
            country="Japan",
        ),
    }
    authors = {
        key: Author(
            id=f"geo-growth-author-{key}",
            canonical_name=f"Geo Growth Author {key}",
            normalized_name=f"geo growth author {key}",
            institution=institution,
        )
        for key, institution in institutions.items()
    }
    authors["japan_second"] = Author(
        id="geo-growth-author-japan-second",
        canonical_name="Geo Growth Author Japan Second",
        normalized_name="geo growth author japan second",
        institution=institutions["japan"],
    )

    papers = [
        ("geo-growth-2020", 2020, ["uoft", "china"]),
        ("geo-growth-2024", 2024, ["china", "japan"]),
        ("geo-growth-2024-solo", 2024, ["china"]),
        ("geo-growth-2025", 2025, ["uoft", "japan", "japan_second"]),
        ("geo-growth-2025-solo", 2025, ["uoft"]),
    ]
    for paper_id, year, author_keys in papers:
        paper = Paper(id=paper_id, title=paper_id, year=year)
        paper.authors.extend(
            PaperAuthor(author=authors[key], author_order=index)
            for index, key in enumerate(author_keys)
        )
        session.add(paper)
    session.commit()
    return institutions


def test_geographic_country_center_growth_includes_non_partner_connections(session):
    from app.services.geographic_service import build_geographic_payload

    _seed_center_growth(session)
    payload = build_geographic_payload(
        session,
        PaperFilter(year_from=2020, year_to=2024),
        center_type="country",
        center_id="China",
    )

    assert payload["center"] == {
        "type": "country",
        "id": "China",
        "name": "China",
        "country": "China",
        "paper_count": 3,
        "collaboration_paper_count": 2,
        "partner_count": 2,
        "first_year": 2020,
        "last_year": 2024,
        "missing_year_paper_count": 0,
    }
    assert {(arc["from"], arc["to"]) for arc in payload["arcs"]} == {
        ("China", "Canada"),
        ("China", "Japan"),
    }
    assert [point["year"] for point in payload["growth"]] == list(range(2020, 2025))
    assert payload["growth"][0]["collaboration_papers"] == 1
    assert payload["growth"][-1] == {
        "year": 2024,
        "center_papers": 2,
        "collaboration_papers": 1,
        "active_partners": 1,
        "cumulative_partners": 2,
        "cumulative_collaboration_papers": 2,
    }
    assert {partner["name"] for partner in payload["partners"]} == {
        "Canada",
        "Japan",
    }
    subsets = payload["audit"]["evidence_subsets"]
    assert subsets["center_papers"]["count"] == 3
    assert subsets["collaboration_papers"]["count"] == 2


def test_geographic_institution_center_growth_deduplicates_partner_authors(session):
    from app.services.geographic_service import build_geographic_payload

    institutions = _seed_center_growth(session)
    payload = build_geographic_payload(
        session,
        PaperFilter(year_from=2020, year_to=2025),
        center_type="institution",
        center_id=institutions["uoft"].id,
    )

    assert payload["center"]["name"] == "University of Toronto"
    assert payload["center"]["paper_count"] == 3
    assert payload["center"]["collaboration_paper_count"] == 2
    assert payload["center"]["partner_count"] == 2
    japan = next(
        partner for partner in payload["partners"] if partner["name"] == "Japan Growth University"
    )
    assert japan["paper_count"] == 1
    assert {(arc["from"], arc["to"], arc["weight"]) for arc in payload["arcs"]} == {
        ("Canada", "China", 1),
        ("Canada", "Japan", 1),
    }


def test_geographic_center_is_projection_not_paper_filter(session):
    from app.services.geographic_service import build_geographic_payload

    institutions = _seed_center_growth(session)
    filt = PaperFilter(year_from=2020, year_to=2025)
    country_payload = build_geographic_payload(
        session,
        filt,
        center_type="country",
        center_id="China",
    )
    institution_payload = build_geographic_payload(
        session,
        filt,
        center_type="institution",
        center_id=institutions["uoft"].id,
    )

    assert country_payload["audit"]["filter_fingerprint"] == institution_payload[
        "audit"
    ]["filter_fingerprint"]
    assert country_payload["audit"]["paper_set_sha256"] == institution_payload[
        "audit"
    ]["paper_set_sha256"]
    assert country_payload["audit"]["projection_fingerprint"] != institution_payload[
        "audit"
    ]["projection_fingerprint"]
    assert country_payload["audit"]["evidence_subsets"]["center_papers"][
        "paper_set_sha256"
    ] != institution_payload["audit"]["evidence_subsets"]["center_papers"][
        "paper_set_sha256"
    ]


def test_geographic_endpoint_rejects_unknown_or_incomplete_center(session):
    from tests.admin_client import AdminTestClient as TestClient
    from app.main import app

    _seed_center_growth(session)
    client = TestClient(app)

    assert client.get(
        "/analytics/geographic",
        params={"center_type": "institution"},
    ).status_code == 422
    assert client.get(
        "/analytics/geographic",
        params={"center_type": "institution", "center_id": "missing"},
    ).status_code == 422
    assert client.get(
        "/analytics/geographic",
        params={"center_type": "country", "center_id": "Atlantis"},
    ).status_code == 422
    assert client.get(
        "/analytics/geographic",
        params={
            "center_country": "China",
            "center_type": "country",
            "center_id": "Japan",
        },
    ).status_code == 422


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


def test_people_grid_uses_full_ac_members_csv(seeded_session):
    from app.services.people_grid_service import build_people_grid

    data = build_people_grid(seeded_session)

    assert data["total_people"] >= 82
    assert len(data["elements"]) >= 82


def test_network_growth_cumulative_counts_unique_entities(fulltext_seeded_session):
    from tests.admin_client import AdminTestClient as TestClient
    from app.main import app

    _setup(fulltext_seeded_session)
    client = TestClient(app)
    r = client.get("/analytics/network-growth", params={"year_from": 2023, "year_to": 2024})
    assert r.status_code == 200
    body = r.json()
    yearly_author_sum = sum(row["authors"] for row in body["yearly"])
    latest = body["cumulative"][-1]

    assert latest["authors"] <= yearly_author_sum
    assert latest["institutions"] <= sum(row["institutions"] for row in body["yearly"])
