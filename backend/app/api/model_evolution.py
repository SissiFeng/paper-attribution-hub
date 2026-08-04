"""Read-only operations surface for the human-feedback model loop."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import ModelTrainingRun
from app.services.model_evolution import (
    model_evolution_status,
    training_run_to_dict,
)

router = APIRouter(prefix="/model-evolution", tags=["model-evolution"])


class ModelTrainingRunOut(BaseModel):
    run_id: str
    status: str
    trigger_review_count: int
    trigger_event_ids: list[str]
    trigger_paper_ids: list[str]
    lease_generation: int
    training_example_count: int
    validation_example_count: int
    backend: str
    model_version: str | None = None
    evaluation_scope: str | None = None
    candidate_metrics: dict[str, Any] | None = None
    incumbent_metrics: dict[str, Any] | None = None
    validation_candidate_metrics: dict[str, Any] | None = None
    validation_incumbent_metrics: dict[str, Any] | None = None
    promotion_reason: str | None = None
    promotion_gate_config: dict[str, Any] | None = None
    runtime_versions: dict[str, Any] | None = None
    cache_sync_status: str | None = None
    training_dataset_hash: str | None = None
    validation_dataset_hash: str | None = None
    label_boundary_hashes: dict[str, str] | None = None
    candidate_model_sha256: str | None = None
    incumbent_model_sha256: str | None = None
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    promoted_at: datetime | None = None
    heartbeat_at: datetime | None = None


class ModelEvolutionStatusOut(BaseModel):
    batch_size: int
    pending_reviews: int
    reviews_until_retrain: int
    progress: float
    current_model_version: str | None = None
    production_authority: dict[str, Any]
    validation_gate: dict[str, Any]
    active_run: ModelTrainingRunOut | None = None
    latest_run: ModelTrainingRunOut | None = None


@router.get("/status", response_model=ModelEvolutionStatusOut)
def get_model_evolution_status(
    session: Session = Depends(get_session),
) -> ModelEvolutionStatusOut:
    return ModelEvolutionStatusOut.model_validate(model_evolution_status(session))


@router.get("/runs", response_model=list[ModelTrainingRunOut])
def list_model_training_runs(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    session: Session = Depends(get_session),
) -> list[ModelTrainingRunOut]:
    rows = session.execute(
        select(ModelTrainingRun)
        .order_by(ModelTrainingRun.started_at.desc())
        .limit(limit)
    ).scalars()
    return [
        ModelTrainingRunOut.model_validate(training_run_to_dict(row))
        for row in rows
    ]
