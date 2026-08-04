from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AttributionSkillInvocationRecord(Base):
    """Immutable replay record for one attribution Skill invocation."""

    __tablename__ = "attribution_skill_invocations"

    invocation_id: Mapped[str] = mapped_column(String, primary_key=True)
    paper_id: Mapped[str] = mapped_column(
        ForeignKey("papers.id"), nullable=False, index=True
    )
    skill_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    skill_version: Mapped[str] = mapped_column(String, nullable=False)
    policy_version: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    input_snapshot_id: Mapped[str] = mapped_column(String, nullable=False)
    input_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    input_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    invocation_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    decision: Mapped[str | None] = mapped_column(String, index=True)
    final_confidence: Mapped[float | None] = mapped_column(Float)
    failure_category: Mapped[str | None] = mapped_column(String, index=True)
    retrieval_api_calls: Mapped[int] = mapped_column(Integer, default=0)
    fulltext_retrieval_status: Mapped[str] = mapped_column(
        String, default="not_requested"
    )
    extraction_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    model_calls: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    graph_queries: Mapped[int] = mapped_column(Integer, default=0)
    human_review_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    resolution_path: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
