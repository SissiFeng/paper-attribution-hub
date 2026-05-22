"""End-to-end discovery tests with fully mocked HTTP."""
import httpx
import pytest

from app.models import DiscoveryCandidate, Paper
from app.services.discovery_service import (
    approve_candidate,
    reject_candidate,
    run_discovery,
)
from app.services.external.crossref_client import CrossrefClient
from app.services.external.openalex_client import OpenAlexClient
from app.services.external.semantic_scholar_client import SemanticScholarClient

from tests.fixtures.external_responses import (
    crossref_work,
    openalex_work,
    s2_paper,
)


# A single Work fixture that combines all the signals so we can drive the
# discovery hybrid logic deterministically.
def _ac_core_work(doi="10.1126/scirobotics.aax9876", openalex_id="W_AC_CORE"):
    return openalex_work(doi=doi, openalex_id=openalex_id)


# ---------------------------------------------------------------------------
# Transports for the 3 external clients
# ---------------------------------------------------------------------------


def _make_openalex_transport():
    """Mock: each AC core DOI maps to a unique OpenAlex work id, but only
    the FIRST one has citing papers. This way each candidate accumulates
    exactly one cite_of_core trigger — below the auto threshold (2), so the
    non-ORCID candidate stays in the queue."""
    _doi_to_oa: dict[str, str] = {}

    def _oa_id_for(doi: str) -> str:
        if doi not in _doi_to_oa:
            _doi_to_oa[doi] = f"W_AC_{len(_doi_to_oa)}"
        return _doi_to_oa[doi]

    citing_target = "W_AC_0"  # only the first AC core has citing papers

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith("/works/doi:"):
            doi = path.split(":", 1)[1]
            return httpx.Response(
                200,
                json=_ac_core_work(doi=doi, openalex_id=_oa_id_for(doi)),
            )
        if path == "/works":
            f = request.url.params.get("filter", "")
            if f.startswith(f"cites:{citing_target}"):
                return httpx.Response(
                    200,
                    json={
                        "results": [
                            openalex_work(
                                doi="10.test/auto.1",
                                openalex_id="W_AUTO",
                                citing_authors=[
                                    {
                                        "name": "Alan Aspuru-Guzik",
                                        "orcid": "https://orcid.org/0000-0003-1024-3325",
                                    }
                                ],
                            ),
                            openalex_work(
                                doi="10.test/queue.1",
                                openalex_id="W_QUEUE",
                                citing_authors=[
                                    {"name": "Random Researcher"}
                                ],
                            ),
                        ]
                    },
                )
            if f.startswith("cites:") or f.startswith("author.id:"):
                return httpx.Response(200, json={"results": []})
        if path == "/authors":
            return httpx.Response(200, json={"results": []})
        if path.startswith("/authors/orcid:"):
            return httpx.Response(404, json={})
        return httpx.Response(404, json={})

    return httpx.MockTransport(handler)


def _make_s2_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"recommendedPapers": []})
    return httpx.MockTransport(handler)


def _make_crossref_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/works/"):
            doi = request.url.path.split("/works/")[-1]
            return httpx.Response(200, json=crossref_work(doi=doi))
        return httpx.Response(404, json={})
    return httpx.MockTransport(handler)


def _run(session, *, strategies=None, max_candidates=None):
    with OpenAlexClient(transport=_make_openalex_transport()) as oa, \
         SemanticScholarClient(transport=_make_s2_transport()) as s2, \
         CrossrefClient(transport=_make_crossref_transport()) as cr:
        return run_discovery(
            session,
            strategies=strategies or ["cite_of_core"],
            max_candidates=max_candidates,
            openalex=oa,
            s2=s2,
            crossref=cr,
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_hybrid_splits_auto_vs_queue(seeded_session):
    result = _run(seeded_session)
    assert result.candidates_seen == 2
    assert result.auto_ingested >= 1  # the ORCID-matched one
    assert result.queued >= 1


def test_auto_ingested_paper_lands_in_corpus_with_provenance(seeded_session):
    _run(seeded_session)
    # v0.7 splits auto provenance into discovered_auto / _high / _low based on
    # confidence; any of them count as "auto".
    auto_papers = [
        p for p in seeded_session.query(Paper).all()
        if p.provenance and p.provenance.startswith("discovered_auto")
    ]
    assert auto_papers
    assert any(p.doi == "10.test/auto.1" for p in auto_papers)


def test_queued_candidate_can_be_approved(seeded_session):
    _run(seeded_session)
    queued = (
        seeded_session.query(DiscoveryCandidate)
        .filter(DiscoveryCandidate.status == "queued")
        .first()
    )
    assert queued is not None
    paper = approve_candidate(seeded_session, queued.id, reviewer="ssf")
    assert paper.provenance == "discovered_approved"
    # Candidate row is updated.
    refreshed = seeded_session.get(DiscoveryCandidate, queued.id)
    assert refreshed.status == "approved"
    assert refreshed.resulting_paper_id == paper.id


def test_queued_candidate_can_be_rejected(seeded_session):
    _run(seeded_session)
    queued = (
        seeded_session.query(DiscoveryCandidate)
        .filter(DiscoveryCandidate.status == "queued")
        .first()
    )
    reject_candidate(seeded_session, queued.id, reviewer="ssf", notes="not AC")
    refreshed = seeded_session.get(DiscoveryCandidate, queued.id)
    assert refreshed.status == "rejected"
    assert refreshed.review_notes == "not AC"


def test_existing_doi_is_skipped(seeded_session):
    # Add a paper with one of the mocked DOIs so it should be skipped.
    from app.adapters.base import PaperRecord
    from app.adapters.csv_source import CsvPaperSource  # noqa: F401  (import side effects)

    seeded_session.add(
        Paper(
            id="P_EXISTING",
            title="Already here",
            doi="10.test/auto.1",
            provenance="csv",
        )
    )
    seeded_session.commit()
    result = _run(seeded_session)
    assert result.skipped_already_in_corpus >= 1
    # The auto paper shouldn't have been duplicated.
    assert seeded_session.query(Paper).filter(
        Paper.doi == "10.test/auto.1"
    ).count() == 1


def test_triggers_merge_when_same_paper_hit_by_multiple_strategies(seeded_session):
    """If two strategies surface the same external_id, triggers should
    merge rather than create duplicate candidate rows."""
    _run(seeded_session, strategies=["cite_of_core", "ac_coauthor"])
    cnt = seeded_session.query(DiscoveryCandidate).filter(
        DiscoveryCandidate.external_id == "10.test/auto.1"
    ).count()
    # The same paper appearing via multiple strategies still collapses to a
    # single candidate row.
    assert cnt == 0 or cnt == 1
