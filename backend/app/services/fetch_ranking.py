"""Rank full-text OA candidates before fetching.

Given all legal OA candidates for one paper (already resolved from its
identifiers), decide the try-order. Parseability dominates: JATS/XML and HTML
carry acknowledgements and references far more reliably than a publisher PDF,
which is often a scanned or hard-to-parse layout. Licensed OA, the requested
version, and reliable provenance break ties.

Pure and dependency-free; the fetch pipeline calls this to order downloads,
then verifies each fetched document with ``document_identity.verify_identity``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Parseability of a format for evidence extraction (acks/refs/funding).
_FORMAT_QUALITY = {
    "jats_xml": 1.0,
    "xml": 0.95,
    "html": 0.80,
    "pdf": 0.50,
    "metadata": 0.10,
}
# Mild default version preference; the requested version adds a match bonus.
_VERSION_QUALITY = {
    "published": 0.90,
    "publishedversion": 0.90,
    "accepted": 0.85,
    "acceptedversion": 0.85,
    "preprint": 0.60,
    "submittedversion": 0.60,
}
_SOURCE_QUALITY = {
    "pmc": 0.95,
    "europepmc": 0.95,
    "publisher": 1.0,
    "repository": 0.85,
    "openaire": 0.85,
    "openalex": 0.80,
    "unpaywall": 0.80,
    "core": 0.75,
    "arxiv": 0.70,
    "s2": 0.70,
    "semantic_scholar": 0.70,
}
_DEFAULT_QUALITY = 0.6


@dataclass(frozen=True)
class FetchCandidate:
    source: str
    url: str
    version: str | None = None
    license: str | None = None
    fmt: str | None = None
    is_oa: bool = True


@dataclass(frozen=True)
class RankedCandidate:
    candidate: FetchCandidate
    score: float
    reasons: dict[str, float] = field(default_factory=dict)


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def _score(candidate: FetchCandidate, prefer_version: str | None) -> RankedCandidate:
    fmt_q = _FORMAT_QUALITY.get(_norm(candidate.fmt), _DEFAULT_QUALITY)
    ver_q = _VERSION_QUALITY.get(_norm(candidate.version), 0.5)
    src_q = _SOURCE_QUALITY.get(_norm(candidate.source), _DEFAULT_QUALITY)
    legal = 1.0 if candidate.license else 0.7  # OA but unknown license is weaker
    version_match = (
        0.1 if prefer_version and _norm(candidate.version) == _norm(prefer_version) else 0.0
    )
    reasons = {
        "format_quality": round(fmt_q, 3),
        "version_quality": round(ver_q, 3),
        "source_quality": round(src_q, 3),
        "legal_access": legal,
        "version_match": version_match,
    }
    score = round(
        0.40 * fmt_q
        + 0.20 * ver_q
        + 0.15 * src_q
        + 0.15 * legal
        + version_match,
        4,
    )
    return RankedCandidate(candidate=candidate, score=score, reasons=reasons)


def rank_candidates(
    candidates: list[FetchCandidate],
    *,
    prefer_version: str | None = None,
) -> list[RankedCandidate]:
    """Return legal candidates, deduplicated by URL, best-first.

    Non-OA candidates are dropped. Ties break by format then source name for a
    deterministic order.
    """
    seen: set[str] = set()
    ranked: list[RankedCandidate] = []
    for candidate in candidates:
        if not candidate.is_oa:
            continue
        key = candidate.url.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        ranked.append(_score(candidate, prefer_version))

    ranked.sort(
        key=lambda r: (-r.score, _norm(r.candidate.fmt), _norm(r.candidate.source))
    )
    return ranked
