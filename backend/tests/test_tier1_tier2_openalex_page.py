from __future__ import annotations

import csv
import json

from app.scripts.build_tier1_tier2_openalex_page import (
    UOFT_OPENALEX_ID,
    aggregate_default,
    build_dataset,
    build_s3_snapshot_rows,
    read_input_csv,
    write_s3_snapshot,
    write_outputs,
)


def _write_input(path) -> None:
    fields = [
        "EID",
        "DOI",
        "Title",
        "Publication_Year",
        "merge_tier_membership",
        "author_count",
    ]
    rows = [
        {
            "EID": "E1",
            "DOI": "10.test/one",
            "Title": "Paper one",
            "Publication_Year": "2024",
            "merge_tier_membership": "1",
            "author_count": "3",
        },
        {
            "EID": "E1-duplicate",
            "DOI": "https://doi.org/10.test/one",
            "Title": "Paper one",
            "Publication_Year": "2024",
            "merge_tier_membership": "2",
            "author_count": "3",
        },
        {
            "EID": "E2",
            "DOI": "",
            "Title": "Paper without DOI",
            "Publication_Year": "2023",
            "merge_tier_membership": "2",
            "author_count": "1",
        },
        {
            "EID": "E3",
            "DOI": "10.test/unmatched",
            "Title": "Unmatched paper",
            "Publication_Year": "2022",
            "merge_tier_membership": "2",
            "author_count": "2",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _work() -> dict:
    uoft = {
        "id": UOFT_OPENALEX_ID,
        "display_name": "University of Toronto",
        "ror": "https://ror.org/03dbr7087",
        "country_code": "CA",
        "type": "education",
        "lineage": [UOFT_OPENALEX_ID],
    }
    mit = {
        "id": "https://openalex.org/I63966007",
        "display_name": "Massachusetts Institute of Technology",
        "ror": "https://ror.org/042nb2s44",
        "country_code": "US",
        "type": "education",
        "lineage": ["https://openalex.org/I63966007"],
    }
    return {
        "id": "https://openalex.org/W1",
        "doi": "https://doi.org/10.test/one",
        "title": "Paper one",
        "publication_year": 2024,
        "authorships": [
            {
                "author_position": "first",
                "is_corresponding": False,
                "institutions": [uoft],
            },
            {
                "author_position": "middle",
                "is_corresponding": False,
                "institutions": [mit],
            },
            {
                "author_position": "last",
                "is_corresponding": True,
                "institutions": [mit],
            },
        ],
        "is_authors_truncated": False,
        "is_retracted": False,
    }


def test_read_build_and_write_independent_snapshot(tmp_path):
    source = tmp_path / "merged.csv"
    _write_input(source)
    papers, stats = read_input_csv(source)

    assert stats == {
        "raw_rows": 4,
        "distinct_papers": 3,
        "rows_with_doi": 3,
        "unique_dois": 2,
        "missing_doi_rows": 1,
        "duplicate_doi_groups": 1,
        "duplicate_rows_beyond_first": 1,
        "tier_membership_rows": {"1": 1, "2": 3},
    }
    assert next(row for row in papers if row.doi == "10.test/one").membership == "1+2"

    dataset = build_dataset(
        papers,
        {"10.test/one": [_work()]},
        generated_at="2026-08-19T00:00:00+00:00",
        source_name=source.name,
        source_sha256="abc123",
        input_stats=stats,
        fetch_stats={"api_calls": 1, "cache_hits": 0},
    )
    assert dataset["manifest"]["openalex"]["match_status"] == {
        "doi_exact": 1,
        "missing_doi": 1,
        "openalex_unmatched": 1,
    }
    assert dataset["manifest"]["counts"]["authorships"] == 3
    assert (
        dataset["manifest"]["data_boundary"]["excluded"][-1]
        == "Scopus affiliations as fallback"
    )

    report = aggregate_default(dataset)
    assert report["corpus_papers"] == 3
    assert report["papers_with_authorship_metadata"] == 1
    assert report["focus_paper_count"] == 1
    assert report["focus_weighted_credit"] == 0.35
    assert report["other_weighted_credit"] == 0.65
    assert report["institutions"][0]["name"] == "Massachusetts Institute of Technology"

    outputs = write_outputs(
        dataset,
        data_js=tmp_path / "data" / "snapshot.js",
        artifact_dir=tmp_path / "artifacts",
    )
    data_text = (tmp_path / "data" / "snapshot.js").read_text(encoding="utf-8")
    assert data_text.startswith("window.TIER1_TIER2_OPENALEX_INSTITUTION_DATA=")
    manifest = json.loads((tmp_path / "artifacts" / "manifest.json").read_text())
    assert manifest["schema_version"] == "tier1_tier2_openalex_institution.v1"
    assert manifest["default_report"]["focus_paper_count"] == 1
    assert outputs["default_report"]["affiliation_credit_coverage"] == 1.0


def test_infers_openalex_truncation_for_more_than_one_hundred_input_authors(tmp_path):
    source = tmp_path / "merged.csv"
    _write_input(source)
    papers, stats = read_input_csv(source)
    target = next(row for row in papers if row.doi == "10.test/one")
    target = target.__class__(**{**target.__dict__, "author_count": 101})
    dataset = build_dataset(
        [target],
        {"10.test/one": [_work()]},
        generated_at="2026-08-19T00:00:00+00:00",
        source_name=source.name,
        source_sha256="abc123",
        input_stats=stats,
    )
    paper = dataset["papers"][0]
    assert paper["x"] is True
    assert "openalex_authors_truncated_inferred_from_input_count" in paper["q"]


def test_projects_shared_s3_snapshot_contract(tmp_path):
    source = tmp_path / "merged.csv"
    _write_input(source)
    papers, stats = read_input_csv(source)
    dataset = build_dataset(
        papers,
        {"10.test/one": [_work()]},
        generated_at="2026-08-19T00:00:00+00:00",
        source_name=source.name,
        source_sha256="abc123",
        input_stats=stats,
    )

    paper_rows, authorships, affiliations = build_s3_snapshot_rows(dataset)
    assert len(paper_rows) == 3
    assert len(authorships) == 3
    assert sum(row["resolved"] is True for row in affiliations) == 3
    assert authorships[0]["author_identity_scope"] == "paper_local_openalex_order"
    assert authorships[0]["author_weights"]["lead_balanced"] == 0.35

    output = write_s3_snapshot(
        dataset,
        snapshot_dir=tmp_path / "s3-snapshot",
        bucket="artifacts-bucket",
        snapshot_id="snapshot-tier1-tier2",
    )
    manifest = json.loads((tmp_path / "s3-snapshot" / "manifest.json").read_text())
    assert manifest["schema_version"] == "tier1_metadata_snapshot.v2"
    assert manifest["corpus"] == {
        "id": "tier1_tier2",
        "label": "Tier 1 + Tier 2",
        "source": "merged.csv",
    }
    assert manifest["storage"]["separation_verified"] is True
    assert output["manifest_s3_key"].endswith("/snapshot-tier1-tier2/manifest.json")
