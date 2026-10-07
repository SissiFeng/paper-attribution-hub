from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ScientificKnowledgeRecord(Base):
    """Classification-neutral scientific knowledge compiled for one paper."""

    __tablename__ = "scientific_knowledge_records"

    paper_id: Mapped[str] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    compiler_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_snapshot_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entities: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    assertions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
