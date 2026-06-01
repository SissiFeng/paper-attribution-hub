from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PaperClassification(Base):
    __tablename__ = "paper_classifications"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    paper_id: Mapped[str] = mapped_column(
        ForeignKey("papers.id"), unique=True, nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String, index=True)
    confidence: Mapped[float] = mapped_column(Float)
    author_score: Mapped[float] = mapped_column(Float, default=0.0)
    institution_score: Mapped[float] = mapped_column(Float, default=0.0)
    topic_score: Mapped[float] = mapped_column(Float, default=0.0)
    network_score: Mapped[float] = mapped_column(Float, default=0.0)
    fulltext_evidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    citation_score: Mapped[float] = mapped_column(Float, default=0.0)
    graph_signals: Mapped[dict | None] = mapped_column(JSON)
    matched_people: Mapped[list[dict] | None] = mapped_column(JSON)
    matched_institutions: Mapped[list[dict] | None] = mapped_column(JSON)
    matched_topics: Mapped[list[dict] | None] = mapped_column(JSON)
    reasons: Mapped[list[str] | None] = mapped_column(JSON)
    model_version: Mapped[str] = mapped_column(String, default="rules-v0.1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # v0.7 #review-loop additions
    last_classified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Set when the daily pipeline thinks a reviewer should look at this paper.
    # Cleared by /reviews/queue/skip or after a confirmation/correction.
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # Priority score (0-1). Higher = surface sooner in the queue.
    review_priority: Mapped[float] = mapped_column(Float, default=0.0)
    # Bumped when a reviewer hits /confirm or /reviews/{id}. Once human_confirmed
    # is True the daily pipeline never overwrites the label automatically.
    human_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    human_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    human_confirmed_by: Mapped[str | None] = mapped_column(String, nullable=True)

    # ── Scopus-sourced evidence signals ──────────────────────────────────
    # Each 0-1 float; set by scopus_classifier before the LLM judge runs.
    funding_signal: Mapped[float] = mapped_column(Float, default=0.0)
    acknowledgement_signal: Mapped[float] = mapped_column(Float, default=0.0)
    retrieval_signal: Mapped[float] = mapped_column(Float, default=0.0)
    architecture_signal: Mapped[float] = mapped_column(Float, default=0.0)

    # ── Knowledge-base classification memory ─────────────────────────────
    sdl_relevance_label: Mapped[str | None] = mapped_column(String, nullable=True)
    ac_attribution_label: Mapped[str | None] = mapped_column(String, nullable=True)
    model_agreement_status: Mapped[str | None] = mapped_column(String, nullable=True)
    disagreement_type: Mapped[str | None] = mapped_column(String, nullable=True)
    evidence_summary: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    future_rule_update: Mapped[str | None] = mapped_column(Text, nullable=True)

    paper: Mapped["Paper"] = relationship(back_populates="classification")  # noqa: F821
