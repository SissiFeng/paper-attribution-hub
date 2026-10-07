"""Private application identity, browser sessions, bookmarks and discussion grants."""
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Reader(Base):
    __tablename__ = 'pas_readers'
    __table_args__ = (UniqueConstraint('workspace_id', 'slack_user_id'),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    slack_user_id: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ReaderSession(Base):
    __tablename__ = 'pas_reader_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    reader_id: Mapped[str] = mapped_column(ForeignKey('pas_readers.id'), nullable=False, index=True)
    expires: Mapped[int] = mapped_column(Integer, nullable=False)


class Bookmark(Base):
    __tablename__ = 'pas_bookmarks'
    reader_id: Mapped[str] = mapped_column(ForeignKey('pas_readers.id'), primary_key=True)
    paper_id: Mapped[str] = mapped_column(ForeignKey('papers.id'), primary_key=True)
    note: Mapped[str] = mapped_column(Text, nullable=False, default='')
    saved_at: Mapped[int] = mapped_column(Integer, nullable=False)


class ChatParticipant(Base):
    __tablename__ = 'chat_participants'
    session_id: Mapped[str] = mapped_column(ForeignKey('chat_sessions.id'), primary_key=True)
    reader_id: Mapped[str] = mapped_column(ForeignKey('pas_readers.id'), primary_key=True)
