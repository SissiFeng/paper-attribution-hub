from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Paper, PaperProposition
from app.schemas import PropositionOut

router = APIRouter(tags=["propositions"])


def _row_to_out(r: PaperProposition) -> PropositionOut:
    return PropositionOut(
        id=r.id,
        paper_id=r.paper_id,
        predicate=r.predicate,
        object_value=r.object_value,
        object_key=r.object_key,
        claim_text=r.claim_text,
        confidence=r.confidence,
        source_section=r.source_section,
        source_chunk_id=r.source_chunk_id,
        extra=r.extra,
    )


@router.get("/papers/{paper_id}/propositions", response_model=list[PropositionOut])
def list_propositions_for_paper(
    paper_id: str,
    predicate: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[PropositionOut]:
    if session.get(Paper, paper_id) is None:
        raise HTTPException(status_code=404, detail=f"Paper {paper_id} not found")
    stmt = select(PaperProposition).where(PaperProposition.paper_id == paper_id)
    if predicate:
        stmt = stmt.where(PaperProposition.predicate == predicate)
    rows = list(session.execute(stmt).scalars())
    rows.sort(key=lambda r: -r.confidence)
    return [_row_to_out(r) for r in rows]


@router.get("/propositions", response_model=list[PropositionOut])
def list_propositions(
    predicate: str | None = Query(default=None),
    object_key: str | None = Query(default=None),
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
    limit: int = Query(default=200, ge=1, le=2000),
    session: Session = Depends(get_session),
) -> list[PropositionOut]:
    stmt = select(PaperProposition)
    if predicate:
        stmt = stmt.where(PaperProposition.predicate == predicate)
    if object_key:
        stmt = stmt.where(PaperProposition.object_key == object_key)
    if min_confidence is not None:
        stmt = stmt.where(PaperProposition.confidence >= min_confidence)
    rows = list(session.execute(stmt).scalars())
    rows.sort(key=lambda r: -r.confidence)
    return [_row_to_out(r) for r in rows[:limit]]
