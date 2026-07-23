"""Document identity verification: is the fetched doc actually the target paper?

A wrong-document fetch is worse than a missing one — it injects false evidence
that downstream masking will faithfully treat as real. DOI is authoritative;
otherwise title/author/year are combined.
"""

from __future__ import annotations

from app.services.document_identity import DocIdentity, verify_identity


def _doc(title="", authors=(), year=None, doi=None):
    return DocIdentity(title=title, authors=list(authors), year=year, doi=doi)


def test_matching_doi_is_authoritative_match():
    v = verify_identity(
        _doc(title="X", doi="10.1/ABC"),
        _doc(title="completely different", doi="10.1/abc"),  # case-insensitive
    )
    assert v.verdict == "MATCH"
    assert v.score >= 0.95


def test_conflicting_doi_is_authoritative_mismatch():
    v = verify_identity(
        _doc(title="Same Title", authors=["Smith"], doi="10.1/aaa"),
        _doc(title="Same Title", authors=["Smith"], doi="10.1/bbb"),
    )
    assert v.verdict == "MISMATCH"
    assert v.score <= 0.1


def test_no_doi_identical_title_and_author_overlap_is_match():
    v = verify_identity(
        _doc(title="Autonomous discovery of laser materials", authors=["Alan Aspuru-Guzik"]),
        _doc(title="Autonomous discovery of laser materials", authors=["A. Aspuru-Guzik"]),
    )
    assert v.verdict == "MATCH"


def test_title_match_but_disjoint_authors_is_uncertain():
    v = verify_identity(
        _doc(title="A study of catalysis", authors=["Smith", "Jones"]),
        _doc(title="A study of catalysis", authors=["Kim", "Park"]),
    )
    assert v.verdict == "UNCERTAIN"


def test_different_title_is_mismatch():
    v = verify_identity(
        _doc(title="Self-driving labs for chemistry", authors=["Smith"]),
        _doc(title="A review of medieval poetry", authors=["Smith"]),
    )
    assert v.verdict == "MISMATCH"


def test_partial_title_plus_year_is_match():
    v = verify_identity(
        _doc(title="Bayesian optimization for catalyst screening", year=2023),
        _doc(title="Bayesian optimization catalyst screening study", year=2023),
    )
    assert v.verdict == "MATCH"


def test_sparse_metadata_is_uncertain():
    v = verify_identity(_doc(title="Optimization"), _doc(title="Optimization methods"))
    assert v.verdict == "UNCERTAIN"
