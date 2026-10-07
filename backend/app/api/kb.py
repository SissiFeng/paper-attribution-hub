from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import (
    KbEntityIndexOut,
    KbEntityPageOut,
    KbLabProfileOut,
    KbSummaryOut,
    ScientificKnowledgeOut,
)
from app.services.kb_service import entity_index, entity_page, kb_summary, lab_profile
from app.services.scientific_knowledge_service import (
    ScientificKnowledgeNotFoundError,
    get_scientific_knowledge,
)

router = APIRouter(prefix="/kb", tags=["kb"])


@router.get("/summary", response_model=KbSummaryOut)
def summary(session: Session = Depends(get_session)) -> KbSummaryOut:
    """Headline totals for the knowledge-base landing page."""
    return KbSummaryOut(**kb_summary(session))


@router.get(
    "/papers/{paper_id}/scientific-knowledge",
    response_model=ScientificKnowledgeOut,
)
def scientific_knowledge(
    paper_id: str,
    session: Session = Depends(get_session),
) -> ScientificKnowledgeOut:
    """Read a compiled, classification-neutral scientific knowledge record."""
    try:
        record = get_scientific_knowledge(session, paper_id)
    except ScientificKnowledgeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ScientificKnowledgeOut(
        paper_id=record.paper_id,
        schema_version=record.schema_version,
        compiler_version=record.compiler_version,
        source_snapshot_hash=record.source_snapshot_hash,
        content_hash=record.content_hash,
        entities=record.entities,
        assertions=record.assertions,
        source_metadata=record.source_metadata,
        generated_at=record.generated_at,
    )


@router.get("/entities", response_model=list[KbEntityIndexOut])
def entities(
    entity_type: str | None = Query(default=None),
    q: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[KbEntityIndexOut]:
    """Distinct normalized entities with paper/lab counts and year span."""
    return [
        KbEntityIndexOut(**entry)
        for entry in entity_index(session, entity_type=entity_type, q=q)
    ]


@router.get("/entities/{entity_type}/{name}", response_model=KbEntityPageOut)
def entity_detail(
    entity_type: str, name: str, session: Session = Depends(get_session)
) -> KbEntityPageOut:
    """Full entity page: labs, papers, timeline, evidence, adoption lags."""
    page = entity_page(session, entity_type, name)
    if page is None:
        raise HTTPException(
            status_code=404, detail=f"Entity {entity_type}/{name} not found"
        )
    return KbEntityPageOut(**page)


@router.get("/labs/{lab_id}/profile", response_model=KbLabProfileOut)
def lab_profile_page(
    lab_id: str, session: Session = Depends(get_session)
) -> KbLabProfileOut:
    """Aggregated lab profile: tags histogram, top entities, collaborations."""
    profile = lab_profile(session, lab_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Lab {lab_id} not found")
    return KbLabProfileOut(**profile)
