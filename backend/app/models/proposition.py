from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PaperProposition(Base):
    """Structured claim extracted from a paper.

    Schema (parse.md §6):
        (paper_id, predicate, object) + supporting evidence pointer

    Predicates used in v0.4:
      - funded_by(paper, "Acceleration Consortium")
      - uses_method(paper, "Bayesian optimization")
      - affiliated_with(paper, "University of Toronto")
      - cites(paper, ac_core_id)
      - belongs_to_topic(paper, topic_id)
    """

    __tablename__ = "paper_propositions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    paper_id: Mapped[str] = mapped_column(
        ForeignKey("papers.id"), nullable=False, index=True
    )
    predicate: Mapped[str] = mapped_column(String, index=True)
    object_value: Mapped[str] = mapped_column(Text)
    object_key: Mapped[str | None] = mapped_column(String, index=True)
    source_section: Mapped[str | None] = mapped_column(String)
    source_evidence_id: Mapped[str | None] = mapped_column(
        ForeignKey("paper_evidence.id")
    )
    source_chunk_id: Mapped[str | None] = mapped_column(ForeignKey("paper_chunks.id"))
    claim_text: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    extra: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
