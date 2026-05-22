from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.schemas import EvalMetric, EvalReport
from app.services.eval_service import run_evaluation

router = APIRouter(prefix="/eval", tags=["eval"])


@router.get("/metrics", response_model=EvalReport)
def eval_metrics(
    k: int = Query(default=5, ge=1, le=50),
    session: Session = Depends(get_session),
) -> EvalReport:
    if not settings.eval_labels_csv.exists():
        raise HTTPException(
            status_code=404, detail=f"Eval labels not found at {settings.eval_labels_csv}"
        )
    report = run_evaluation(session, settings.eval_labels_csv, k=k)
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
    )
