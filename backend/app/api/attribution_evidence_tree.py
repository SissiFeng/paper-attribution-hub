from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.models import Paper
from app.schemas import AttributionEvidenceTreeOut
from app.services.attribution_evidence_tree import build_attribution_evidence_tree

router = APIRouter(prefix="/papers", tags=["attribution_evidence_tree"])


@router.get(
    "/{paper_id}/attribution-evidence-tree",
    response_model=AttributionEvidenceTreeOut,
)
def attribution_evidence_tree(
    paper_id: str, session: Session = Depends(get_session)
) -> AttributionEvidenceTreeOut:
    if not settings.attribution_evidence_tree_enabled:
        raise HTTPException(
            status_code=404, detail="Attribution evidence tree is disabled"
        )
    if session.get(Paper, paper_id) is None:
        raise HTTPException(status_code=404, detail=f"Paper {paper_id} not found")
    return build_attribution_evidence_tree(session, paper_id)
