from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class HumanReview(Base):
    __tablename__ = "human_reviews"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    paper_id: Mapped[str] = mapped_column(
        ForeignKey("papers.id"), unique=True, nullable=False, index=True
    )
    # Legacy classifier-taxonomy correction. Independent SDL and AC reviews do
    # not populate this field and therefore cannot silently become training data.
    human_label: Mapped[str | None] = mapped_column(String, nullable=True)
    sdl_judgement: Mapped[str | None] = mapped_column(
        String, nullable=True, index=True
    )
    ac_relevance_judgement: Mapped[str | None] = mapped_column(
        String, nullable=True, index=True
    )
    ai_for_science_judgement: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    review_status: Mapped[str | None] = mapped_column(
        String, nullable=True, index=True
    )
    evidence_level: Mapped[str | None] = mapped_column(String, nullable=True)
    judgement_basis: Mapped[str | None] = mapped_column(String, nullable=True)
    corrected_topics: Mapped[list[str] | None] = mapped_column(JSON)
    corrected_people: Mapped[list[str] | None] = mapped_column(JSON)
    reviewer: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(Text)
    disagreement_type: Mapped[str | None] = mapped_column(String, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    future_rule_update: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    paper: Mapped["Paper"] = relationship(back_populates="review")  # noqa: F821
