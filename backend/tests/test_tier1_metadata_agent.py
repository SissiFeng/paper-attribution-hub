from __future__ import annotations

import csv

import httpx
from sqlalchemy import func, select

from app.models import Author, Paper, PaperAuthorshipMetadata
from app.services.external.crossref_client import CrossrefClient
from app.services.external.openalex_client import OpenAlexClient
from app.services.external.ror_client import RorClient
from app.services.tier1_metadata_agent import (
    read_tier1_csv,
    run_tier1_metadata_agent,
)


def _write_csv(path) -> None:
    fieldnames = [
        "Key",
        "Item Type",
        "Title",
        "Publication Year",
        "Publication Title",
        "Author",
        "Abstract Note",
        "DOI",
        "Url",
        "File Attachments",
    ]
    rows = [
        {
            "Key": "A1",
            "Item Type": "journalArticle",
            "Title": "Paper one",
            "Publication Year": "2024",
            "Publication Title": "Journal A",
            "Author": "Jane First; Sam Last",
            "Abstract Note": "",
            "DOI": "10.test/one",
            "Url": "",
            "File Attachments": "one.pdf",
        },
        {
            "Key": "A2",
            "Item Type": "journalArticle",
            "Title": "Paper one",
            "Publication Year": "2024",
            "Publication Title": "Journal A",
            "Author": "Jane First; Sam Last",
            "Abstract Note": "A longer abstract.",
            "DOI": "https://doi.org/10.test/one",
            "Url": "",
            "File Attachments": "",
        },
        {
            "Key": "B1",
            "Item Type": "journalArticle",
            "Title": "Paper two",
            "Publication Year": "2025",
            "Publication Title": "Journal B",
            "Author": "Alex Solo",
            "Abstract Note": "",
            "DOI": "10.test/two",
            "Url": "",
            "File Attachments": "",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _institution(
    name: str,
    *,
    openalex_id: str,
    ror: str,
    country_code: str,
) -> dict:
    return {
        "id": openalex_id,
        "display_name": name,
        "ror": ror,
        "country_code": country_code,
        "type": "education",
        "lineage": [openalex_id],
    }


def _authorship(
    name: str, author_id: str, position: str, institutions: list[dict]
) -> dict:
    return {
        "author_position": position,
        "is_corresponding": position == "last",
        "author": {"id": author_id, "display_name": name, "orcid": None},
        "institutions": institutions,
        "raw_affiliation_strings": [item["display_name"] for item in institutions],
    }


def _openalex_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path != "/works":
        return httpx.Response(404, json={})
    uoft = _institution(
        "University of Toronto",
        openalex_id="https://openalex.org/I185261750",
        ror="https://ror.org/03dbr7087",
        country_code="CA",
    )
    mit = _institution(
        "Massachusetts Institute of Technology",
        openalex_id="https://openalex.org/I63966007",
        ror="https://ror.org/042nb2s44",
        country_code="US",
    )
    return httpx.Response(
        200,
        json={
            "results": [
                {
                    "id": "https://openalex.org/W1",
                    "doi": "https://doi.org/10.test/one",
                    "title": "Paper one",
                    "publication_year": 2024,
                    "cited_by_count": 7,
                    "authorships": [
                        _authorship(
                            "Jane First",
                            "https://openalex.org/A1",
                            "first",
                            [uoft, mit],
                        ),
                        _authorship(
                            "Sam Last",
                            "https://openalex.org/A2",
                            "last",
                            [uoft],
                        ),
                    ],
                },
                {
                    "id": "https://openalex.org/W2",
                    "doi": "https://doi.org/10.test/two",
                    "title": "Paper two",
                    "publication_year": 2025,
                    "cited_by_count": 2,
                    "authorships": [
                        _authorship(
                            "Alex Solo",
                            "https://openalex.org/A3",
                            "first",
                            [uoft],
                        )
                    ],
                },
            ]
        },
    )


def _unexpected_handler(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"Unexpected fallback request: {request.url}")


def test_read_tier1_csv_deduplicates_by_normalized_doi(tmp_path):
    path = tmp_path / "tier1.csv"
    _write_csv(path)

    papers, summary = read_tier1_csv(path)

    assert len(papers) == 2
    assert papers[0].doi == "10.test/one"
    assert papers[0].duplicate_count == 2
    assert papers[0].abstract == "A longer abstract."
    assert summary == {
        "raw_rows": 3,
        "unique_dois": 2,
        "duplicate_groups": 1,
        "duplicate_rows": 2,
    }


def test_agent_persists_paper_specific_affiliations(session, tmp_path):
    path = tmp_path / "tier1.csv"
    _write_csv(path)
    openalex = OpenAlexClient(transport=httpx.MockTransport(_openalex_handler))
    crossref = CrossrefClient(transport=httpx.MockTransport(_unexpected_handler))
    ror = RorClient(transport=httpx.MockTransport(_unexpected_handler))
    try:
        summary = run_tier1_metadata_agent(
            session,
            path,
            openalex=openalex,
            crossref=crossref,
            ror=ror,
        )
    finally:
        openalex.close()
        crossref.close()
        ror.close()

    assert summary["status"] == "succeeded"
    assert summary["raw_rows"] == 3
    assert summary["selected_papers"] == 2
    assert summary["papers_persisted"] == 2
    assert summary["authorship_rows"] == 3
    assert session.scalar(select(func.count(Paper.id))) == 2
    metadata = list(
        session.execute(
            select(PaperAuthorshipMetadata).order_by(
                PaperAuthorshipMetadata.paper_id,
                PaperAuthorshipMetadata.author_order,
            )
        ).scalars()
    )
    assert len(metadata) == 3
    assert len(metadata[0].affiliations) == 2
    assert metadata[0].sources == ["openalex", "zotero_csv"]
    assert all(item["institution_id"] for row in metadata for item in row.affiliations)
    assert all(row.provenance_hash for row in metadata)


def test_repeated_openalex_identity_keeps_both_author_slots(session, tmp_path):
    path = tmp_path / "tier1.csv"
    _write_csv(path)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/works":
            return httpx.Response(404, json={})
        uoft = _institution(
            "University of Toronto",
            openalex_id="https://openalex.org/I185261750",
            ror="https://ror.org/03dbr7087",
            country_code="CA",
        )
        repeated = _authorship(
            "Repeated Identity",
            "https://openalex.org/A-REPEATED",
            "first",
            [uoft],
        )
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "https://openalex.org/W-REPEATED",
                        "doi": "https://doi.org/10.test/one",
                        "title": "Paper one",
                        "publication_year": 2024,
                        "authorships": [
                            repeated,
                            {**repeated, "author_position": "last"},
                        ],
                    }
                ]
            },
        )

    openalex = OpenAlexClient(transport=httpx.MockTransport(handler))
    crossref = CrossrefClient(transport=httpx.MockTransport(_unexpected_handler))
    ror = RorClient(transport=httpx.MockTransport(_unexpected_handler))
    try:
        summary = run_tier1_metadata_agent(
            session,
            path,
            openalex=openalex,
            crossref=crossref,
            ror=ror,
            max_papers=1,
        )
    finally:
        openalex.close()
        crossref.close()
        ror.close()

    rows = list(session.execute(select(PaperAuthorshipMetadata)).scalars())
    assert summary["status"] == "succeeded"
    assert len(rows) == 2
    assert len({row.author_id for row in rows}) == 2
    assert any(
        "same_name_authors_disambiguated_per_paper" in row.quality_flags for row in rows
    )


def test_repeated_openalex_identity_is_idempotent(session, tmp_path):
    path = tmp_path / "tier1.csv"
    _write_csv(path)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/works":
            return httpx.Response(404, json={})
        uoft = _institution(
            "University of Toronto",
            openalex_id="https://openalex.org/I185261750",
            ror="https://ror.org/03dbr7087",
            country_code="CA",
        )
        repeated = _authorship(
            "Repeated Identity",
            "https://openalex.org/A-REPEATED",
            "first",
            [uoft],
        )
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "https://openalex.org/W-REPEATED",
                        "doi": "https://doi.org/10.test/one",
                        "title": "Paper one",
                        "publication_year": 2024,
                        "authorships": [
                            repeated,
                            {**repeated, "author_position": "last"},
                        ],
                    }
                ]
            },
        )

    openalex = OpenAlexClient(transport=httpx.MockTransport(handler))
    crossref = CrossrefClient(transport=httpx.MockTransport(_unexpected_handler))
    ror = RorClient(transport=httpx.MockTransport(_unexpected_handler))
    try:
        first = run_tier1_metadata_agent(
            session,
            path,
            openalex=openalex,
            crossref=crossref,
            ror=ror,
            max_papers=1,
        )
        second = run_tier1_metadata_agent(
            session,
            path,
            openalex=openalex,
            crossref=crossref,
            ror=ror,
            max_papers=1,
        )
    finally:
        openalex.close()
        crossref.close()
        ror.close()

    rows = list(session.execute(select(PaperAuthorshipMetadata)).scalars())
    assert first["status"] == "succeeded"
    assert second["status"] == "succeeded"
    assert len(rows) == 2
    assert session.scalar(select(func.count(Author.id))) == 2
