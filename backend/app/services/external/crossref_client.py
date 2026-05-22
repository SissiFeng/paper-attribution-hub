"""Crossref REST API client.

Crossref is the **authority** for DOIs — when OpenAlex and S2 disagree on
a paper's title / authors / year, Crossref breaks the tie. We also use the
Funder Registry to canonicalize funder names mentioned in acknowledgements
("Acceleration Consortium" appears in Crossref's funder list, so we can
resolve it to a canonical Funder DOI when one exists).

Endpoints:
  GET /works/{doi}                → work metadata
  GET /funders?query=...          → funder lookup
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.adapters.base import PaperRecord
from app.config import settings
from app.services.external.base import ExternalClient
from app.services.external.cache import cached_get
from app.services.normalization_service import normalize_doi


class CrossrefClient(ExternalClient):
    name = "crossref"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(base_url=settings.crossref_url, **kwargs)

    def _cached(
        self, session: Session, path: str, params: dict[str, Any] | None = None
    ) -> dict:
        key = self.request_key(path, params)
        return cached_get(
            session,
            self.name,
            key,
            lambda: self.fetch_raw(path, params=params),
            ttl=timedelta(hours=settings.external_cache_ttl_hours),
        )

    def work_by_doi(self, session: Session, doi: str) -> dict | None:
        doi_norm = normalize_doi(doi)
        if not doi_norm:
            return None
        payload = self._cached(session, f"/works/{doi_norm}")
        return payload.get("message") if payload else None

    def search_funder(self, session: Session, name: str) -> list[dict]:
        payload = self._cached(
            session, "/funders", {"query": name, "rows": 5}
        )
        return ((payload.get("message") or {}).get("items") or [])


def crossref_work_to_record(
    work: dict, source: str = "crossref"
) -> PaperRecord:
    doi = normalize_doi(work.get("DOI"))
    title_list = work.get("title") or []
    title = title_list[0] if title_list else ""
    authors: list[str] = []
    affiliations: list[str] = []
    for a in work.get("author") or []:
        given = (a.get("given") or "").strip()
        family = (a.get("family") or "").strip()
        full = f"{given} {family}".strip()
        if full:
            authors.append(full)
        aff_list = a.get("affiliation") or []
        first_aff = aff_list[0].get("name") if aff_list else ""
        affiliations.append(first_aff or "")
    issued = (work.get("issued") or {}).get("date-parts") or [[]]
    year = issued[0][0] if issued and issued[0] else None
    venue = None
    for key in ("container-title", "publisher"):
        vals = work.get(key)
        if vals:
            venue = vals[0] if isinstance(vals, list) else vals
            break

    paper_id = (
        f"DOI:{doi.replace('/', '_')}" if doi else f"CR:{work.get('URL', '?')[-32:]}"
    )
    return PaperRecord(
        paper_id=paper_id,
        title=title,
        abstract=work.get("abstract"),
        authors=authors,
        affiliations=affiliations,
        year=int(year) if year else None,
        doi=doi,
        venue=venue,
        keywords=[],
        source=source,
        raw={"crossref": work},
    )
