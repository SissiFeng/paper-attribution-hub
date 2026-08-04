"""Auditable state for human-feedback-driven model evolution."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ModelTrainingRun(Base):
    __tablename__ = "model_training_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    trigger_review_count: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger_event_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    trigger_paper_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    backend: Mapped[str] = mapped_column(String, nullable=False)
    lease_generation: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    training_example_count: Mapped[int] = mapped_column(Integer, default=0)
    validation_example_count: Mapped[int] = mapped_column(Integer, default=0)
    training_dataset_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    validation_dataset_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    label_boundary_hashes: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )
    evaluation_scope: Mapped[str | None] = mapped_column(String, nullable=True)
    candidate_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    incumbent_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    validation_candidate_metrics: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )
    validation_incumbent_metrics: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )
    candidate_model_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    production_model_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate_model_sha256: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    model_artifact: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )
    incumbent_model_sha256: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    model_version: Mapped[str | None] = mapped_column(String, nullable=True)
    promotion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    promotion_gate_config: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )
    runtime_versions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cache_sync_status: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    promoted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class ModelTrainingState(Base):
    __tablename__ = "model_training_state"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    batch_size: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    active_run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    lease_generation: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    production_run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    current_model_version: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class TrainingFeedbackEvent(Base):
    __tablename__ = "training_feedback_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    review_id: Mapped[str] = mapped_column(
        ForeignKey("human_reviews.id"), nullable=False, index=True
    )
    paper_id: Mapped[str] = mapped_column(
        ForeignKey("papers.id"), nullable=False, index=True
    )
    human_label: Mapped[str] = mapped_column(String, nullable=False)
    reviewer: Mapped[str | None] = mapped_column(String, nullable=True)
    incumbent_label: Mapped[str | None] = mapped_column(String, nullable=True)
    incumbent_confidence: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    consumed_by_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("model_training_runs.id"), nullable=True, index=True
    )
    retired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    retirement_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
