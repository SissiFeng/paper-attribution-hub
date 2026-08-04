from __future__ import annotations

from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PaperChunk(Base):
    __tablename__ = "paper_chunks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    paper_id: Mapped[str] = mapped_column(
        ForeignKey("papers.id"), nullable=False, index=True
    )
    section_id: Mapped[str | None] = mapped_column(ForeignKey("paper_sections.id"))
    section_type: Mapped[str] = mapped_column(String, index=True)
    chunk_text: Mapped[str] = mapped_column(Text)
    # Contextual prefix prepended for BM25 / vector indexing (parse.md §3).
    # Stored so retrieval results can show why an embed-time match happened.
    indexed_text: Mapped[str | None] = mapped_column(Text)
    char_start: Mapped[int] = mapped_column(Integer, default=0)
    char_end: Mapped[int] = mapped_column(Integer, default=0)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding: Mapped[list[float] | None] = mapped_column(
        JSON().with_variant(Vector(1536), "postgresql")
    )
    embedding_backend: Mapped[str | None] = mapped_column(String)
    chunk_metadata: Mapped[dict | None] = mapped_column("metadata", JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    section: Mapped["PaperSection | None"] = relationship(back_populates="chunks")  # noqa: F821
