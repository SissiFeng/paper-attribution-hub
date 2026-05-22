"""Tests for the v0.6 missed-paper grouped view. Relies on v0.5 discovery
candidates seeded via mocked HTTP."""
import httpx

from app.models import DiscoveryCandidate
from app.services.discovery_service import run_discovery
from app.services.external.crossref_client import CrossrefClient
from app.services.external.openalex_client import OpenAlexClient
from app.services.external.semantic_scholar_client import SemanticScholarClient
from app.services.missed_papers_service import build_missed_paper_groups

from tests.fixtures.external_responses import crossref_work, openalex_work


def _seed_candidates(session):
    """Run a discovery cycle that injects candidates with different trigger
    profiles so we can verify the grouping logic."""

    _oa_id: dict[str, str] = {}

    def oa_handler(request):
        path = request.url.path
        if path.startswith("/works/doi:"):
            doi = path.split(":", 1)[1]
            oid = _oa_id.setdefault(doi, f"W{len(_oa_id)}")
            return httpx.Response(200, json=openalex_work(doi=doi, openalex_id=oid))
        if path == "/works":
            f = request.url.params.get("filter", "")
            # Different AC cores return different cited papers so we get
            # candidates with multiple-cite triggers.
            if f.startswith("cites:W0") or f.startswith("cites:W1"):
                return httpx.Response(
                    200,
                    json={
                        "results": [
                            openalex_work(
                                doi="10.miss/shared",
                                openalex_id="W_SHARED",
                                citing_authors=[
                                    {"name": "Some Author", "institution": "Random Lab"}
                                ],
                            ),
                        ]
                    },
                )
            return httpx.Response(200, json={"results": []})
        return httpx.Response(200, json={"results": []})

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
        run_discovery(
            session,
            strategies=["cite_of_core"],
            openalex=oa,
            s2=s2,
            crossref=cr,
        )


def test_missed_paper_groups_have_descriptions(seeded_session):
    _seed_candidates(seeded_session)
    # Inject an extra candidate that simulates an AC-partner affiliation.
    seeded_session.add(
        DiscoveryCandidate(
            id="disc_test_partner",
            external_id="10.partner/test",
            doi="10.partner/test",
            title="Mock UofT paper",
            authors=[{"name": "X"}],
            affiliations=["University of Toronto"],
            source="openalex",
            triggers=[
                {"strategy": "cite_of_core", "source": "openalex", "detail": "x", "weight": 0.5}
            ],
            confidence=0.5,
            status="queued",
        )
    )
    seeded_session.commit()

    groups = build_missed_paper_groups(seeded_session, status="queued")
    by_key = {g.key: g for g in groups}
    assert "partner_institution" in by_key
    partner_group = by_key["partner_institution"]
    assert "disc_test_partner" in partner_group.candidate_ids
    # Each group has a non-empty description for the UI.
    for g in groups:
        assert g.description
        assert g.label
