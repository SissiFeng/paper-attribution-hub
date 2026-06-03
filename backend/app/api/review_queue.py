"""Review-queue + pipeline endpoints (v0.7 review loop).

REST surface:

  GET  /reviews/queue?limit=20             — paginated, priority-sorted
  GET  /reviews/queue/next                  — single highest-priority item
  GET  /reviews/queue/size                  — count outstanding
  POST /reviews/{paper_id}/confirm          — lock the current label
  POST /reviews/{paper_id}/skip             — defer for N days
  POST /pipeline/run                        — manual trigger (admin)
  GET  /pipeline/runs                       — recent run log
  GET  /pipeline/runs/latest                — most recent run
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import RagStatusOut
from app.services.rag_status_service import rag_status_by_paper
from app.services.review_queue import (
    QueueItem,
    confirm_classification,
    get_next,
    list_queue,
    queue_size,
    skip_for_now,
)
from app.services.scheduled_pipeline import (
    latest_run,
    recent_runs,
    run_daily_pipeline,
)

router = APIRouter(tags=["review-queue"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class QueueItemOut(BaseModel):
    paper_id: str
    title: str
    label: str
    confidence: float
    priority: float
    reasons: list[str]
    last_classified_at: datetime | None
    provenance: str | None
    has_human_review: bool
    rag_status: RagStatusOut | None = None

    @classmethod
    def from_item(
        cls,
        item: QueueItem,
        rag_status: RagStatusOut | None = None,
    ) -> "QueueItemOut":
        return cls(
            paper_id=item.paper_id,
            title=item.title,
            label=item.label,
            confidence=item.confidence,
            priority=item.priority,
            reasons=item.reasons,
            last_classified_at=item.last_classified_at,
            provenance=item.provenance,
            has_human_review=item.has_human_review,
            rag_status=rag_status,
        )


class ConfirmIn(BaseModel):
    reviewer: str | None = None


class SkipIn(BaseModel):
    cooldown_days: int = 7


class PipelineRunOut(BaseModel):
    run_id: str
    status: str
    duration_seconds: float
    started_at: datetime
    finished_at: datetime
    discovered_candidates: int
    auto_ingested: int
    queued_for_review: int
    classified_new: int
    reclassified_stale: int
    enqueued_for_review: int
    error_message: str | None
    steps: list[dict] | None
    triggered_by: str

    @classmethod
    def from_row(cls, row) -> "PipelineRunOut":
        return cls(
            run_id=row.id,
            status=row.status,
            duration_seconds=row.duration_seconds,
            started_at=row.started_at,
            finished_at=row.finished_at or row.started_at,
            discovered_candidates=row.discovered_candidates,
            auto_ingested=row.auto_ingested,
            queued_for_review=row.queued_for_review,
            classified_new=row.classified_new,
            reclassified_stale=row.reclassified_stale,
            enqueued_for_review=row.enqueued_for_review,
            error_message=row.error_message,
            steps=row.steps,
            triggered_by=row.triggered_by,
        )


class PipelineRunInput(BaseModel):
    do_discovery: bool | None = None
    do_fulltext: bool | None = None
    use_learned: bool | None = None
    use_judge: bool | None = None
    triggered_by: str = "manual"


# ---------------------------------------------------------------------------
# Queue endpoints
# ---------------------------------------------------------------------------


@router.get("/reviews/queue", response_model=list[QueueItemOut])
def get_queue(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    include_confirmed: Annotated[bool, Query()] = False,
    session: Session = Depends(get_session),
) -> list[QueueItemOut]:
    items = list_queue(
        session,
        limit=limit,
        offset=offset,
        include_confirmed=include_confirmed,
    )
    statuses = rag_status_by_paper(session, [item.paper_id for item in items])
    return [QueueItemOut.from_item(it, statuses.get(it.paper_id)) for it in items]


@router.get("/reviews/queue/next", response_model=QueueItemOut | None)
def get_queue_next(
    session: Session = Depends(get_session),
) -> QueueItemOut | None:
    item = get_next(session)
    if not item:
        return None
    status = rag_status_by_paper(session, [item.paper_id]).get(item.paper_id)
    return QueueItemOut.from_item(item, status)


@router.get("/reviews/queue/size")
def get_queue_size(session: Session = Depends(get_session)) -> dict:
    return {"count": queue_size(session)}


@router.post("/reviews/{paper_id}/confirm", response_model=QueueItemOut)
def confirm(
    paper_id: str,
    payload: ConfirmIn = Body(default_factory=ConfirmIn),
    session: Session = Depends(get_session),
) -> QueueItemOut:
    try:
        cls = confirm_classification(session, paper_id, reviewer=payload.reviewer)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    paper = cls.paper
    status = rag_status_by_paper(session, [paper.id]).get(paper.id)
    return QueueItemOut(
        paper_id=paper.id,
        title=paper.title,
        label=cls.label,
        confidence=cls.confidence,
        priority=0.0,
        reasons=[f"Confirmed by {payload.reviewer or 'reviewer'}"],
        last_classified_at=cls.last_classified_at,
        provenance=paper.provenance,
        has_human_review=paper.review is not None,
        rag_status=status,
    )


@router.post("/reviews/{paper_id}/skip", response_model=QueueItemOut)
def skip(
    paper_id: str,
    payload: SkipIn = Body(default_factory=SkipIn),
    session: Session = Depends(get_session),
) -> QueueItemOut:
    try:
        cls = skip_for_now(
            session, paper_id, cooldown_days=payload.cooldown_days
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    paper = cls.paper
    status = rag_status_by_paper(session, [paper.id]).get(paper.id)
    return QueueItemOut(
        paper_id=paper.id,
        title=paper.title,
        label=cls.label,
        confidence=cls.confidence,
        priority=0.0,
        reasons=[f"Deferred for {payload.cooldown_days} days"],
        last_classified_at=cls.last_classified_at,
        provenance=paper.provenance,
        has_human_review=paper.review is not None,
        rag_status=status,
    )


# ---------------------------------------------------------------------------
# Pipeline endpoints
# ---------------------------------------------------------------------------


@router.post("/pipeline/run", response_model=PipelineRunOut)
def trigger_pipeline(
    payload: PipelineRunInput = Body(default_factory=PipelineRunInput),
    session: Session = Depends(get_session),
) -> PipelineRunOut:
    """Manual pipeline trigger. Same logic as the cron CLI."""
    result = run_daily_pipeline(
        session,
        do_discovery=payload.do_discovery,
        do_fulltext=payload.do_fulltext,
        use_learned=payload.use_learned,
        use_judge=payload.use_judge,
        triggered_by=payload.triggered_by,
    )
    # Materialize into a stub PipelineRun-like object for the response.
    return PipelineRunOut(
        run_id=result.run_id,
        status=result.status,
        duration_seconds=result.duration_seconds,
        started_at=result.started_at,
        finished_at=result.finished_at,
        discovered_candidates=result.discovered_candidates,
        auto_ingested=result.auto_ingested,
        queued_for_review=result.queued_for_review,
        classified_new=result.classified_new,
        reclassified_stale=result.reclassified_stale,
        enqueued_for_review=result.enqueued_for_review,
        error_message=result.error_message,
        steps=result.steps,
        triggered_by=payload.triggered_by,
    )


@router.get("/pipeline/runs", response_model=list[PipelineRunOut])
def list_runs(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    session: Session = Depends(get_session),
) -> list[PipelineRunOut]:
    rows = recent_runs(session, limit=limit)
    return [PipelineRunOut.from_row(r) for r in rows]


@router.get("/pipeline/runs/latest", response_model=PipelineRunOut | None)
def get_latest_run(
    session: Session = Depends(get_session),
) -> PipelineRunOut | None:
    row = latest_run(session)
    return PipelineRunOut.from_row(row) if row else None
