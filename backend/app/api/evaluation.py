from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.schemas import EvalMetric, EvalReport, RagFeedbackOut, RagFeedbackReport
from app.services.eval_service import run_evaluation
from app.services.rag_evaluator import build_feedback_report

router = APIRouter(prefix="/eval", tags=["eval"])


@router.get("/metrics", response_model=EvalReport)
def eval_metrics(
    k: int = Query(default=5, ge=1, le=50),
    stage1_role: str = Query(default="validation"),
    release_frozen_test: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> EvalReport:
    if settings.sdl_stage1_only:
        from app.services.eval_service import run_stage1_evaluation

        try:
            report = run_stage1_evaluation(
                session,
                role=stage1_role,
                release_frozen_test=release_frozen_test,
                k=k,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _response(report)
    if not settings.eval_labels_csv.exists():
        raise HTTPException(
            status_code=404, detail=f"Eval labels not found at {settings.eval_labels_csv}"
        )
    report = run_evaluation(session, settings.eval_labels_csv, k=k)
    return _response(report)


def _response(report) -> EvalReport:
    return EvalReport(
        per_label=[
            EvalMetric(
                label=m.label,
                precision=m.precision,
                recall=m.recall,
                f1=m.f1,
                support=m.support,
            )
            for m in report.per_label
        ],
        macro_precision=report.macro_precision,
        macro_recall=report.macro_recall,
        macro_f1=report.macro_f1,
        accuracy=report.accuracy,
        confusion=report.confusion,
        evidence_recall_at_k=report.evidence_recall_at_k,
        k=report.k,
        n_evaluated=report.n_evaluated,
        dataset_role=report.dataset_role,
        dataset_id=report.dataset_id,
        dataset_hash=report.dataset_hash,
        includes_silver=report.includes_silver,
        label_scope=report.label_scope,
        annotation_sources=report.annotation_sources,
        evidence_levels=report.evidence_levels,
        allowed_claim=report.allowed_claim,
    )


@router.get("/rag-feedback", response_model=RagFeedbackReport)
def rag_feedback_report(
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> RagFeedbackReport:
    report = build_feedback_report(session, limit=limit)
    return RagFeedbackReport(
        total_feedback=report["total_feedback"],
        average_rating=report["average_rating"],
        low_rating_count=report["low_rating_count"],
        by_failure_type=report["by_failure_type"],
        recent=[
            RagFeedbackOut(
                id=row.id,
                query=row.query,
                rating=row.rating,
                failure_type=row.failure_type,
                note=row.note,
                answer_model=row.answer_model,
                source_chunk_ids=row.source_chunk_ids or [],
                source_paper_ids=row.source_paper_ids or [],
                created_at=row.created_at,
            )
            for row in report["recent"]
        ],
    )
