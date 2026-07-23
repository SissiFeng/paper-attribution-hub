"""Candidate ranking for full-text fetch.

Turns the serial 'first registry that returns a PDF wins' chain into a ranked
aggregation: prefer parseable formats (JATS/XML/HTML over PDF), licensed OA,
the requested version, and reliable provenance. Deduplicates candidates that
point at the same URL so three registries naming one file rank as one.
"""

from __future__ import annotations

from app.services.fetch_ranking import FetchCandidate, rank_candidates


def _c(source, fmt, *, url=None, version=None, license=None, is_oa=True):
    return FetchCandidate(
        source=source,
        url=url or f"http://ex/{source}/{fmt}",
        version=version,
        license=license,
        fmt=fmt,
        is_oa=is_oa,
    )


def test_jats_xml_ranks_above_pdf():
    ranked = rank_candidates([_c("openalex", "pdf"), _c("pmc", "jats_xml")])
    assert ranked[0].candidate.fmt == "jats_xml"


def test_licensed_oa_ranks_above_unknown_license():
    ranked = rank_candidates(
        [_c("a", "pdf", url="u1"), _c("b", "pdf", url="u2", license="cc-by")]
    )
    assert ranked[0].candidate.license == "cc-by"


def test_prefers_requested_version():
    ranked = rank_candidates(
        [_c("a", "pdf", url="u1", version="published"),
         _c("b", "pdf", url="u2", version="accepted")],
        prefer_version="accepted",
    )
    assert ranked[0].candidate.version == "accepted"


def test_dedup_collapses_same_url():
    ranked = rank_candidates(
        [_c("openalex", "pdf", url="http://same/x"),
         _c("unpaywall", "pdf", url="http://same/x")]
    )
    assert len(ranked) == 1


def test_drops_non_oa_candidates():
    ranked = rank_candidates([_c("a", "pdf", url="u1", is_oa=False),
                              _c("b", "html", url="u2")])
    assert len(ranked) == 1
    assert ranked[0].candidate.source == "b"


def test_results_are_scored_and_sorted_descending():
    ranked = rank_candidates([_c("openalex", "pdf"), _c("pmc", "jats_xml")])
    assert ranked[0].score >= ranked[1].score
    assert ranked[0].reasons  # per-factor breakdown present


def test_empty_input():
    assert rank_candidates([]) == []
