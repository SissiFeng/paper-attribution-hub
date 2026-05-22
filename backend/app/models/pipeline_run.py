"""Audit log for scheduled-pipeline executions.

One row per `run_daily_pipeline` invocation. Lets reviewers and admins see
when the last run was, what it did, and whether it succeeded.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)

    # What the run did.
    discovered_candidates: Mapped[int] = mapped_column(Integer, default=0)
    auto_ingested: Mapped[int] = mapped_column(Integer, default=0)
    queued_for_review: Mapped[int] = mapped_column(Integer, default=0)
    classified_new: Mapped[int] = mapped_column(Integer, default=0)
    reclassified_stale: Mapped[int] = mapped_column(Integer, default=0)
    enqueued_for_review: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[str] = mapped_column(String, default="success", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Free-form per-step breakdown so the API can render a step list.
    steps: Mapped[list[dict] | None] = mapped_column(JSON)
    triggered_by: Mapped[str] = mapped_column(String, default="cron")
