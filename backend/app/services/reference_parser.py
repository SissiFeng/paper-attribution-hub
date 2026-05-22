"""Parse references from a paper's References section.

v0.3 approach: regex-driven extraction. For each non-empty line of a
references section we:
  1. Pull out a DOI if present.
  2. Pull out a 4-digit year.
  3. Use the remainder as a best-effort title/author guess.

The output is a list of `ParsedReference` records that the ingestion service
joins against (a) our own papers (by DOI) and (b) the `ac_core_papers` table.

GROBID-quality structured reference parsing is a v0.4 upgrade — this is a
deliberate trade-off: the heuristic catches the signals we actually care
about for attribution (does this paper cite an AC core paper?) without
adding a Docker dep.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.normalization_service import normalize_doi

_DOI_RE = re.compile(
    r"(?:doi[:\s]*)?(10\.\d{4,9}/[A-Za-z0-9._\-;()/:]+)",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_REF_INDEX_RE = re.compile(r"^\s*(\[?\d+\]?[\.\)])?\s*")


@dataclass
class ParsedReference:
    raw_text: str
    doi: str | None = None
    title: str | None = None
    year: int | None = None
    authors: list[str] = field(default_factory=list)


def _strip_index(line: str) -> str:
    return _REF_INDEX_RE.sub("", line, count=1).strip()


def _split_references_body(text: str) -> list[str]:
    """Split a References section into candidate reference strings.

    References sections come in two formats:
      (a) one per line: "1. Foo et al. 2024."
      (b) blank-line separated: paragraph per reference
    We try numbered split first, then fall back to lines.
    """
    text = text.strip()
    if not text:
        return []
    # Numbered split (most common): split on \n followed by "<num>. " or "[num] "
    numbered = re.split(r"\n(?=\s*\[?\d{1,3}\]?[\.\)]\s)", text)
    if len(numbered) >= 2:
        return [p.strip() for p in numbered if p.strip()]
    # Otherwise fall back to line-by-line.
    return [line.strip() for line in text.splitlines() if line.strip()]


def parse_references(text: str) -> list[ParsedReference]:
    refs: list[ParsedReference] = []
    for raw_block in _split_references_body(text):
        stripped = _strip_index(raw_block)
        doi_match = _DOI_RE.search(stripped)
        doi = normalize_doi(doi_match.group(1)) if doi_match else None
        year_match = _YEAR_RE.search(stripped)
        year = int(year_match.group(0)) if year_match else None

        # Strip the DOI tail so the remainder can be a title guess.
        cleaned = stripped
        if doi_match:
            cleaned = (stripped[: doi_match.start()] + stripped[doi_match.end() :]).strip()

        # Title guess: the longest period-delimited segment that contains no
        # obvious author commas. We don't lean on it for attribution; it's
        # just there for the review UI.
        title_guess: str | None = None
        for chunk in re.split(r"[.;]\s+", cleaned):
            chunk = chunk.strip(" .")
            if len(chunk) > 12 and len(chunk.split()) >= 3 and ", " not in chunk[:30]:
                title_guess = chunk
                break

        refs.append(
            ParsedReference(
                raw_text=raw_block,
                doi=doi,
                title=title_guess,
                year=year,
            )
        )
    return refs


def extract_references_from_sections(sections) -> list[ParsedReference]:
    """Pull all references from any section whose type is 'references'."""
    out: list[ParsedReference] = []
    for sec in sections:
        if getattr(sec, "section_type", None) == "references":
            out.extend(parse_references(sec.text))
    return out
