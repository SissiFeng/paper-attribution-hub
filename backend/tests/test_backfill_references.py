"""Tests for the OpenAlex reference backfill. No live HTTP — MockTransport."""
import httpx

from app.models import Paper, PaperReference
from app.models.sdl import PaperLabLink, SdlLab
from app.scripts.backfill_references import backfill_references
from app.services.external.openalex_client import OpenAlexClient

from tests.fixtures.external_responses import openalex_work

# P1 cites P2 (in corpus) and one external work; P2 cites nothing we know.
_WORKS = {
    "10.test/p1": {
        **openalex_work(doi="10.test/p1", openalex_id="W1"),
        "referenced_works": [
            "https://openalex.org/W2",
            "https://openalex.org/W999",
        ],
    },
    "10.test/p2": {
        **openalex_work(doi="10.test/p2", openalex_id="W2"),
        "referenced_works": [],
    },
}


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if "/works/doi:" in path:
        doi = path.split("/works/doi:")[-1]
        work = _WORKS.get(doi)
        if work:
            return httpx.Response(200, json=work)
        return httpx.Response(404, json={})
    return httpx.Response(404, json={})


def _seed(session):
    lab = SdlLab(
        id="lab-a", name="Lab A", institution="UofT", pi_names=["A"], domain_focus=""
    )
    session.add(lab)
    for pid, doi in [("P1", "10.test/p1"), ("P2", "10.test/p2"), ("P3", None)]:
        session.add(Paper(id=pid, title=f"Paper {pid}", doi=doi))
        session.add(
            PaperLabLink(paper_id=pid, lab_id="lab-a", source="manual", confidence=1.0)
        )
    session.commit()


def test_backfill_creates_corpus_internal_edges(session):
    _seed(session)
    client = OpenAlexClient(transport=httpx.MockTransport(_handler))
    summary = backfill_references(session, client)

    # P3 has no DOI and is excluded from targeting.
    assert summary["papers_targeted"] == 2
    assert summary["works_fetched"] == 2
    assert summary["edges_created"] == 1

    refs = session.query(PaperReference).all()
    assert len(refs) == 1
    ref = refs[0]
    assert ref.citing_paper_id == "P1"
    assert ref.cited_paper_id == "P2"
    assert ref.cited_doi == "10.test/p2"
    assert ref.raw_text == "openalex:https://openalex.org/W2"


def test_backfill_is_idempotent_and_preserves_fulltext_refs(session):
    _seed(session)
    # A pre-existing reference parsed from PDF full text must survive re-runs.
    session.add(
        PaperReference(
            id="ref-pdf-1",
            citing_paper_id="P1",
            raw_text="[1] Some reference parsed from the PDF.",
        )
    )
    session.commit()

    client = OpenAlexClient(transport=httpx.MockTransport(_handler))
    first = backfill_references(session, client)
    client2 = OpenAlexClient(transport=httpx.MockTransport(_handler))
    second = backfill_references(session, client2)

    assert first["edges_created"] == 1
    assert second["edges_created"] == 1
    assert second["edges_replaced"] == 1  # replaced its own row, not the PDF one

    refs = session.query(PaperReference).order_by(PaperReference.id).all()
    assert len(refs) == 2
    assert {r.raw_text[:9] for r in refs} == {"[1] Some ", "openalex:"}
