"""Cross-SDL knowledge-transfer foundation: lab registry, paper→lab links,
typed paper entities (methods / materials / instruments / software)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SdlLab(Base):
    """A self-driving lab in the consortium. `member_author_names` is the
    author roster used to map papers to the lab."""

    __tablename__ = "sdl_labs"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # slug
    name: Mapped[str] = mapped_column(String, nullable=False)
    institution: Mapped[str] = mapped_column(String, nullable=False)
    pi_names: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    domain_focus: Mapped[str] = mapped_column(String, nullable=False)
    platform_stack: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    automation_level: Mapped[str | None] = mapped_column(String, nullable=True)
    member_author_names: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class PaperLabLink(Base):
    """A paper attributed to an SDL lab. `source` is "author_roster",
    "ac_members", or "manual"."""

    __tablename__ = "paper_lab_links"

    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id"), primary_key=True)
    lab_id: Mapped[str] = mapped_column(ForeignKey("sdl_labs.id"), primary_key=True)
    source: Mapped[str] = mapped_column(String, nullable=False, default="author_roster")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.9)


class PaperEntity(Base):
    """A typed entity extracted from a paper.

    entity_type is one of method | material | instrument | software |
    institution.
    `name` is the surface form as matched; `normalized_name` is the vocab
    canonical, which is what cross-lab transfer analytics should join on.

    For method entities, `stage` is the pipeline stage the method is used in
    (a stage id from data/method_stages.yaml, e.g. "property_prediction") and
    `usage_snippet` is the sentence the method was matched in (≤250 chars).
    Both are NULL for non-method entity types. Institution rows are
    paper-level front-matter affiliation mentions; they do not assert a
    resolved author-to-institution relationship.
    """

    __tablename__ = "paper_entities"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    paper_id: Mapped[str] = mapped_column(
        ForeignKey("papers.id"), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    normalized_name: Mapped[str] = mapped_column(String, nullable=False)
    evidence_chunk_id: Mapped[str | None] = mapped_column(
        ForeignKey("paper_chunks.id"), nullable=True
    )
    section: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.6)
    extractor: Mapped[str] = mapped_column(String, nullable=False, default="vocabulary")
    stage: Mapped[str | None] = mapped_column(String, nullable=True)
    usage_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "paper_id", "entity_type", "normalized_name", name="uq_paper_entity"
        ),
        Index("ix_paper_entities_type_norm", "entity_type", "normalized_name"),
    )
