from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth import require_api_key
from app.attribution_skill_contract import AttributionSkillInvocation
from app.db import get_session
from app.services.attribution_skill_service import (
    AttributionSkillCatalog,
    AttributionSkillInvokeRequest,
    InvocationConflictError,
    InvocationNotFoundError,
    PaperNotFoundError,
    attribution_skill_catalog,
    get_recorded_attribution_invocation,
    invoke_attribution_skill,
    replay_matching_attribution_invocation,
)

router = APIRouter(
    prefix="/api/v1/attribution-skills",
    tags=["attribution_skills"],
)


@router.get("", response_model=AttributionSkillCatalog)
def list_attribution_skills() -> AttributionSkillCatalog:
    return attribution_skill_catalog()


@router.post(
    "/invoke",
    response_model=AttributionSkillInvocation,
    dependencies=[Depends(require_api_key)],
)
def invoke(
    payload: AttributionSkillInvokeRequest,
    session: Session = Depends(get_session),
) -> AttributionSkillInvocation:
    try:
        result = invoke_attribution_skill(session, payload)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            try:
                return replay_matching_attribution_invocation(
                    session,
                    payload,
                )
            except InvocationNotFoundError:
                raise exc
        return result
    except PaperNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Paper {payload.paper_id} not found",
        )
    except InvocationConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get(
    "/invocations/{invocation_id}",
    response_model=AttributionSkillInvocation,
    dependencies=[Depends(require_api_key)],
)
def replay(
    invocation_id: str,
    session: Session = Depends(get_session),
) -> AttributionSkillInvocation:
    try:
        return get_recorded_attribution_invocation(session, invocation_id)
    except InvocationNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Attribution Skill invocation {invocation_id} not found",
        )
