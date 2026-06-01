from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[str | None] = mapped_column(Text)
    doi: Mapped[str | None] = mapped_column(String, unique=True)
    year: Mapped[int | None] = mapped_column(Integer)
    venue: Mapped[str | None] = mapped_column(String)
    source: Mapped[str] = mapped_column(String, default="csv")
    # v0.5: how this paper entered the corpus. One of:
    #   csv | pdf | openalex | semantic_scholar | crossref |
    #   discovered_auto | discovered_approved | manual_upload
    provenance: Mapped[str] = mapped_column(String, default="csv", index=True)
    keywords: Mapped[list[str] | None] = mapped_column(JSON)
    full_text_available: Mapped[bool] = mapped_column(Boolean, default=False)
    pdf_path: Mapped[str | None] = mapped_column(String)
    raw_metadata: Mapped[dict | None] = mapped_column(JSON)

    # Scopus Indexed Keywords (separate from author-assigned keywords)
    indexed_keywords: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # ── Scopus retrieval provenance ──────────────────────────────────────
    eid: Mapped[str | None] = mapped_column(String, unique=True, nullable=True, index=True)
    retrieval_tier: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    merge_tier_membership: Mapped[str | None] = mapped_column(String, nullable=True)
    query_string: Mapped[str | None] = mapped_column(Text, nullable=True)
    funding_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    funding_sponsors: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # ── AC gold set fields (from AC Publications CSV) ────────────────────
    ac_known_publication: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    ac_acknowledged: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ac_highly_relevant: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ac_high_impact: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ac_members_matched: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    ac_programs: Mapped[str | None] = mapped_column(String, nullable=True)
    sdl_tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    research_tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # ── Attribution scores (set by scopus_classifier) ────────────────────
    ac_attribution_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sdl_relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Tier 2 architecture component scores (0/1 keyword presence) ──────
    ai_decision_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    automation_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    closed_loop_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    # Bumped whenever ingestion / fulltext attachment / curation touches the
    # paper; the daily pipeline uses this to find papers whose classification
    # is stale relative to their content.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    authors: Mapped[list["PaperAuthor"]] = relationship(
        back_populates="paper",
        cascade="all, delete-orphan",
        order_by="PaperAuthor.author_order",
    )
    classification: Mapped["PaperClassification | None"] = relationship(  # noqa: F821
        back_populates="paper", uselist=False, cascade="all, delete-orphan"
    )
    review: Mapped["HumanReview | None"] = relationship(  # noqa: F821
        back_populates="paper", uselist=False, cascade="all, delete-orphan"
    )


class PaperAuthor(Base):
    __tablename__ = "paper_authors"

    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id"), primary_key=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("authors.id"), primary_key=True)
    author_order: Mapped[int] = mapped_column(Integer, default=0)
    affiliation_text: Mapped[str | None] = mapped_column(Text)
    match_confidence: Mapped[float | None] = mapped_column()

    paper: Mapped[Paper] = relationship(back_populates="authors")
    author: Mapped["Author"] = relationship(back_populates="papers")  # noqa: F821
