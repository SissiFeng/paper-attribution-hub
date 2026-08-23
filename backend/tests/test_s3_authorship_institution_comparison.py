from __future__ import annotations

import csv
import io

from fastapi.testclient import TestClient
import pytest

from app.institution_main import app
from app.main import app as primary_app
from app.services.s3_authorship_institution_comparison import (
    InstitutionMetadataFilter,
    Tier1MetadataSnapshot,
    Tier1MetadataSnapshotStore,
    build_authorship_institution_comparison,
    build_metadata_country_detail,
    build_metadata_geographic_overview,
    comparison_options,
    get_snapshot_store,
)


UOFT = {
    "institution_id": "inst_uoft",
    "display_name": "University of Toronto",
    "ror": "https://ror.org/03dbr7087",
    "openalex_id": "https://openalex.org/I185261750",
    "country_code": "CA",
    "lineage": ["https://openalex.org/I185261750"],
    "source": "openalex",
    "confidence": 0.98,
    "resolved": True,
}
OXFORD = {
    "institution_id": "inst_oxford",
    "display_name": "University of Oxford",
    "ror": "https://ror.org/052gg0110",
    "openalex_id": "https://openalex.org/I40120149",
    "country_code": "GB",
    "lineage": ["https://openalex.org/I40120149"],
    "source": "openalex",
    "confidence": 0.98,
    "resolved": True,
}


def _authorship(
    paper_id: str,
    author_id: str,
    order: int,
    count: int,
    *,
    is_corresponding: bool = False,
) -> dict:
    is_first = order == 0
    is_last = order == count - 1
    if count == 1:
        balanced = heavy = fractional = 1.0
    elif count == 2:
        balanced = heavy = fractional = 0.5
    else:
        balanced = 0.35 if is_first or is_last else 0.3 / (count - 2)
        heavy = 0.4 if is_first or is_last else 0.2 / (count - 2)
        fractional = 1 / count
    paper_title = "Three authors" if paper_id == "p1" else "Multi affiliation"
    return {
        "paper_id": paper_id,
        "doi": f"10.1000/{paper_id}",
        "paper_title": paper_title,
        "author_id": author_id,
        "author_name": f"Author {author_id}",
        "author_order_zero_based": order,
        "author_rank_one_based": order + 1,
        "author_count": count,
        "author_position": "first" if is_first else "last" if is_last else "middle",
        "is_first": is_first,
        "is_last": is_last,
        "is_corresponding": is_corresponding,
        "openalex_author_id": None,
        "orcid": None,
        "provenance_hash": f"hash-{paper_id}-{author_id}",
        "author_weights": {
            "lead_balanced": balanced,
            "lead_heavy": heavy,
            "equal_fractional": fractional,
            "full_counting": 1.0,
        },
    }


def _snapshot(corpus: str = "tier1") -> Tier1MetadataSnapshot:
    papers = (
        {
            "paper_id": "p1",
            "doi": "10.1000/p1",
            "title": "Three authors",
            "abstract": None,
            "year": 2024,
        },
        {
            "paper_id": "p2",
            "doi": "10.1000/p2",
            "title": "Multi affiliation",
            "abstract": None,
            "year": 2025,
        },
    )
    authorships = (
        _authorship("p1", "a0", 0, 3),
        _authorship("p1", "a1", 1, 3, is_corresponding=True),
        _authorship("p1", "a2", 2, 3),
        _authorship("p2", "a3", 0, 1, is_corresponding=True),
    )
    affiliations = tuple(
        {
            **affiliation,
            "paper_id": paper_id,
            "author_id": author_id,
        }
        for paper_id, author_id, values in (
            ("p1", "a0", [UOFT]),
            ("p1", "a1", [OXFORD]),
            ("p1", "a2", [UOFT]),
            ("p2", "a3", [UOFT, OXFORD]),
        )
        for affiliation in values
    )
    return Tier1MetadataSnapshot(
        manifest={
            "schema_version": "tier1_metadata_snapshot.v2",
            "kind": "tier1_metadata_snapshot",
            "status": "ready",
            "corpus": {
                "id": corpus,
                "label": "Tier 1 + Tier 2" if corpus == "tier1_tier2" else "Tier 1",
            },
            "enrichment_run": {
                "id": "run-1",
                "agent_version": "test",
                "status": "succeeded",
                "input_sha256": "input-sha",
                "summary": {},
                "started_at": "2026-01-01T00:00:00Z",
                "completed_at": "2026-01-01T00:01:00Z",
            },
            "scope": {
                "papers": 2,
                "papers_with_authorship_metadata": 2,
                "authorships": 4,
            },
            "storage": {
                "bucket": "metadata-bucket",
                "snapshot_id": "snapshot-1",
                "raw_prefix": "raw/metadata/tier1/snapshot-1",
                "fulltext_prefix": "raw/zotero/",
                "separation_verified": True,
            },
        },
        manifest_key=f"manifests/metadata/{corpus}/snapshot-1/manifest.json",
        manifest_sha256="manifest-sha",
        papers=papers,
        authorships=authorships,
        affiliations=affiliations,
    )


def test_s3_snapshot_comparison_counts_any_affiliated_author() -> None:
    result = build_authorship_institution_comparison(
        _snapshot(),
        InstitutionMetadataFilter(),
        credit_scheme="lead_balanced",
        author_role="last",
        affiliation_allocation="fractional",
    )

    oxford = next(row for row in result["institutions"] if row["id"] == "inst_oxford")
    assert result["scope"]["corpus_papers"] == 2
    assert result["scope"]["authorship_metadata_rows"] == 4
    assert result["focus"]["paper_count"] == 2
    assert result["focus"]["share_of_corpus_papers"] == 1.0
    assert oxford["paper_count"] == 2
    assert result["focus"]["weighted_credit"] == 0.85
    assert result["network"]["scope"]["complete_papers"] == 2
    assert result["network"]["scope"]["papers_with_connections"] == 1
    assert result["network"]["scope"]["connection_count"] == 1
    assert result["network"]["focus"]["collaborator_count"] == 1
    assert result["network"]["focus"]["rank"] == 1
    assert result["network"]["edges"] == [
        {
            "source": "inst_oxford",
            "target": "inst_uoft",
            "paper_count": 1,
        }
    ]
    assert (
        result["network"]["method"]["focus_identity_rule"]
        == "exact_uoft_ror_or_openalex_id"
    )
    assert all(row["focus_paper_share_of_corpus"] == 1.0 for row in result["yearly"])
    assert result["audit"]["data_boundary"]["mode"] == "metadata_only_s3_snapshot"
    assert (
        "primary application papers table"
        in result["audit"]["data_boundary"]["excluded"]
    )
    assert result["audit"]["snapshot"]["separation_verified"] is True


def test_first_and_corresponding_author_filters_are_independent() -> None:
    first = build_authorship_institution_comparison(
        _snapshot(),
        InstitutionMetadataFilter(search="Three authors"),
        credit_scheme="full_counting",
        author_role="first",
        affiliation_allocation="fractional",
    )
    corresponding = build_authorship_institution_comparison(
        _snapshot(),
        InstitutionMetadataFilter(search="Three authors"),
        credit_scheme="full_counting",
        author_role="corresponding",
        affiliation_allocation="fractional",
    )

    assert first["scope"]["selected_authorships"] == 1
    assert first["focus"]["weighted_credit"] == 1.0
    assert first["comparison"]["other_institutions_weighted_credit"] == 0.0
    assert first["configuration"]["author_role_label"] == "First author only"

    assert corresponding["scope"]["selected_authorships"] == 1
    assert corresponding["focus"]["weighted_credit"] == 0.0
    assert corresponding["comparison"]["other_institutions_weighted_credit"] == 1.0
    assert (
        corresponding["configuration"]["author_role_label"]
        == "Corresponding author only"
    )
    assert first["network"] == corresponding["network"]

    role_options = comparison_options(_snapshot())["author_roles"]
    assert [option["value"] for option in role_options] == [
        "all",
        "first",
        "corresponding",
        "last",
        "middle",
    ]
    assert all(option["description"] for option in role_options)


def test_metadata_geographic_overview_uses_country_codes_without_fake_arc() -> None:
    result = build_metadata_geographic_overview(
        _snapshot(),
        InstitutionMetadataFilter(),
    )

    countries = {row["country_code"]: row for row in result["countries"]}
    assert result["scope"]["corpus_papers"] == 2
    assert result["scope"]["mapped_papers"] == 2
    assert result["scope"]["paper_country_coverage"] == 1.0
    assert countries["CA"]["paper_count"] == 2
    assert countries["GB"]["paper_count"] == 2
    assert countries["CA"]["institution_count"] == 1
    assert countries["GB"]["institution_count"] == 1
    assert result["collaborations"] == [
        {"source": "CA", "target": "GB", "paper_count": 1}
    ]
    assert result["scope"]["cross_country_papers"] == 1
    assert result["audit"]["data_boundary"]["mode"] == "metadata_only_s3_snapshot"
    assert (
        result["audit"]["projection"]["collaboration_rule"]
        == "different_authors_across_two_countries"
    )


def test_metadata_country_detail_compares_only_country_institutions() -> None:
    result = build_metadata_country_detail(
        _snapshot(),
        InstitutionMetadataFilter(),
        "gb",
        credit_scheme="full_counting",
        affiliation_allocation="fractional",
    )

    assert result["country"]["country_code"] == "GB"
    assert result["country"]["paper_count"] == 2
    assert result["scope"]["country_institutions"] == 1
    assert [row["name"] for row in result["institutions"]] == ["University of Oxford"]
    assert result["institutions"][0]["weighted_credit"] == 1.5
    assert result["institutions"][0]["share_of_country_credit"] == 1.0
    assert result["audit"]["algorithm"] == (
        "s3_metadata_country_institution_comparison.v1"
    )


def test_api_reads_snapshot_and_rejects_fulltext_filter() -> None:
    class Store:
        def load(self):
            return _snapshot()

    app.dependency_overrides[get_snapshot_store] = Store
    try:
        client = TestClient(app)
        response = client.get(
            "/institution-authorship/report",
            params={"credit_scheme": "equal_fractional", "year_from": 2024},
        )
        colleague_view = client.get(
            "/institution-authorship/report",
            params={
                "credit_scheme": "full_counting",
                "affiliation_allocation": "full",
            },
        )
        rejected = client.get(
            "/institution-authorship/report",
            params={"has_fulltext": "true"},
        )
        prefixed = client.get("/api/institution-authorship/options")
        geographic = client.get("/api/institution-authorship/geographic")
        country = client.get(
            "/institution-authorship/geographic/countries/GB",
            params={"credit_scheme": "equal_fractional"},
        )
        missing_country = client.get("/institution-authorship/geographic/countries/ZZ")
    finally:
        app.dependency_overrides.pop(get_snapshot_store, None)

    assert response.status_code == 200
    assert response.json()["scope"]["corpus_papers"] == 2
    assert colleague_view.status_code == 200
    colleague_payload = colleague_view.json()
    assert colleague_payload["configuration"]["credit_scheme"] == "full_counting"
    assert colleague_payload["configuration"]["affiliation_allocation"] == "full"
    assert colleague_payload["focus"]["weighted_credit"] == 3.0
    assert (
        next(
            row
            for row in colleague_payload["institutions"]
            if row["id"] == "inst_oxford"
        )["weighted_credit"]
        == 2.0
    )
    assert rejected.status_code == 422
    assert "has_fulltext" in rejected.json()["detail"]

    assert prefixed.status_code == 200
    assert geographic.status_code == 200
    assert geographic.json()["scope"]["country_count"] == 2
    assert country.status_code == 200
    assert country.json()["country"]["country_code"] == "GB"
    assert missing_country.status_code == 404


def test_api_selects_corpus_and_exports_corpus_specific_filename() -> None:
    class Store:
        def __init__(self, corpus: str):
            self.corpus = corpus

        def load(self):
            return _snapshot(self.corpus)

    def selected_store(corpus: str = "tier1"):
        return Store(corpus)

    app.dependency_overrides[get_snapshot_store] = selected_store
    try:
        client = TestClient(app)
        report = client.get(
            "/institution-authorship/report",
            params={"corpus": "tier1_tier2"},
        )
        options = client.get(
            "/institution-authorship/options",
            params={"corpus": "tier1_tier2"},
        )
        export = client.get(
            "/institution-authorship/export.csv",
            params={"corpus": "tier1_tier2"},
        )
        metadata_export = client.get(
            "/institution-authorship/author-institution-map.csv",
            params={"corpus": "tier1"},
        )
        rejected_metadata_export = client.get(
            "/institution-authorship/author-institution-map.csv",
            params={"corpus": "tier1_tier2"},
        )
    finally:
        app.dependency_overrides.pop(get_snapshot_store, None)
    invalid = client.get(
        "/institution-authorship/report",
        params={"corpus": "unknown"},
    )

    assert report.status_code == 200
    assert report.json()["configuration"]["corpus"] == "tier1_tier2"
    assert options.status_code == 200
    assert options.json()["corpus"]["label"] == "Tier 1 + Tier 2"
    assert [row["id"] for row in options.json()["corpora"]] == [
        "tier1",
        "tier1_tier2",
    ]
    assert export.status_code == 200
    assert (
        "tier1-tier2-institution-authorship-comparison.csv"
        in export.headers["content-disposition"]
    )
    assert metadata_export.status_code == 200
    assert metadata_export.headers["x-paper-count"] == "2"
    assert (
        "tier1-2-paper-author-institution-metadata.csv"
        in metadata_export.headers["content-disposition"]
    )
    metadata_rows = list(
        csv.DictReader(io.StringIO(metadata_export.content.decode("utf-8-sig")))
    )
    assert {row["paper_id"] for row in metadata_rows} == {"p1", "p2"}
    assert {row["author_name"] for row in metadata_rows} == {
        "Author a0",
        "Author a1",
        "Author a2",
        "Author a3",
    }
    assert rejected_metadata_export.status_code == 422
    assert invalid.status_code == 422


def test_snapshot_store_rejects_cross_wired_manifest() -> None:
    store = Tier1MetadataSnapshotStore(
        s3_client=object(),
        bucket="bucket",
        manifest_key="manifest.json",
        corpus="tier1_tier2",
    )
    with pytest.raises(RuntimeError, match="does not match requested corpus"):
        store._validate_manifest(_snapshot("tier1").manifest)


def test_primary_application_does_not_mount_institution_metadata_routes() -> None:
    paths = {route.path for route in primary_app.routes}
    assert "/institution-authorship/report" not in paths
    assert "/api/institution-authorship/report" not in paths
