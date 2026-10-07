from __future__ import annotations

import logging
from typing import Any, Callable, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import require_api_key
from app.config import settings
from app.db import get_session
from app.models import WikiPage
from app.services.wiki_compiler import (
    WikiPaperNotFoundError,
    compile_wiki,
    get_or_compile_wiki,
    record_compile_interruption,
)
from app.services.wiki_synthesis_service import (
    WikiSynthesisNotFoundError,
    WikiSynthesisValidationError,
    archive_chat_synthesis,
    get_synthesis,
    review_synthesis,
)
from app.services.llm_wiki_lifecycle import lint_llm_wiki_vault

router = APIRouter(prefix="/wiki", tags=["wiki"])
logger = logging.getLogger(__name__)


class WikiChipOut(BaseModel):
    label: str
    kind: str


class WikiSectionOut(BaseModel):
    key: str
    heading: str
    body: str
    chips: list[WikiChipOut] = Field(default_factory=list)


class WikiPageOut(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    title: str
    sections: list[WikiSectionOut]
    generated_at: str
    model_version: str
    prompt_version: str
    content_md: str | None
    source_snapshot_hash: str | None
    content_hash: str | None
    source_metadata: dict[str, Any]
    compile_status: str
    is_stale: bool


class WikiSynthesisArchiveIn(BaseModel):
    chat_message_id: str = Field(min_length=1, max_length=128)
    title: str | None = Field(default=None, max_length=240)


class WikiSynthesisReviewIn(BaseModel):
    status: Literal["reviewed", "superseded"]
    reviewer: str = Field(min_length=1, max_length=160)
    note: str | None = Field(default=None, max_length=2000)


class WikiSynthesisOut(BaseModel):
    id: str
    title: str
    review_status: str
    authority: str
    generated_at: str
    source_metadata: dict[str, Any]
    content_md: str | None
    content_hash: str | None
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
        content_md=page.content_md,
        source_snapshot_hash=page.source_snapshot_hash,
        content_hash=page.content_hash,
        source_metadata=page.source_metadata or {},
        compile_status=page.compile_status or "complete",
        is_stale=bool(page.is_stale),
    )


def _serialize_synthesis(page: WikiPage) -> WikiSynthesisOut:
    metadata = page.source_metadata or {}
    return WikiSynthesisOut(
        id=page.id,
        title=page.title,
        review_status=str(metadata.get("review_status") or "draft"),
        authority=str(metadata.get("authority") or "draft_synthesis"),
        generated_at=page.generated_at.isoformat(),
        source_metadata=metadata,
        content_md=page.content_md,
        content_hash=page.content_hash,
        is_stale=bool(page.is_stale),
    )


def _compile_or_http_error(
    *,
    session: Session,
    paper_id: str,
    compiler: Callable[[Session, str], WikiPage],
) -> WikiPageOut:
    try:
        page = compiler(session, paper_id)
        session.commit()
        return _serialize(page)
    except WikiPaperNotFoundError as error:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(error)) from error
    except Exception as error:
        session.rollback()
        logger.exception("Wiki compilation interrupted for paper %s", paper_id)
        try:
            record_compile_interruption(session, paper_id, error)
            session.commit()
        except Exception:
            session.rollback()
            logger.exception(
                "Could not persist wiki interruption state for paper %s", paper_id
            )
        raise HTTPException(
            status_code=500,
            detail="Wiki compilation interrupted; retry is safe.",
        ) from error


@router.get("/paper/{paper_id}", response_model=WikiPageOut)
def get_paper_wiki(paper_id: str, session: Session = Depends(get_session)):
    """Return the wiki page for a paper, compiling it on-the-fly if needed."""
    return _compile_or_http_error(
        session=session,
        paper_id=paper_id,
        compiler=get_or_compile_wiki,
    )


@router.post("/paper/{paper_id}/compile", response_model=WikiPageOut)
def recompile_paper_wiki(paper_id: str, session: Session = Depends(get_session)):
    """Recompute the wiki page; unchanged inputs remain a no-op."""
    return _compile_or_http_error(
        session=session,
        paper_id=paper_id,
        compiler=compile_wiki,
    )


@router.post(
    "/syntheses",
    response_model=WikiSynthesisOut,
    dependencies=[Depends(require_api_key)],
)
def archive_synthesis(
    payload: WikiSynthesisArchiveIn,
    response: Response,
    session: Session = Depends(get_session),
):
    """Archive a persisted answer as a non-authoritative synthesis draft."""
    try:
        page, created = archive_chat_synthesis(
            session,
            chat_message_id=payload.chat_message_id,
            title=payload.title,
        )
        session.commit()
    except WikiSynthesisNotFoundError as error:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(error)) from error
    except WikiSynthesisValidationError as error:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    response.status_code = 201 if created else 200
    return _serialize_synthesis(page)


@router.get("/syntheses", response_model=list[WikiSynthesisOut])
def list_syntheses(
    review_status: Literal["draft", "reviewed", "superseded"] | None = Query(
        default=None
    ),
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
):
    """List synthesis drafts or reviewed knowledge for curator workflows."""
    query = select(WikiPage).where(WikiPage.entity_type == "synthesis")
    if review_status is not None:
        query = query.where(
            WikiPage.source_metadata["review_status"].as_string() == review_status
        )
    pages = session.execute(
        query.order_by(WikiPage.generated_at.desc(), WikiPage.id).limit(limit)
    ).scalars()
    return [_serialize_synthesis(page) for page in pages]


@router.get("/syntheses/{synthesis_id}", response_model=WikiSynthesisOut)
def get_synthesis_detail(
    synthesis_id: str,
    session: Session = Depends(get_session),
):
    try:
        return _serialize_synthesis(get_synthesis(session, synthesis_id))
    except WikiSynthesisNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/syntheses/{synthesis_id}/review",
    response_model=WikiSynthesisOut,
    dependencies=[Depends(require_api_key)],
)
def review_synthesis_page(
    synthesis_id: str,
    payload: WikiSynthesisReviewIn,
    session: Session = Depends(get_session),
):
    """Promote grounded work or explicitly retire it; never infer review."""
    try:
        page = review_synthesis(
            session,
            synthesis_id=synthesis_id,
            status=payload.status,
            reviewer=payload.reviewer,
            note=payload.note,
        )
        session.commit()
        return _serialize_synthesis(page)
    except WikiSynthesisNotFoundError as error:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(error)) from error
    except WikiSynthesisValidationError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/lint")
def lint_live_wiki(
    stale_after_days: int = Query(default=30, ge=0, le=3650),
) -> dict[str, Any]:
    """Return a read-only health report for the complete live wiki vault."""
    return lint_llm_wiki_vault(
        settings.llm_wiki_root,
        stale_after_days=stale_after_days,
    ).to_dict()
