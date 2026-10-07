"""Reading projects and explicitly scoped research artifacts; no public defaults."""
from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class ResearchProject(Base):
    __tablename__ = 'research_projects'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey('pas_readers.id'), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False, default='')
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)


class ProjectMember(Base):
    __tablename__ = 'research_project_members'
    project_id: Mapped[str] = mapped_column(ForeignKey('research_projects.id'), primary_key=True)
    reader_id: Mapped[str] = mapped_column(ForeignKey('pas_readers.id'), primary_key=True)


class ProjectPaper(Base):
    __tablename__ = 'research_project_papers'
    project_id: Mapped[str] = mapped_column(ForeignKey('research_projects.id'), primary_key=True)
    paper_id: Mapped[str] = mapped_column(ForeignKey('papers.id'), primary_key=True)


class ProjectDiscussion(Base):
    __tablename__ = 'research_project_discussions'
    session_id: Mapped[str] = mapped_column(ForeignKey('chat_sessions.id'), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey('research_projects.id'), nullable=False, index=True)


class Annotation(Base):
    __tablename__ = 'research_annotations'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey('pas_readers.id'), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey('research_projects.id'), index=True)
    paper_id: Mapped[str] = mapped_column(ForeignKey('papers.id'), nullable=False, index=True)
    anchor: Mapped[dict] = mapped_column(JSON, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)


class EvidenceComparison(Base):
    __tablename__ = 'research_comparisons'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey('pas_readers.id'), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey('research_projects.id'), index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    paper_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    dimensions: Mapped[list] = mapped_column(JSON, nullable=False)
    cells: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)
