"""Identity-gated candidate fetch loop.

Rank candidates, fetch the best, verify it is the target paper, and fall through
to the next on a mismatch. The network fetch is injected so the loop is testable
and does not couple to the fetch pipeline.
"""

from __future__ import annotations

from app.services.document_identity import DocIdentity
from app.services.fetch_orchestrator import FetchedDoc, fetch_best_document
from app.services.fetch_ranking import FetchCandidate


def _cand(source, fmt, url):
    return FetchCandidate(source=source, url=url, fmt=fmt, license="cc-by")


TARGET = DocIdentity(title="Self-driving labs", authors=["Smith"], doi="10.1/x")


def test_accepts_first_matching_candidate_and_stops():
    calls: list[str] = []

    def fetch_fn(candidate):
        calls.append(candidate.url)
        return FetchedDoc(identity=DocIdentity(title="anything", doi="10.1/x"))

    out = fetch_best_document(
        [_cand("pmc", "jats_xml", "u1"), _cand("oa", "pdf", "u2")],
        TARGET,
        fetch_fn=fetch_fn,
    )
    assert out.status == "ACCEPTED_MATCH"
    assert out.accepted.candidate.url == "u1"  # best-ranked (xml) tried first
    assert calls == ["u1"]  # stopped after the match


def test_falls_through_mismatch_to_next_candidate():
    def fetch_fn(candidate):
        if candidate.url == "u1":
            return FetchedDoc(identity=DocIdentity(title="x", doi="10.9/other"))
        return FetchedDoc(identity=DocIdentity(title="x", doi="10.1/x"))

    out = fetch_best_document(
        [_cand("pmc", "jats_xml", "u1"), _cand("oa", "pdf", "u2")],
        TARGET,
        fetch_fn=fetch_fn,
    )
    assert out.status == "ACCEPTED_MATCH"
    assert out.accepted.candidate.url == "u2"


def test_all_mismatch_is_rejected():
    def fetch_fn(candidate):
        return FetchedDoc(identity=DocIdentity(title="x", doi="10.9/other"))

    out = fetch_best_document([_cand("a", "pdf", "u1")], TARGET, fetch_fn=fetch_fn)
    assert out.status == "REJECTED_ALL"
    assert out.accepted is None


def test_uncertain_accepted_as_fallback_when_allowed():
    # Title match, disjoint authors, no DOI on fetched -> UNCERTAIN.
    target = DocIdentity(title="A study of catalysis", authors=["Smith"])

    def fetch_fn(candidate):
        return FetchedDoc(
            identity=DocIdentity(title="A study of catalysis", authors=["Kim"])
        )

    accepted = fetch_best_document(
        [_cand("a", "pdf", "u1")], target, fetch_fn=fetch_fn, accept_uncertain=True
    )
    assert accepted.status == "ACCEPTED_UNCERTAIN"

    rejected = fetch_best_document(
        [_cand("a", "pdf", "u1")], target, fetch_fn=fetch_fn, accept_uncertain=False
    )
    assert rejected.status == "REJECTED_ALL"


def test_failed_fetch_is_skipped():
    def fetch_fn(candidate):
        return None if candidate.url == "u1" else FetchedDoc(
            identity=DocIdentity(doi="10.1/x")
        )

    out = fetch_best_document(
        [_cand("pmc", "jats_xml", "u1"), _cand("oa", "pdf", "u2")],
        TARGET,
        fetch_fn=fetch_fn,
    )
    assert out.status == "ACCEPTED_MATCH"
    assert out.accepted.candidate.url == "u2"
    assert any(a.parse_ok is False for a in out.attempts)


def test_no_candidates():
    out = fetch_best_document([], TARGET, fetch_fn=lambda c: None)
    assert out.status == "NO_CANDIDATES"
