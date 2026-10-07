from __future__ import annotations

import csv
import json

import httpx

from app.scripts.fetch_scopus_openalex_metadata import (
    ScopusSearchClient,
    ScopusOpenAlexClient,
    deduplicate_scopus_records,
    enrich_records,
    load_scopus_csv,
    normalize_scopus_entry,
    write_export,
)


def _scopus_entry(index: int, *, doi: str | None = None) -> dict:
    entry = {
        "eid": f"2-s2.0-{index}",
        "dc:identifier": f"SCOPUS_ID:{index}",
        "dc:title": f"Autonomous lab paper {index}",
        "dc:creator": "Example, A.",
        "prism:coverDate": "2024-01-01",
        "prism:publicationName": "Example Journal",
        "citedby-count": str(index),
        "link": [{"@ref": "scopus", "@href": f"https://scopus/{index}"}],
    }
    if doi:
        entry["prism:doi"] = doi
    return entry


def test_scopus_search_paginates_and_sends_credentials():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        start = int(request.url.params["start"])
        page = [_scopus_entry(index, doi=f"10.test/{index}") for index in range(start, min(start + 2, 3))]
        return httpx.Response(
            200,
            json={
                "search-results": {
                    "opensearch:totalResults": "3",
                    "entry": page,
                }
            },
        )

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = ScopusSearchClient("secret-key", insttoken="inst-token", client=http)
    entries, total = client.search("ALL(test)", page_size=2)

    assert total == 3
    assert [entry["eid"] for entry in entries] == ["2-s2.0-0", "2-s2.0-1", "2-s2.0-2"]
    assert len(requests) == 2
    assert requests[0].headers["X-ELS-APIKey"] == "secret-key"
    assert requests[0].headers["X-ELS-Insttoken"] == "inst-token"
    assert requests[0].url.params["view"] == "STANDARD"


def test_deduplication_uses_doi_then_eid_then_fallback():
    records = [
        normalize_scopus_entry(_scopus_entry(1, doi="https://doi.org/10.TEST/ONE")),
        normalize_scopus_entry(_scopus_entry(2, doi="10.test/one")),
        normalize_scopus_entry(_scopus_entry(3)),
        normalize_scopus_entry({**_scopus_entry(3), "dc:title": "Different title"}),
        normalize_scopus_entry(_scopus_entry(4)),
        normalize_scopus_entry({**_scopus_entry(5), "eid": None}),
        normalize_scopus_entry(
            {**_scopus_entry(1, doi="10.test/two"), "dc:title": "DOI wins"}
        ),
    ]
    records[-1]["eid"] = None
    records[-1]["title"] = records[-2]["title"]

    unique = deduplicate_scopus_records(records)

    assert [item["eid"] for item in unique] == [
        "2-s2.0-1",
        "2-s2.0-3",
        "2-s2.0-4",
        None,
        None,
    ]
    assert unique[-1]["doi"] == "10.test/two"


def test_load_scopus_csv_accepts_chinese_web_export(tmp_path):
    path = tmp_path / "scopus.csv"
    path.write_text(
        "文献标题,年份,作者,来源出版物名称,施引文献,DOI,链接,文献类型,EID\n"
        '"A self-driving lab",2026,"Example, A.",Journal,7,10.TEST/ONE,'
        "https://scopus/1,Article,2-s2.0-123\n",
        encoding="utf-8-sig",
    )

    records = load_scopus_csv(path)

    assert records == [
        {
            "eid": "2-s2.0-123",
            "scopus_id": "123",
            "doi": "10.test/one",
            "title": "A self-driving lab",
            "year": 2026,
            "cover_date": None,
            "first_author": "Example, A.",
            "source_title": "Journal",
            "document_type": "Article",
            "citation_count": 7,
            "scopus_url": "https://scopus/1",
            "raw": {
                "文献标题": "A self-driving lab",
                "年份": "2026",
                "作者": "Example, A.",
                "来源出版物名称": "Journal",
                "施引文献": "7",
                "DOI": "10.TEST/ONE",
                "链接": "https://scopus/1",
                "文献类型": "Article",
                "EID": "2-s2.0-123",
            },
        }
    ]


def test_openalex_enrichment_prefers_doi_and_uses_exact_title_fallback(session):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.params.get("filter", "").startswith("doi:"):
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": "https://openalex.org/W1",
                            "doi": "https://doi.org/10.test/1",
                            "display_name": "Autonomous lab paper 1",
                            "publication_year": 2024,
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "https://openalex.org/W2",
                        "doi": None,
                        "display_name": "Autonomous lab paper 2",
                        "publication_year": 2024,
                    }
                ]
            },
        )

    client = ScopusOpenAlexClient(transport=httpx.MockTransport(handler))
    records = [
        normalize_scopus_entry(_scopus_entry(1, doi="10.test/1")),
        normalize_scopus_entry(_scopus_entry(2)),
    ]

    enriched = enrich_records(records, client, session)

    assert [item["openalex"]["id"] for item in enriched] == [
        "https://openalex.org/W1",
        "https://openalex.org/W2",
    ]
    assert [item["match"]["method"] for item in enriched] == ["doi", "title_year"]


def test_write_export_creates_auditable_artifacts(tmp_path):
    scopus = normalize_scopus_entry(_scopus_entry(1, doi="10.test/1"))
    work = {
        "id": "https://openalex.org/W1",
        "doi": "https://doi.org/10.test/1",
        "display_name": "=DANGEROUS_FORMULA()",
        "publication_year": 2024,
        "abstract_inverted_index": {"An": [0], "abstract": [1]},
        "authorships": [],
    }
    enriched = [
        {
            "scopus": scopus,
            "openalex": work,
            "match": {"matched": True, "method": "doi", "confidence": 1.0},
        }
    ]

    manifest = write_export(
        tmp_path,
        query="ALL(test)",
        expected_count=1,
        scopus_total=1,
        raw_entry_count=1,
        enriched=enriched,
    )

    assert manifest["scopus_count_matches_expected"] is True
    assert manifest["match_methods"] == {"doi": 1}
    assert set(manifest["artifacts"]) == {
        "scopus_results.jsonl",
        "openalex_metadata.jsonl",
        "merged_metadata.csv",
        "match_audit.csv",
    }
    assert json.loads((tmp_path / "manifest.json").read_text())["openalex_matched_records"] == 1
    with (tmp_path / "merged_metadata.csv").open(encoding="utf-8-sig") as handle:
        row = next(csv.DictReader(handle))
    assert row["abstract"] == "An abstract"
    assert row["openalex_match_method"] == "doi"
    assert row["openalex_title"] == "'=DANGEROUS_FORMULA()"


def test_write_export_rejects_symlink_destination(tmp_path):
    target = tmp_path / "target.csv"
    target.write_text("do not overwrite", encoding="utf-8")
    (tmp_path / "merged_metadata.csv").symlink_to(target)
    scopus = normalize_scopus_entry(_scopus_entry(1, doi="10.test/1"))
    enriched = [
        {
            "scopus": scopus,
            "openalex": {"id": "https://openalex.org/W1"},
            "match": {"matched": True, "method": "doi", "confidence": 1.0},
        }
    ]

    try:
        write_export(
            tmp_path,
            query="ALL(test)",
            expected_count=1,
            scopus_total=1,
            raw_entry_count=1,
            enriched=enriched,
        )
    except ValueError as exc:
        assert "symlink" in str(exc)
    else:
        raise AssertionError("Expected symlink destination to be rejected")
    assert target.read_text(encoding="utf-8") == "do not overwrite"
