from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class WikiPage(Base):
    """LLM-compiled knowledge digest for a corpus entity (paper / author / institution / topic)."""

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
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    # True when the underlying data changed after the last compile.
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", name="uq_wiki_entity"),
    )
