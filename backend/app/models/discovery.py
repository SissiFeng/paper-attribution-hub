from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class DiscoveryCandidate(Base):
    """A paper the discovery service found in an external API that *might*
    belong to the AC corpus. Lives in this table until either auto-ingested
    or human-approved (then a row is created in `papers`).

    A single external paper may be discovered through multiple strategies
    (e.g. it cites an AC core paper AND is co-authored by Aspuru-Guzik) —
    we dedup by `external_id` and merge the `triggers` JSON list.
    """

    __tablename__ = "discovery_candidates"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    # The DOI or external work id (OpenAlex W-id, S2 paperId) used to dedup.
    external_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    doi: Mapped[str | None] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(Text)
    abstract: Mapped[str | None] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(Integer)
    venue: Mapped[str | None] = mapped_column(String)
    authors: Mapped[list[dict] | None] = mapped_column(JSON)
    affiliations: Mapped[list[str] | None] = mapped_column(JSON)

    # Where we found it.
    source: Mapped[str] = mapped_column(String, index=True)  # openalex|s2|crossref
    triggers: Mapped[list[dict]] = mapped_column(JSON)  # list of trigger dicts

    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    auto_eligible: Mapped[bool] = mapped_column(default=False, index=True)
    status: Mapped[str] = mapped_column(String, default="queued", index=True)
    # status ∈ {queued, approved, rejected, auto_ingested}

    reviewer: Mapped[str | None] = mapped_column(String)
    review_notes: Mapped[str | None] = mapped_column(Text)
    resulting_paper_id: Mapped[str | None] = mapped_column(ForeignKey("papers.id"))

    raw_payload: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExternalCache(Base):
    """Cache for external API responses. Keyed by (source, request_key).

    The request_key is a stable canonicalized form of the request — for
    OpenAlex it might be `work/doi:10.xxx`, for S2 `recommendations/p123`,
    for Crossref `works/10.xxx`.
    """

    __tablename__ = "external_cache"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String, index=True)
    request_key: Mapped[str] = mapped_column(String, index=True)
    status_code: Mapped[int] = mapped_column(Integer, default=200)
    payload: Mapped[dict | None] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
