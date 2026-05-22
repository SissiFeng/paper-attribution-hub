"""Source-reliability ranking (newidea.md §"二、4").

When the same metadata field (title / authors / year / DOI / affiliations)
arrives from multiple sources, we keep the one from the most trustworthy
source. The ranking is explicit so future tuning is a one-line edit.

Trust order (highest → lowest):
  1. internal          — curated by humans / committed to our repo
  2. crossref          — authoritative DOI registry
  3. openalex          — well-maintained, structured
  4. semantic_scholar  — broad coverage but noisier
  5. pdf               — PyMuPDF + regex (no structure guarantees)
  6. llm               — speculative; never used as a primary source
"""
from __future__ import annotations

from dataclasses import dataclass

SOURCE_TRUST: dict[str, int] = {
    "internal": 100,
    "csv": 100,            # CSV ingest = curated
    "manual_upload": 95,
    "crossref": 80,
    "grobid": 75,          # structured PDF parse beats heuristic
    "openalex": 70,
    "semantic_scholar": 60,
    "pdf": 40,
    "pymupdf": 40,
    "llm": 20,
    "discovered_auto": 50,  # auto-discovered; pending review
    "discovered_approved": 90,  # human said yes
}


def trust(source: str) -> int:
    return SOURCE_TRUST.get(source, 30)


@dataclass(order=True)
class _Candidate:
    rank: int
    value: object


def pick_best(
    *fields: tuple[str, object | None],
) -> object | None:
    """Given (source, value) tuples, return the value from the highest-trust
    non-empty source. Falls back to None when everything is empty."""
    best: _Candidate | None = None
    for source, value in fields:
        if value is None or value == "" or value == []:
            continue
        rank = trust(source)
        if best is None or rank > best.rank:
            best = _Candidate(rank, value)
    return best.value if best is not None else None


def merge_paper_records(*records) -> dict:
    """Merge multiple PaperRecord-like dicts/objects into one canonical view.

    Each field independently picks the highest-trust source that has a
    non-empty value. The output is a plain dict because the caller decides
    what to do with it (write to discovery_candidates, hand to ingestion,
    or display in the UI).
    """
    if not records:
        return {}

    def get(rec, field):
        return getattr(rec, field, None) if not isinstance(rec, dict) else rec.get(field)

    sources = [get(r, "source") or "unknown" for r in records]
    fields = (
        "paper_id",
        "title",
        "abstract",
        "doi",
        "year",
        "venue",
        "authors",
        "affiliations",
        "keywords",
    )
    out: dict = {}
    for field in fields:
        candidates = [(s, get(r, field)) for s, r in zip(sources, records)]
        out[field] = pick_best(*candidates)
    out["sources"] = sources
    return out
