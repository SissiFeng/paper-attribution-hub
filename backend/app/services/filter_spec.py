"""Unified paper filter used by /papers, /papers/export.csv, /analytics/*.

Why this exists: figure.md is explicit that analytics charts must come from
structured DB queries, not RAG. That means the same filter has to drive the
table view, the Sankey, the timeline, and the institution network. A single
Pydantic spec + one SQLAlchemy helper guarantees they stay in sync.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Query
from pydantic import BaseModel, Field
from sqlalchemy import Select, String, exists, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Author,
    HumanReview,
    Institution,
    Paper,
    PaperAuthor,
    PaperClassification,
)


class PaperFilter(BaseModel):
    """Filter parameters accepted by every paper-listing or analytics endpoint."""

    year_from: int | None = None
    year_to: int | None = None
    labels: list[str] = Field(default_factory=list)
    topic_ids: list[str] = Field(default_factory=list)
    institution_ids: list[str] = Field(default_factory=list)
    partner_only: bool = False
    ac_author_only: bool = False
    has_fulltext: bool | None = None
    has_review: bool | None = None
    min_confidence: float | None = None
    max_confidence: float | None = None
    search: str | None = None

    def is_empty(self) -> bool:
        return self.model_dump(exclude_defaults=True) == {}


def paper_filter_query(
    year_from: Annotated[int | None, Query()] = None,
    year_to: Annotated[int | None, Query()] = None,
    labels: Annotated[list[str] | None, Query()] = None,
    topic_ids: Annotated[list[str] | None, Query()] = None,
    institution_ids: Annotated[list[str] | None, Query()] = None,
    partner_only: Annotated[bool, Query()] = False,
    ac_author_only: Annotated[bool, Query()] = False,
    has_fulltext: Annotated[bool | None, Query()] = None,
    has_review: Annotated[bool | None, Query()] = None,
    min_confidence: Annotated[float | None, Query(ge=0.0, le=1.0)] = None,
    max_confidence: Annotated[float | None, Query(ge=0.0, le=1.0)] = None,
    search: Annotated[str | None, Query()] = None,
) -> PaperFilter:
    """FastAPI dependency that turns query params into a PaperFilter."""
    return PaperFilter(
        year_from=year_from,
        year_to=year_to,
        labels=labels or [],
        topic_ids=topic_ids or [],
        institution_ids=institution_ids or [],
        partner_only=partner_only,
        ac_author_only=ac_author_only,
        has_fulltext=has_fulltext,
        has_review=has_review,
        min_confidence=min_confidence,
        max_confidence=max_confidence,
        search=search,
    )


def apply_filter(stmt: Select, filt: PaperFilter) -> Select:
    """Apply a PaperFilter to a Select that returns Paper rows."""
    if filt.year_from is not None:
        stmt = stmt.where(Paper.year >= filt.year_from)
    if filt.year_to is not None:
        stmt = stmt.where(Paper.year <= filt.year_to)
    if filt.has_fulltext is not None:
        stmt = stmt.where(Paper.full_text_available.is_(filt.has_fulltext))
    if filt.search:
        like = f"%{filt.search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Paper.title).like(like),
                func.lower(Paper.abstract).like(like),
            )
        )

    if (
        filt.labels
        or filt.min_confidence is not None
        or filt.max_confidence is not None
        or filt.topic_ids
    ):
        # Use EXISTS subquery instead of JOIN so we never produce duplicate rows
        # (JOIN on a 1:1 relationship is safe, but DISTINCT on JSON columns fails
        # in PostgreSQL because json has no equality operator).
        cls_conds = [PaperClassification.paper_id == Paper.id]
        if filt.labels:
            cls_conds.append(PaperClassification.label.in_([l.upper() for l in filt.labels]))
        if filt.min_confidence is not None:
            cls_conds.append(PaperClassification.confidence >= filt.min_confidence)
        if filt.max_confidence is not None:
            cls_conds.append(PaperClassification.confidence <= filt.max_confidence)
        if filt.topic_ids:
            for tid in filt.topic_ids:
                like_pattern = f'%"topic_id": "{tid}"%'
                cls_conds.append(
                    func.cast(PaperClassification.matched_topics, String).like(like_pattern)
                )
        stmt = stmt.where(
            exists(select(1).select_from(PaperClassification).where(*cls_conds))
        )

    if filt.has_review is True:
        stmt = stmt.where(exists().where(HumanReview.paper_id == Paper.id))
    elif filt.has_review is False:
        stmt = stmt.where(~exists().where(HumanReview.paper_id == Paper.id))

    if filt.ac_author_only or filt.institution_ids or filt.partner_only:
        # Join through paper_authors → authors → institutions for these filters.
        pa = PaperAuthor.__table__
        au = Author.__table__
        inst = Institution.__table__
        stmt = stmt.where(
            exists().select_from(pa.join(au, au.c.id == pa.c.author_id))
            .where(pa.c.paper_id == Paper.id)
            .where(
                (au.c.is_ac_member.is_(True))
                if filt.ac_author_only
                else True
            )
        )
        if filt.institution_ids or filt.partner_only:
            stmt = stmt.where(
                exists()
                .select_from(
                    pa.join(au, au.c.id == pa.c.author_id).join(
                        inst, inst.c.id == au.c.institution_id
                    )
                )
                .where(pa.c.paper_id == Paper.id)
                .where(
                    inst.c.id.in_(filt.institution_ids)
                    if filt.institution_ids
                    else inst.c.is_partner.is_(True)
                )
            )

    return stmt


def filtered_paper_ids(session: Session, filt: PaperFilter) -> list[str]:
    """Helper that returns the paper-id list matching the filter."""
    stmt = apply_filter(select(Paper.id), filt)
    return [pid for (pid,) in session.execute(stmt).all()]
