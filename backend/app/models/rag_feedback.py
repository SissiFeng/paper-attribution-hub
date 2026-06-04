from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RagFeedback(Base):
    __tablename__ = "rag_feedback"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    failure_type: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_model: Mapped[str | None] = mapped_column(String, nullable=True)
    source_chunk_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    source_paper_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
