"""Tests for the OpenAlex / S2 / Crossref clients. No live HTTP — we inject
httpx.MockTransport so the clients run against canned responses."""
import httpx
import pytest

from app.services.external.crossref_client import (
    CrossrefClient,
    crossref_work_to_record,
)
from app.services.external.openalex_client import (
    OpenAlexClient,
    work_to_paper_record,
)
from app.services.external.semantic_scholar_client import (
    SemanticScholarClient,
    s2_paper_to_record,
)

from tests.fixtures.external_responses import (
    crossref_work,
    openalex_work,
    s2_paper,
)


# ---------------------------------------------------------------------------
# OpenAlex
# ---------------------------------------------------------------------------


def _openalex_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if "/works/doi:" in path:
        doi = path.split("/works/doi:")[-1]
        return httpx.Response(
            200, json=openalex_work(doi=doi, openalex_id="W12345")
        )
    if path == "/works":
        filter_q = request.url.params.get("filter", "")
        if filter_q.startswith("cites:"):
            return httpx.Response(
                200,
                json={
                    "results": [
                        openalex_work(
                            doi="10.test/cited.1",
                            openalex_id="W1",
                            citing_authors=[{"name": "Alan Aspuru-Guzik", "orcid": "https://orcid.org/0000-0003-1024-3325"}],
                        ),
                        openalex_work(
                            doi="10.test/cited.2",
                            openalex_id="W2",
                            citing_authors=[{"name": "Unknown Author"}],
                        ),
                    ]
                },
            )
        if filter_q.startswith("author.id:"):
            return httpx.Response(
                200,
                json={
                    "results": [
                        openalex_work(
                            doi="10.test/author.1",
                            openalex_id="W3",
                            citing_authors=[{"name": "Alan Aspuru-Guzik"}],
                        )
                    ]
                },
            )
    if path == "/authors":
        return httpx.Response(200, json={"results": [{"id": "https://openalex.org/A555"}]})
    if path.startswith("/authors/orcid:"):
        return httpx.Response(200, json={"id": "https://openalex.org/A555"})
    return httpx.Response(404, json={})


def test_openalex_work_by_doi(session):
    transport = httpx.MockTransport(_openalex_handler)
    with OpenAlexClient(transport=transport) as client:
        work = client.work_by_doi(session, "10.1126/scirobotics.aax9876")
        assert work["title"] == "Mock paper for W12345"


def test_openalex_papers_citing(session):
    transport = httpx.MockTransport(_openalex_handler)
    with OpenAlexClient(transport=transport) as client:
        results = list(client.papers_citing(session, "W12345"))
    assert len(results) == 2
    assert results[0]["doi"].endswith("10.test/cited.1")


def test_work_to_paper_record_extracts_doi_and_authors(session):
    transport = httpx.MockTransport(_openalex_handler)
    with OpenAlexClient(transport=transport) as client:
        work = client.work_by_doi(session, "10.test/abc")
    record = work_to_paper_record(work)
    assert record.doi == "10.test/abc"
    assert record.title.startswith("Mock paper")
    assert record.year == 2024


# ---------------------------------------------------------------------------
# Semantic Scholar
# ---------------------------------------------------------------------------


def _s2_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if "/paper/DOI:" in path:
        doi = path.split("/paper/DOI:")[-1]
        return httpx.Response(200, json=s2_paper(doi=doi))
    if "/recommendations/v1/papers/forpaper/" in path:
        return httpx.Response(
            200,
            json={
                "recommendedPapers": [
                    s2_paper(doi="10.test/rec.1", paper_id="rec1"),
                    s2_paper(doi="10.test/rec.2", paper_id="rec2"),
                ]
            },
        )
    return httpx.Response(404, json={})


def test_s2_paper_by_doi(session):
    transport = httpx.MockTransport(_s2_handler)
    with SemanticScholarClient(transport=transport) as client:
        paper = client.paper_by_doi(session, "10.test/main")
    assert paper["externalIds"]["DOI"] == "10.test/main"


def test_s2_recommendations(session):
    transport = httpx.MockTransport(_s2_handler)
    with SemanticScholarClient(transport=transport) as client:
        recs = client.recommendations(session, "10.test/seed")
    assert len(recs) == 2


def test_s2_paper_to_record(session):
    transport = httpx.MockTransport(_s2_handler)
    with SemanticScholarClient(transport=transport) as client:
        paper = client.paper_by_doi(session, "10.test/main")
    rec = s2_paper_to_record(paper)
    assert rec.doi == "10.test/main"
    assert "Jane Doe" in rec.authors


# ---------------------------------------------------------------------------
# Crossref
# ---------------------------------------------------------------------------


def _crossref_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.startswith("/works/"):
        doi = request.url.path.split("/works/")[-1]
        return httpx.Response(200, json=crossref_work(doi=doi))
    return httpx.Response(404, json={})


def test_crossref_work_by_doi(session):
    transport = httpx.MockTransport(_crossref_handler)
    with CrossrefClient(transport=transport) as client:
        work = client.work_by_doi(session, "10.test/abc")
    assert work["DOI"] == "10.test/abc"


def test_crossref_work_to_record_pulls_authors(session):
    transport = httpx.MockTransport(_crossref_handler)
    with CrossrefClient(transport=transport) as client:
        work = client.work_by_doi(session, "10.test/abc")
    rec = crossref_work_to_record(work)
    assert rec.doi == "10.test/abc"
    assert "Alan Aspuru-Guzik" in rec.authors
    assert rec.year == 2024
    assert "University of Toronto" in rec.affiliations
