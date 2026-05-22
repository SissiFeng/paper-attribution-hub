from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PaperReference(Base):
    """A reference parsed from the citing paper's References section.

    `cited_paper_id` is populated when the cited DOI matches a paper already
    in our corpus. `cited_ac_core_id` is populated when the DOI matches a
    curated AC landmark paper. Both are nullable — we still record the raw
    reference text even when we can't resolve it.
    """

    __tablename__ = "paper_references"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    citing_paper_id: Mapped[str] = mapped_column(
        ForeignKey("papers.id"), nullable=False, index=True
    )
    cited_paper_id: Mapped[str | None] = mapped_column(
        ForeignKey("papers.id"), index=True
    )
    cited_ac_core_id: Mapped[str | None] = mapped_column(
        ForeignKey("ac_core_papers.id"), index=True
    )
    cited_doi: Mapped[str | None] = mapped_column(String, index=True)
    cited_title: Mapped[str | None] = mapped_column(Text)
    cited_authors: Mapped[list[str] | None] = mapped_column(JSON)
    cited_year: Mapped[int | None] = mapped_column(Integer)
    raw_text: Mapped[str] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class AcCorePaper(Base):
    """Curated AC / SDL landmark papers. Citing one is itself a relevance signal."""

    __tablename__ = "ac_core_papers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    doi: Mapped[str | None] = mapped_column(String, unique=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    authors: Mapped[list[str] | None] = mapped_column(JSON)
    year: Mapped[int | None] = mapped_column(Integer)
    venue: Mapped[str | None] = mapped_column(String)
    why_core: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
