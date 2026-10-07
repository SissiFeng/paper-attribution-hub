from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str | None] = mapped_column(String(160), nullable=True)
    scope: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey('pas_readers.id'), nullable=True, index=True)
    workspace_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default='0')
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        UniqueConstraint("session_id", "ordinal", name="uq_chat_messages_session_ordinal"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    reader_id: Mapped[str | None] = mapped_column(ForeignKey('pas_readers.id'), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="complete")
    answer_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    sources: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    audit: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    scope: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
