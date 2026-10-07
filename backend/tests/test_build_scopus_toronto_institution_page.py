from __future__ import annotations

import json
from pathlib import Path

from app.scripts.build_scopus_toronto_institution_page import (
    build_toronto_dataset,
    render_page,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )


def _work() -> dict:
    return {
        "id": "https://openalex.org/W1",
        "doi": "https://doi.org/10.test/one",
        "title": "Paper one",
        "publication_year": 2024,
        "authorships": [
            {
                "author_position": "first",
                "is_corresponding": True,
                "institutions": [
                    {
                        "id": "https://openalex.org/I185261750",
                        "display_name": "University of Toronto",
                        "ror": "https://ror.org/03dbr7087",
                        "country_code": "CA",
                        "type": "education",
                        "lineage": ["https://openalex.org/I185261750"],
                    }
                ],
            }
        ],
        "is_authors_truncated": False,
        "is_retracted": False,
    }


def test_builds_scopus_bounded_dataset_from_enrichment_artifacts(tmp_path):
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "scopus_unique_records": 2,
                "scopus_input_sha256": "abc123",
                "scopus_query": 'ALL("self-driving lab*") AND AFFIL(Toronto)',
            }
        ),
        encoding="utf-8",
    )
    _write_jsonl(
        tmp_path / "scopus_results.jsonl",
        [
            {"eid": "E1", "doi": "10.test/one", "title": "Paper one", "year": 2024, "raw": {"作者 ID": "1"}},
            {"eid": "E2", "doi": None, "title": "Paper two", "year": 2023, "raw": {"作者 ID": "2; 3"}},
        ],
    )
    _write_jsonl(
        tmp_path / "openalex_metadata.jsonl",
        [
            {"scopus_eid": "E1", "match": {"matched": True, "method": "doi"}, "openalex": _work()},
            {"scopus_eid": "E2", "match": {"matched": False, "method": None}, "openalex": None},
        ],
    )

    dataset = build_toronto_dataset(
        tmp_path, generated_at="2026-08-25T00:00:00+00:00"
    )

    assert dataset["manifest"]["counts"]["papers"] == 2
    assert dataset["manifest"]["openalex"]["match_status"] == {
        "doi_exact": 1,
        "missing_doi": 1,
    }
    assert dataset["manifest"]["corpus"]["query"].endswith("AFFIL(Toronto)")
    assert dataset["papers"][0]["d"] == "10.test/one"
    assert dataset["papers"][1]["d"] is None
    assert dataset["papers"][0]["u"][0][0] == 1


def test_retargets_reviewed_institution_page_without_tier_filters():
    root = Path(__file__).resolve().parents[2]
    template = (
        root / "frontend/public/tier1-tier2-openalex-institution-comparison.html"
    ).read_text(encoding="utf-8")

    page = render_page(template)

    assert "Scopus Toronto · 176 papers · OpenAlex metadata only" in page
    assert "scopus-toronto-176-openalex-institution-data.js" in page
    assert '<option value="tier1">' not in page
    assert "Zotero Tier 1/Tier 2" in page
    assert 'max="2028" placeholder="2028"' in page
