"""Semantic Scholar Graph API client.

We use S2 primarily for its **recommendations** endpoint — given a paper id
it returns "papers like this", which is exactly what we want for the
"missed-paper discovery" use case in newidea.md.

S2 endpoints:
  GET /paper/{id}                          → paper metadata
  GET /paper/{id}/recommendations          → similar papers
  GET /paper/search?query=...              → search
  GET /paper/{id}/citations                → papers citing this one (alt to OA)

ID forms supported by S2: DOI:10.xxx, S2 paperId (40-char hex), arXiv:xxx,
URL, etc. We standardize on `DOI:{doi}` because that's what we already have.
"""
from __future__ import annotations

import os
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.adapters.base import PaperRecord
from app.config import settings
from app.services.external.base import ExternalClient
from app.services.external.cache import cached_get
from app.services.normalization_service import normalize_doi


class SemanticScholarClient(ExternalClient):
    name = "semantic_scholar"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(base_url=settings.semantic_scholar_url, **kwargs)
        api_key = (
            kwargs.get("api_key")
            or os.environ.get("PAS_SEMANTIC_SCHOLAR_API_KEY")
            or settings.semantic_scholar_api_key
        )
        if api_key:
            self._client.headers["x-api-key"] = api_key

    PAPER_FIELDS = (
        "paperId,externalIds,title,abstract,year,venue,authors,"
        "referenceCount,citationCount"
    )

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

    def paper_by_doi(self, session: Session, doi: str) -> dict | None:
        doi_norm = normalize_doi(doi)
        if not doi_norm:
            return None
        return self._cached(
            session, f"/paper/DOI:{doi_norm}", {"fields": self.PAPER_FIELDS}
        )

    def recommendations(
        self, session: Session, doi: str, limit: int = 25
    ) -> list[dict]:
        doi_norm = normalize_doi(doi)
        if not doi_norm:
            return []
        # The recommendations endpoint actually lives at a different base
        # (recommendations.semanticscholar.org/v1/papers/forpaper/...), but
        # we call it through `/recommendations/v1/papers/forpaper/DOI:...`
        # which the graph host proxies.
        payload = self._cached(
            session,
            f"/recommendations/v1/papers/forpaper/DOI:{doi_norm}",
            {"limit": limit, "fields": self.PAPER_FIELDS},
        )
        return payload.get("recommendedPapers", []) or []

    def papers_by_author_search(
        self, session: Session, name: str, limit: int = 10
    ) -> list[dict]:
        payload = self._cached(
            session,
            "/author/search",
            {"query": name, "limit": limit, "fields": "authorId,name,affiliations"},
        )
        return payload.get("data", []) or []


# ---------------------------------------------------------------------------
# Normalization: S2 paper → PaperRecord
# ---------------------------------------------------------------------------


def s2_paper_to_record(paper: dict, source: str = "semantic_scholar") -> PaperRecord:
    doi = None
    ext = paper.get("externalIds") or {}
    if "DOI" in ext:
        doi = normalize_doi(ext["DOI"])
    authors = [a.get("name") for a in (paper.get("authors") or []) if a.get("name")]
    affiliations = [""] * len(authors)
    year = paper.get("year")
    paper_id = (
        f"DOI:{doi.replace('/', '_')}"
        if doi
        else f"S2:{paper.get('paperId')}"
    )
    return PaperRecord(
        paper_id=paper_id,
        title=(paper.get("title") or "").strip(),
        abstract=paper.get("abstract"),
        authors=authors,
        affiliations=affiliations,
        year=int(year) if year else None,
        doi=doi,
        venue=paper.get("venue"),
        keywords=[],
        source=source,
        raw={"s2_paperId": paper.get("paperId"), "raw": paper},
    )
