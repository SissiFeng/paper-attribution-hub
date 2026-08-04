import pytest
from urllib.parse import parse_qs
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from app.main import app
from app.models import Paper
from app.services.filter_spec import (
    PaperFilter,
    apply_filter,
    build_filter_audit,
    canonical_filter_query_string,
    filter_fingerprint,
    paper_set_sha256,
)


def _ids(session, filt: PaperFilter) -> list[str]:
    stmt = apply_filter(select(Paper.id), filt)
    return [pid for (pid,) in session.execute(stmt).all()]


def test_empty_filter_returns_all(fulltext_seeded_session):
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    ids = _ids(fulltext_seeded_session, PaperFilter())
    assert set(ids) >= {"P001", "P003", "P011"}


def test_canonical_filter_query_string_encodes_every_dimension():
    filt = PaperFilter(
        year_from=2021,
        year_to=2025,
        labels=["EXCLUDE", "CORE_RELEVANT"],
        topic_ids=["topic/a?b", "topic&c"],
        fields=["field=A&B"],
        institution_ids=["institution/1"],
        countries=["Côte d'Ivoire", "Réunion"],
        cities=["Toronto", "Vancouver"],
        corpus_sources=["LEGACY_IMPORT"],
        sdl_judgements=["CONFIRMED_SDL"],
        ac_relevance_judgements=["AC_RELEVANT"],
        ai_for_science_judgements=["AI_FOR_SCIENCE"],
        review_statuses=["COMPLETED"],
        review_statuses_include_unreviewed=True,
        unreviewed_min_confidence=0.75,
        unreviewed_sdl_labels=["SDL_ADJACENT"],
        exclude_unreviewed_corpus_sources=["ARCHITECTURE_BROAD_RETRIEVAL"],
        require_review=True,
        partner_only=True,
        ac_author_only=False,
        has_fulltext=True,
        has_review=False,
        min_confidence=0.25,
        max_confidence=0.9,
        search="A&B = 1?\nnext",
    )

    parsed = parse_qs(
        canonical_filter_query_string(filt, metric_key="themes.top_0.name"),
        keep_blank_values=True,
    )

    assert set(parsed) == set(PaperFilter.model_fields) | {"metric_key"}
    assert parsed["review_statuses_include_unreviewed"] == ["true"]
    assert parsed["unreviewed_min_confidence"] == ["0.75"]
    assert parsed["unreviewed_sdl_labels"] == ["SDL_ADJACENT"]
    assert parsed["exclude_unreviewed_corpus_sources"] == [
        "ARCHITECTURE_BROAD_RETRIEVAL"
    ]
    assert parsed["require_review"] == ["true"]
    assert parsed["labels"] == ["CORE_RELEVANT", "EXCLUDE"]
    assert parsed["topic_ids"] == ["topic&c", "topic/a?b"]
    assert parsed["countries"] == ["Côte d'Ivoire", "Réunion"]
    assert parsed["cities"] == ["Toronto", "Vancouver"]
    assert parsed["search"] == ["A&B = 1?\nnext"]
    assert parsed["partner_only"] == ["true"]
    assert parsed["ac_author_only"] == ["false"]
    assert parsed["metric_key"] == ["themes.top_0.name"]


def test_paper_set_hash_is_unambiguous_and_order_independent():
    assert paper_set_sha256(["a\nb", "c"]) != paper_set_sha256(["a", "b\nc"])
    mixed = ["éclair", "Alpha", "alpha", "Ångström"]
    assert paper_set_sha256(mixed) == paper_set_sha256(list(reversed(mixed)))


def test_year_range_filter(fulltext_seeded_session):
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    ids = _ids(fulltext_seeded_session, PaperFilter(year_from=2024, year_to=2024))
    # P002, P003, P004, P006, P008, P009 are 2024 in our sample data.
    assert ids and all(pid not in {"P010", "P001"} for pid in ids)


def test_label_filter(fulltext_seeded_session):
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    ids = _ids(fulltext_seeded_session, PaperFilter(labels=["CORE_RELEVANT"]))
    assert ids
    assert all(pid in {"P001", "P002", "P004", "P006", "P009"} for pid in ids)


def test_partner_only_filter(fulltext_seeded_session):
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    ids = _ids(fulltext_seeded_session, PaperFilter(partner_only=True))
    # Climate paper P010 (Univ of Oslo) should be excluded; P007 (Tokyo/KAIST) too.
    assert "P010" not in ids
    assert "P007" not in ids


def test_ac_author_only_filter(fulltext_seeded_session):
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    ids = _ids(fulltext_seeded_session, PaperFilter(ac_author_only=True))
    assert "P011" not in ids  # no direct AC author
    assert "P001" in ids


def test_min_confidence_filter(fulltext_seeded_session):
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    ids = _ids(fulltext_seeded_session, PaperFilter(min_confidence=0.8))
    assert "P010" not in ids


def test_search_filter(fulltext_seeded_session):
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    ids = _ids(fulltext_seeded_session, PaperFilter(search="self-driving"))
    assert "P001" in ids or "P006" in ids


def test_combined_filter(fulltext_seeded_session):
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    ids = _ids(
        fulltext_seeded_session,
        PaperFilter(
            labels=["CORE_RELEVANT", "RELATED_RELEVANT"],
            partner_only=True,
            year_from=2023,
        ),
    )
    assert ids
    assert "P010" not in ids


def test_partner_and_institution_filters_are_both_required(
    fulltext_seeded_session,
):
    from app.models import Institution
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    non_partner = fulltext_seeded_session.execute(
        select(Institution).where(Institution.is_partner.is_(False))
    ).scalars().first()
    assert non_partner is not None

    ids = _ids(
        fulltext_seeded_session,
        PaperFilter(
            institution_ids=[non_partner.id],
            partner_only=True,
        ),
    )

    assert ids == []


def test_search_treats_sql_wildcards_as_literal(fulltext_seeded_session):
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)

    assert _ids(fulltext_seeded_session, PaperFilter(search="%")) == []
    assert _ids(fulltext_seeded_session, PaperFilter(search="_")) == []


def test_invalid_cross_field_ranges_fail_at_model_and_api(
    fulltext_seeded_session,
):
    with pytest.raises(ValidationError):
        PaperFilter(year_from=2025, year_to=2024)
    with pytest.raises(ValidationError):
        PaperFilter(min_confidence=0.9, max_confidence=0.2)
    with pytest.raises(ValidationError):
        PaperFilter(min_confidence=-0.1)
    with pytest.raises(ValidationError):
        PaperFilter(max_confidence=1.1)
    with pytest.raises(ValidationError):
        PaperFilter(min_confidence=float("nan"))

    client = TestClient(app)
    assert client.get("/papers?year_from=2025&year_to=2024").status_code == 422
    assert (
        client.get("/papers?min_confidence=0.9&max_confidence=0.2").status_code
        == 422
    )


def test_human_scope_judgement_overrides_model_scope(
    fulltext_seeded_session,
):
    from app.models import HumanReview
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    paper = fulltext_seeded_session.get(Paper, "P001")
    paper.classification.sdl_relevance_label = "SDL_RELEVANT"
    paper.classification.ac_attribution_label = "CORE_AC"
    fulltext_seeded_session.commit()

    assert "P001" in _ids(
        fulltext_seeded_session,
        PaperFilter(sdl_judgements=["CONFIRMED_SDL"]),
    )
    assert "P001" in _ids(
        fulltext_seeded_session,
        PaperFilter(ac_relevance_judgements=["AC_RELEVANT"]),
    )

    fulltext_seeded_session.add(
        HumanReview(
            id="review_scope_override",
            paper_id="P001",
            sdl_judgement="NOT_SDL",
            ac_relevance_judgement="AC_RELEVANT",
            review_status="COMPLETED",
        )
    )
    fulltext_seeded_session.commit()

    assert "P001" not in _ids(
        fulltext_seeded_session,
        PaperFilter(sdl_judgements=["CONFIRMED_SDL"]),
    )
    assert "P001" in _ids(
        fulltext_seeded_session,
        PaperFilter(sdl_judgements=["NOT_SDL"]),
    )
    assert "P001" in _ids(
        fulltext_seeded_session,
        PaperFilter(ac_relevance_judgements=["AC_RELEVANT"]),
    )


def test_filter_audit_is_stable_and_replayable(fulltext_seeded_session):
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    filt = PaperFilter(year_from=2024, labels=["CORE_RELEVANT"])

    first = build_filter_audit(
        fulltext_seeded_session,
        filt,
        algorithm="test.v1",
        metric_definitions={"paper_count": "Distinct filtered papers."},
    )
    second = build_filter_audit(
        fulltext_seeded_session,
        filt,
        algorithm="test.v1",
        metric_definitions={"paper_count": "Distinct filtered papers."},
    )

    assert first["filter_fingerprint"] == filter_fingerprint(filt)
    assert first["filter_fingerprint"] == second["filter_fingerprint"]
    assert first["paper_set_sha256"] == second["paper_set_sha256"]
    assert first["included_papers"] == len(
        _ids(fulltext_seeded_session, filt)
    )
    assert first["algorithm"] == "test.v1"
    assert first["filter_semantics"]["within_dimension"] == "OR"


def test_filter_enum_values_are_normalized_and_invalid_values_fail_closed(
    fulltext_seeded_session,
):
    assert PaperFilter(
        labels=["core_relevant"],
        corpus_sources=["ac_member_corpus"],
        review_statuses=["completed"],
    ).model_dump()["corpus_sources"] == ["AC_MEMBER_CORPUS"]

    with pytest.raises(ValidationError):
        PaperFilter(sdl_judgements=["maybe"])

    client = TestClient(app)
    response = client.get("/papers?sdl_judgements=maybe")
    assert response.status_code == 422


def test_topic_values_are_or_within_the_dimension(session):
    from app.models import PaperClassification

    first = Paper(id="topic_or_first", title="First topic")
    first.classification = PaperClassification(
        id="topic_or_first_cls",
        label="CORE_RELEVANT",
        confidence=0.9,
        matched_topics=[{"topic_id": "topic-a"}],
        matched_people=[],
        matched_institutions=[],
        reasons=[],
        graph_signals=None,
    )
    second = Paper(id="topic_or_second", title="Second topic")
    second.classification = PaperClassification(
        id="topic_or_second_cls",
        label="CORE_RELEVANT",
        confidence=0.9,
        matched_topics=[{"topic_id": "topic-b"}],
        matched_people=[],
        matched_institutions=[],
        reasons=[],
        graph_signals=None,
    )
    session.add_all([first, second])
    session.commit()

    assert set(_ids(session, PaperFilter(topic_ids=["topic-a", "topic-b"]))) == {
        "topic_or_first",
        "topic_or_second",
    }
    assert _ids(session, PaperFilter(topic_ids=["%"])) == []
    assert _ids(session, PaperFilter(topic_ids=["_"])) == []


def test_country_filter_handles_semicolon_normalization(session):
    from app.models import Author, Institution, PaperAuthor

    institution = Institution(
        id="semicolon_country_inst",
        canonical_name="Cross-border Lab",
        aliases=[],
        normalized_aliases=[],
        country=" canada ;\t USA; TÜRKİYE; United\u00a0States",
    )
    author = Author(
        id="semicolon_country_author",
        canonical_name="Country Author",
        aliases=[],
        normalized_name="country author",
        institution=institution,
    )
    paper = Paper(
        id="semicolon_country_paper",
        title="Country paper",
        year=2024,
    )
    paper.authors.append(PaperAuthor(author=author, author_order=0))
    session.add(paper)
    session.commit()

    assert _ids(session, PaperFilter(countries=["Canada"])) == [
        "semicolon_country_paper"
    ]
    assert _ids(session, PaperFilter(countries=["United States"])) == [
        "semicolon_country_paper"
    ]
    assert _ids(session, PaperFilter(countries=["united states"])) == [
        "semicolon_country_paper"
    ]
    assert _ids(session, PaperFilter(countries=["Türkiye"])) == [
        "semicolon_country_paper"
    ]
    assert len(institution.country_keys) == 3
    from app.services.analytics_service import topic_over_time
    from app.services.filter_spec import available_filter_options
    from app.services.geographic_service import build_geographic_payload

    options = available_filter_options(session)
    assert {"Canada", "Türkiye", "United States"} <= set(options["countries"])
    country_series = topic_over_time(session, PaperFilter(), by="country")
    assert {series.name for series in country_series} == {
        "Canada",
        "Türkiye",
        "United States",
    }
    geography = build_geographic_payload(session, PaperFilter())
    assert {row["country"] for row in geography["countries"]} == {
        "Canada",
        "Türkiye",
        "United States",
    }


def test_country_identity_unifies_accent_variants_across_analytics(session):
    from app.models import Author, Institution, PaperAuthor
    from app.services.analytics_service import topic_over_time
    from app.services.filter_spec import available_filter_options
    from app.services.geographic_service import build_geographic_payload
    from app.services.multi_graph import MultiGraphFilter, build_multi_graph

    accented = Institution(
        id="reunion_accented",
        canonical_name="Réunion Partner Lab",
        aliases=[],
        normalized_aliases=[],
        country="Réunion",
        is_partner=True,
    )
    ascii_only = Institution(
        id="reunion_ascii",
        canonical_name="Reunion Lab",
        aliases=[],
        normalized_aliases=[],
        country="Reunion",
    )
    accented_author = Author(
        id="reunion_accented_author",
        canonical_name="Accented Author",
        aliases=[],
        normalized_name="accented author",
        institution=accented,
    )
    ascii_author = Author(
        id="reunion_ascii_author",
        canonical_name="ASCII Author",
        aliases=[],
        normalized_name="ascii author",
        institution=ascii_only,
    )
    shared = Paper(id="reunion_shared", title="Shared island paper", year=2024)
    shared.authors.extend(
        [
            PaperAuthor(author=accented_author, author_order=0),
            PaperAuthor(author=ascii_author, author_order=1),
        ]
    )
    second = Paper(id="reunion_second", title="Second island paper", year=2024)
    second.authors.append(PaperAuthor(author=ascii_author, author_order=0))
    session.add_all([shared, second])
    session.commit()

    expected_ids = {"reunion_shared", "reunion_second"}
    assert set(_ids(session, PaperFilter(countries=["Réunion"]))) == expected_ids
    assert set(_ids(session, PaperFilter(countries=["Reunion"]))) == expected_ids
    assert available_filter_options(session)["countries"] == ["Réunion"]

    timeline = topic_over_time(session, PaperFilter(), by="country")
    assert [(series.name, series.data) for series in timeline] == [
        ("Réunion", [(2024, 2)])
    ]

    geography = build_geographic_payload(session, PaperFilter())
    assert geography["countries"] == [
        {
            "country": "Réunion",
            "paper_count": 2,
            "institution_count": 2,
            "is_partner": True,
        }
    ]
    assert geography["arcs"] == []

    graph = build_multi_graph(
        session,
        MultiGraphFilter(
            node_types=["country"],
            edge_types=["country_collaboration"],
        ),
    )
    assert [(node.id, node.label, node.metadata["paper_count"]) for node in graph.nodes] == [
        ("country:Réunion", "Réunion", 2)
    ]
    assert graph.edges == []


def test_corpus_source_filter_uses_explicit_and_legacy_provenance(session):
    explicit = Paper(
        id="corpus_explicit",
        title="Explicit corpus",
        corpus_sources=["STRICT_SDL_KEYWORD"],
        provenance="ac_gold",
    )
    inferred = Paper(
        id="corpus_inferred",
        title="Inferred corpus",
        provenance="ac_gold",
        corpus_sources=[],
    )
    session.add_all([explicit, inferred])
    session.commit()

    assert _ids(
        session,
        PaperFilter(corpus_sources=["strict_sdl_keyword"]),
    ) == ["corpus_explicit"]
    assert _ids(
        session,
        PaperFilter(corpus_sources=["ac_member_corpus"]),
    ) == ["corpus_inferred"]
    audit = build_filter_audit(
        session,
        PaperFilter(),
        algorithm="test.corpus-authority.v1",
        metric_definitions={},
    )
    assert audit["corpus_source_breakdown"] == {
        "AC_MEMBER_CORPUS": 1,
        "STRICT_SDL_KEYWORD": 1,
    }
