"""OpenAlex client.

OpenAlex's free Work / Author / Institution / Concept entities cover most
of what we need for discovery. Endpoints we use:

  GET /works/doi:10.xxx            → Work by DOI
  GET /works/W{id}                 → Work by OpenAlex id
  GET /works?filter=cites:W{id}    → papers citing a given work
  GET /works?filter=author.id:A{id}→ papers by an author
  GET /authors?search=Name         → author search (disambiguation)
  GET /institutions?search=Name    → institution lookup

Polite-pool: pass `mailto` to get higher rate limits. The base class adds
it via the User-Agent header.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Iterator

from sqlalchemy.orm import Session

from app.adapters.base import PaperRecord
from app.config import settings
from app.services.external.base import ExternalClient
from app.services.external.cache import cached_get
from app.services.normalization_service import normalize_doi


class OpenAlexClient(ExternalClient):
    name = "openalex"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(base_url=settings.openalex_url, **kwargs)

    # ------- low-level cached calls -------

    def _cached(
        self, session: Session, path: str, params: dict[str, Any] | None = None
    ) -> dict:
        key = self.request_key(path, params)
        # OpenAlex polite pool wants the email as a query parameter when
        # mailto is set — header alone is OK but the query param is what
        # docs recommend.
        if self.polite_mailto:
            params = {**(params or {}), "mailto": self.polite_mailto}
        if settings.openalex_api_key:
            params = {**(params or {}), "api_key": settings.openalex_api_key}
        return cached_get(
            session,
            self.name,
            key,
            lambda: self.fetch_raw(path, params=params),
            ttl=timedelta(hours=settings.external_cache_ttl_hours),
        )

    # ------- public API -------

    def work_by_doi(self, session: Session, doi: str) -> dict | None:
        doi_norm = normalize_doi(doi)
        if not doi_norm:
            return None
        return self._cached(session, f"/works/doi:{doi_norm}")

    def works_by_dois(
        self,
        session: Session,
        dois: list[str],
        *,
        batch_size: int = 100,
    ) -> dict[str, dict]:
        """Fetch known DOIs in bounded OR-filter batches.

        OpenAlex permits at most 100 OR values in one filter. Results are
        returned by normalized DOI so callers can reconcile them without
        relying on response order.
        """
        normalized = sorted(
            {doi for value in dois if (doi := normalize_doi(value))}
        )
        if batch_size < 1 or batch_size > 100:
            raise ValueError("batch_size must be between 1 and 100")
        selected_fields = ",".join(
            [
                "id",
                "doi",
                "title",
                "display_name",
                "publication_year",
                "publication_date",
                "type",
                "language",
                "cited_by_count",
                "is_retracted",
                "authorships",
                "ids",
                "biblio",
                "primary_location",
                "open_access",
                "topics",
                "keywords",
                "abstract_inverted_index",
            ]
        )
        by_doi: dict[str, dict] = {}
        for offset in range(0, len(normalized), batch_size):
            batch = normalized[offset : offset + batch_size]
            payload = self._cached(
                session,
                "/works",
                {
                    "filter": "doi:" + "|".join(batch),
                    "per_page": len(batch),
                    "select": selected_fields,
                },
            )
            for work in payload.get("results") or []:
                doi = normalize_doi(work.get("doi"))
                if doi:
                    by_doi[doi] = work
        return by_doi

    def work_by_id(self, session: Session, openalex_work_id: str) -> dict | None:
        work_id = (openalex_work_id or "").strip().rsplit("/", 1)[-1]
        if not work_id:
            return None
        return self._cached(session, f"/works/{work_id}")

    def papers_citing(
        self, session: Session, openalex_work_id: str, per_page: int = 25
    ) -> Iterator[dict]:
        """Yield Work dicts for papers that cite the given Work id."""
        page = 1
        while True:
            payload = self._cached(
                session,
                "/works",
                {
                    "filter": f"cites:{openalex_work_id}",
                    "per-page": per_page,
                    "page": page,
                },
            )
            results = payload.get("results", []) or []
            for r in results:
                yield r
            if len(results) < per_page or page >= 4:
                # Hard cap at 4 pages to avoid runaway calls during demos.
                break
            page += 1

    def papers_by_author(
        self, session: Session, openalex_author_id: str, per_page: int = 25
    ) -> Iterator[dict]:
        page = 1
        while True:
            payload = self._cached(
                session,
                "/works",
                {
                    "filter": f"author.id:{openalex_author_id}",
                    "per-page": per_page,
                    "page": page,
                },
            )
            results = payload.get("results", []) or []
            for r in results:
                yield r
            if len(results) < per_page or page >= 4:
                break
            page += 1

    def search_author(
        self, session: Session, name: str, orcid: str | None = None
    ) -> list[dict]:
        """Best-effort author disambiguation. ORCID takes precedence."""
        if orcid:
            payload = self._cached(session, f"/authors/orcid:{orcid}")
            return [payload] if payload else []
        payload = self._cached(session, "/authors", {"search": name, "per-page": 5})
        return payload.get("results", []) or []

    def search_institution(self, session: Session, name: str) -> list[dict]:
        payload = self._cached(
            session, "/institutions", {"search": name, "per-page": 5}
        )
        return payload.get("results", []) or []


# ---------------------------------------------------------------------------
# Normalization helpers — Work dict → PaperRecord (the same shape our CSV
# adapter emits, so downstream ingestion code doesn't need to change).
# ---------------------------------------------------------------------------


def work_to_paper_record(work: dict, source: str = "openalex") -> PaperRecord:
    """Convert an OpenAlex Work into our internal PaperRecord."""
    doi = normalize_doi(work.get("doi"))
    title = (work.get("title") or "").strip()
    abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))
    year = work.get("publication_year")
    venue = None
    host_venue = work.get("primary_location") or {}
    if host_venue:
        source_obj = host_venue.get("source") or {}
        venue = source_obj.get("display_name")

    authors: list[str] = []
    affiliations: list[str] = []
    for authorship in work.get("authorships") or []:
        author_name = (authorship.get("author") or {}).get("display_name")
        if author_name:
            authors.append(author_name)
        # Pull the *first* institution per authorship for our positional
        # affiliation array (matches the CSV adapter convention).
        insts = authorship.get("institutions") or []
        affil = insts[0].get("display_name") if insts else None
        affiliations.append(affil or "")

    # `keywords` aren't a first-class OpenAlex field; we fall back to top
    # concepts above a confidence threshold.
    keywords = [
        c.get("display_name")
        for c in (work.get("concepts") or [])[:8]
        if (c.get("score") or 0) > 0.3 and c.get("display_name")
    ]

    paper_id = _stable_id_from_doi_or_openalex(doi, work.get("id"))

    return PaperRecord(
        paper_id=paper_id,
        title=title,
        abstract=abstract,
        authors=authors,
        affiliations=affiliations,
        year=int(year) if year else None,
        doi=doi,
        venue=venue,
        keywords=[k for k in keywords if k],
        source=source,
        raw={"openalex_id": work.get("id"), "raw": work},
    )


def _reconstruct_abstract(inverted: dict | None) -> str | None:
    """OpenAlex stores abstracts as inverted indexes; flatten back to text."""
    if not inverted:
        return None
    positions: dict[int, str] = {}
    for word, idxs in inverted.items():
        for i in idxs:
            positions[i] = word
    if not positions:
        return None
    ordered = sorted(positions.items())
    return " ".join(w for _, w in ordered)


def _stable_id_from_doi_or_openalex(doi: str | None, openalex_id: str | None) -> str:
    """Build a paper_id from the most stable available identifier."""
    if doi:
        # Compress to a reasonable length, sanitize for SQL.
        return "DOI:" + doi.replace("/", "_")
    if openalex_id:
        return openalex_id.rsplit("/", 1)[-1]
    raise ValueError("Cannot mint a paper id without DOI or OpenAlex id")
