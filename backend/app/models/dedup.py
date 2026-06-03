from __future__ import annotations
import uuid
from datetime import UTC, datetime
from sqlalchemy import DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class AuthorDedupDecision(Base):
    """Human-confirmed dedup decision: two Author IDs are the same or different person."""
    __tablename__ = "author_dedup_decisions"
    __table_args__ = (UniqueConstraint("author_id_a", "author_id_b", name="uq_dedup_pair"),)

    id: Mapped[str] = mapped_column(String, primary_key=True,
                                    default=lambda: f"dd_{uuid.uuid4().hex[:10]}")
    author_id_a: Mapped[str] = mapped_column(String, index=True)
    author_id_b: Mapped[str] = mapped_column(String, index=True)
    decision: Mapped[str] = mapped_column(String)  # "merge" | "separate"
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                  default=lambda: datetime.now(UTC))
    decided_by: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
