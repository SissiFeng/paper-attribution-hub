"""Smoke-test the /discovery endpoints with mocked HTTP and a seeded DB.

We don't call /discovery/run via the API here (it would need monkey-patched
client classes); the lower-level service is exercised in test_discovery_service.
Here we focus on queue listing + approve + reject.
"""
import httpx
from fastapi.testclient import TestClient

from app.services.discovery_service import run_discovery
from app.services.external.crossref_client import CrossrefClient
from app.services.external.openalex_client import OpenAlexClient
from app.services.external.semantic_scholar_client import SemanticScholarClient

from tests.fixtures.external_responses import crossref_work, openalex_work


def _setup_discovery(session):
    _doi_to_oa: dict[str, str] = {}

    def oa_handler(request):
        if request.url.path.startswith("/works/doi:"):
            doi = request.url.path.split(":", 1)[1]
            oa_id = _doi_to_oa.setdefault(doi, f"W_API_{len(_doi_to_oa)}")
            return httpx.Response(200, json=openalex_work(doi=doi, openalex_id=oa_id))
        if request.url.path == "/works":
            f = request.url.params.get("filter", "")
            # Only the first AC core's work_id gets citing papers.
            if f.startswith("cites:W_API_0"):
                return httpx.Response(200, json={"results": [
                    openalex_work(doi="10.api/queued", openalex_id="W2", citing_authors=[{"name": "Random"}])
                ]})
            return httpx.Response(200, json={"results": []})
        if request.url.path == "/authors":
            return httpx.Response(200, json={"results": []})
        if request.url.path.startswith("/authors/orcid:"):
            return httpx.Response(404, json={})
        return httpx.Response(404, json={})

    def s2_handler(request):
        return httpx.Response(200, json={"recommendedPapers": []})

    def cr_handler(request):
        if request.url.path.startswith("/works/"):
            doi = request.url.path.split("/works/")[-1]
            return httpx.Response(200, json=crossref_work(doi=doi))
        return httpx.Response(404, json={})

    with OpenAlexClient(transport=httpx.MockTransport(oa_handler)) as oa, \
         SemanticScholarClient(transport=httpx.MockTransport(s2_handler)) as s2, \
         CrossrefClient(transport=httpx.MockTransport(cr_handler)) as cr:
        return run_discovery(
            session, strategies=["cite_of_core"], openalex=oa, s2=s2, crossref=cr
        )


def test_queue_endpoint_lists_queued_candidates(seeded_session):
    _setup_discovery(seeded_session)
    from app.main import app

    client = TestClient(app)
    r = client.get("/discovery/queue")
    assert r.status_code == 200
    items = r.json()
    assert items
    assert all(c["status"] == "queued" for c in items)


def test_approve_endpoint_promotes_candidate_to_paper(seeded_session):
    _setup_discovery(seeded_session)
    from app.main import app

    client = TestClient(app)
    queue = client.get("/discovery/queue").json()
    target = queue[0]
    r = client.post(
        f"/discovery/queue/{target['id']}/approve",
        json={"reviewer": "ssf", "notes": "looks AC-relevant"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"


def test_reject_endpoint_marks_candidate_rejected(seeded_session):
    _setup_discovery(seeded_session)
    from app.main import app

    client = TestClient(app)
    queue = client.get("/discovery/queue").json()
    target = queue[0]
    r = client.post(
        f"/discovery/queue/{target['id']}/reject",
        json={"reviewer": "ssf", "notes": "control theory not SDL"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"
