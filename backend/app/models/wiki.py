from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class WikiPage(Base):
    """Compiled, provenance-bearing evidence view for a corpus entity."""

    __tablename__ = "wiki_pages"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)   # paper | author | institution | topic
    entity_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    # Structured sections: [{"key": str, "heading": str, "body": str, "chips": [...]}]
    sections: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # Raw markdown (optional; derived from sections for display)
    content_md: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str] = mapped_column(String, default="template-v0.1")
    prompt_version: Mapped[str] = mapped_column(String, default="v0.1")
    # Hashes are computed from the deterministic source projection and rendered
    # Markdown respectively.  They make compilation idempotent without relying
    # on every upstream writer remembering to call mark_stale().
    source_snapshot_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    # Compact provenance needed by bundle validation and the frontend.  Raw
    # evidence remains in the immutable Attribution Skill invocation record.
    source_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    compile_status: Mapped[str] = mapped_column(String, default="complete", index=True)
    compile_error: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    # True when the underlying data changed after the last compile.
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", name="uq_wiki_entity"),
    )
