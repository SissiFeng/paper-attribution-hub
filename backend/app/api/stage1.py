from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.services.stage1_readiness import build_stage1_readiness

router = APIRouter(prefix="/stage1", tags=["stage1"])


@router.get("/readiness")
def stage1_readiness(
    session: Session = Depends(get_session),
) -> dict:
    """Report whether classification-derived Stage 1 views are publishable."""
    return build_stage1_readiness(session)
