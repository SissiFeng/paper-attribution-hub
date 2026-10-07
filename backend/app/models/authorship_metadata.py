from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PaperAuthorshipMetadata(Base):
    """Paper-specific author identity, position, and affiliation evidence.

    Affiliations stay paper-specific because an author's institution changes
    over time and one paper can assert multiple affiliations. The JSON payload
    contains normalized institution identities plus source assertions; it must
    never be treated as a timeless author profile.
    """

    __tablename__ = "paper_authorship_metadata"

    paper_id: Mapped[str] = mapped_column(
        ForeignKey("papers.id"), primary_key=True
    )
    author_id: Mapped[str] = mapped_column(
        ForeignKey("authors.id"), primary_key=True
    )
    author_order: Mapped[int] = mapped_column(Integer, nullable=False)
    author_position: Mapped[str] = mapped_column(String, nullable=False)
    is_corresponding: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    openalex_author_id: Mapped[str | None] = mapped_column(String, nullable=True)
    orcid: Mapped[str | None] = mapped_column(String, nullable=True)
    affiliations: Mapped[list[dict]] = mapped_column(
        JSON, nullable=False, default=list
    )
    sources: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    source_record_ids: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    quality_flags: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    provenance_hash: Mapped[str] = mapped_column(String, nullable=False)
    enriched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class MetadataEnrichmentRun(Base):
    """Auditable lifecycle record for one automated metadata-agent run."""

    __tablename__ = "metadata_enrichment_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    agent_version: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    input_path: Mapped[str] = mapped_column(Text, nullable=False)
    input_sha256: Mapped[str] = mapped_column(String, nullable=False, index=True)
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    errors: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
