from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.models import Paper, PaperLabLink, SdlLab

router = APIRouter(prefix="/labs", tags=["labs"])


class LabOut(BaseModel):
    id: str
    name: str
    institution: str
    pi_names: list[str]
    domain_focus: str
    platform_stack: list[str] | None = None
    automation_level: str | None = None
    paper_count: int


class LabPaperOut(BaseModel):
    id: str
    title: str
    year: int | None = None
    label: str | None = None


@router.get("", response_model=list[LabOut])
def list_labs(session: Session = Depends(get_session)) -> list[LabOut]:
    counts = dict(
        session.execute(
            select(PaperLabLink.lab_id, func.count()).group_by(PaperLabLink.lab_id)
        ).all()
    )
    labs = session.execute(select(SdlLab).order_by(SdlLab.name)).scalars()
    return [
        LabOut(
            id=lab.id,
            name=lab.name,
            institution=lab.institution,
            pi_names=lab.pi_names or [],
            domain_focus=lab.domain_focus,
            platform_stack=lab.platform_stack,
            automation_level=lab.automation_level,
            paper_count=counts.get(lab.id, 0),
        )
        for lab in labs
    ]


@router.get("/{lab_id}/papers", response_model=list[LabPaperOut])
def lab_papers(lab_id: str, session: Session = Depends(get_session)) -> list[LabPaperOut]:
    lab = session.get(SdlLab, lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail=f"Lab {lab_id} not found")
    papers = session.execute(
        select(Paper)
        .join(PaperLabLink, PaperLabLink.paper_id == Paper.id)
        .where(PaperLabLink.lab_id == lab_id)
        .options(selectinload(Paper.classification))
        .order_by(Paper.year.desc())
    ).scalars()
    return [
        LabPaperOut(
            id=p.id,
            title=p.title,
            year=p.year,
            label=p.classification.label if p.classification else None,
        )
        for p in papers
    ]
