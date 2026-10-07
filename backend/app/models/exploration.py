"""Project-scoped exploration; no records are public or shared by admin role."""
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class ResearchConnection(Base):
    __tablename__ = 'research_connections'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey('research_projects.id'), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey('pas_readers.id'))
    source_id: Mapped[str] = mapped_column(ForeignKey('papers.id'))
    target_id: Mapped[str] = mapped_column(ForeignKey('papers.id'))
    relation: Mapped[str] = mapped_column(String)
    rationale: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[int] = mapped_column(Integer)


class ResearchWatch(Base):
    __tablename__ = 'research_watches'
    project_id: Mapped[str] = mapped_column(ForeignKey('research_projects.id'), primary_key=True)
    terms: Mapped[list] = mapped_column(JSON, default=list)
    criteria: Mapped[str] = mapped_column(Text, default='')
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    since: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    checked_at: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)


class ResearchScreening(Base):
    __tablename__ = 'research_screenings'
    project_id: Mapped[str] = mapped_column(ForeignKey('research_projects.id'), primary_key=True)
    paper_id: Mapped[str] = mapped_column(ForeignKey('papers.id'), primary_key=True)
    reader_id: Mapped[str] = mapped_column(ForeignKey('pas_readers.id'), primary_key=True)
    decision: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[int] = mapped_column(Integer)


class ResearchAlert(Base):
    __tablename__ = 'research_alerts'
    project_id: Mapped[str] = mapped_column(ForeignKey('research_projects.id'), primary_key=True)
    paper_id: Mapped[str] = mapped_column(ForeignKey('papers.id'), primary_key=True)
    matches: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[int] = mapped_column(Integer)


class ResearchAlertReceipt(Base):
    __tablename__ = 'research_alert_receipts'
    project_id: Mapped[str] = mapped_column(ForeignKey('research_projects.id'), primary_key=True)
    paper_id: Mapped[str] = mapped_column(ForeignKey('papers.id'), primary_key=True)
    reader_id: Mapped[str] = mapped_column(ForeignKey('pas_readers.id'), primary_key=True)
    seen_at: Mapped[int] = mapped_column(Integer)
