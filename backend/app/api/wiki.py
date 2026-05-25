from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_session
from app.services.wiki_compiler import compile_wiki, get_or_compile_wiki

router = APIRouter(prefix="/wiki", tags=["wiki"])


class WikiChipOut(BaseModel):
    label: str
    kind: str


class WikiSectionOut(BaseModel):
    key: str
    heading: str
    body: str
    chips: list[WikiChipOut] = []


class WikiPageOut(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    title: str
    sections: list[WikiSectionOut]
    generated_at: str
    model_version: str
    prompt_version: str
    is_stale: bool


def _serialize(page) -> WikiPageOut:
    return WikiPageOut(
        id=page.id,
        entity_type=page.entity_type,
        entity_id=page.entity_id,
        title=page.title,
        sections=[
            WikiSectionOut(
                key=s.get("key", ""),
                heading=s.get("heading", ""),
                body=s.get("body", ""),
                chips=[WikiChipOut(**c) for c in (s.get("chips") or [])],
            )
            for s in (page.sections or [])
        ],
        generated_at=page.generated_at.isoformat(),
        model_version=page.model_version or "template-v0.1",
        prompt_version=page.prompt_version or "v0.1",
        is_stale=bool(page.is_stale),
    )


@router.get("/paper/{paper_id}", response_model=WikiPageOut)
def get_paper_wiki(paper_id: str, session: Session = Depends(get_session)):
    """Return the wiki page for a paper, compiling it on-the-fly if needed."""
    try:
        page = get_or_compile_wiki(session, paper_id)
        session.commit()
        return _serialize(page)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/paper/{paper_id}/compile", response_model=WikiPageOut)
def recompile_paper_wiki(paper_id: str, session: Session = Depends(get_session)):
    """Force recompile the wiki page for a paper."""
    try:
        page = compile_wiki(session, paper_id)
        session.commit()
        return _serialize(page)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
