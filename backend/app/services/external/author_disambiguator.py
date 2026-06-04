"""Author disambiguation hardening (newidea2.md §1 calls this "地狱级难题").

Order of confidence:

  1. **ORCID match**           ─ definitive (when both sides have an ORCID)
  2. **OpenAlex author ID**    ─ near-definitive (we trust OpenAlex's disambig)
  3. **Name + institution**    ─ good (handles common surnames at scale)
  4. **Name + co-author**      ─ ok (network signal)
  5. **Fuzzy name only**       ─ weak; the v0.1 fuzzy matcher already covers this

This module exposes `disambiguate()` which returns a `DisambiguationMatch`
when it's confident enough to merge an external author into our DB. The
caller decides whether to act on it (the discovery service does; ingestion
does not — direct CSV/PDF authors keep the v0.1 logic).
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Author
from app.services.author_matcher import preferred_author_display_name
from app.services.normalization_service import normalize_name


@dataclass
class DisambiguationMatch:
    author_id: str
    canonical_name: str
    method: str  # "orcid" | "openalex_id" | "name_institution" | "name_coauthor"
    confidence: float  # 0..1


def disambiguate(
    session: Session,
    *,
    name: str,
    orcid: str | None = None,
    openalex_author_id: str | None = None,
    institution: str | None = None,
    coauthor_names: list[str] | None = None,
) -> DisambiguationMatch | None:
    # 1. ORCID match (most reliable)
    if orcid:
        row = session.execute(
            select(Author).where(Author.orcid == orcid)
        ).scalar_one_or_none()
        if row:
            return DisambiguationMatch(
                author_id=row.id,
                canonical_name=preferred_author_display_name(row),
                method="orcid",
                confidence=1.0,
            )

    # 2. OpenAlex author ID match (we store these in the author's `raw_metadata`)
    if openalex_author_id:
        for row in session.execute(select(Author)).scalars():
            meta = row.raw_metadata or {}
            if meta.get("openalex_id") == openalex_author_id:
                return DisambiguationMatch(
                    author_id=row.id,
                    canonical_name=preferred_author_display_name(row),
                    method="openalex_id",
                    confidence=0.95,
                )

    # 3. Name + institution
    normalized = normalize_name(name)
    if institution:
        from app.services.normalization_service import normalize_institution

        target_inst = normalize_institution(institution)
        for row in session.execute(select(Author)).scalars():
            if row.normalized_name != normalized:
                continue
            row_inst = row.institution.canonical_name if row.institution else None
            if row_inst and normalize_institution(row_inst) == target_inst:
                return DisambiguationMatch(
                    author_id=row.id,
                    canonical_name=preferred_author_display_name(row),
                    method="name_institution",
                    confidence=0.85,
                )

    # 4. Name + co-author overlap (graph signal)
    if coauthor_names:
        coauthor_norms = {normalize_name(c) for c in coauthor_names if c}
        for row in session.execute(select(Author)).scalars():
            if row.normalized_name != normalized:
                continue
            # If this author has co-authored with any name in the supplied
            # list (in our DB), count it as supporting evidence.
            their_coauthors = {
                pa2.author.canonical_name
                for pa in row.papers
                for pa2 in pa.paper.authors
                if pa2.author_id != row.id
            }
            their_coauthor_norms = {normalize_name(n) for n in their_coauthors}
            if coauthor_norms & their_coauthor_norms:
                return DisambiguationMatch(
                    author_id=row.id,
                    canonical_name=preferred_author_display_name(row),
                    method="name_coauthor",
                    confidence=0.75,
                )

    return None
