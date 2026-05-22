from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Paper, PaperClassification, PaperEvidence
from app.schemas import (
    ClassificationOut,
    FulltextEvidenceOut,
    GraphSignalsOut,
    HumanReviewOut,
    PaperAuthorOut,
    PaperOut,
    PipelineStats,
)
from app.services.filter_spec import PaperFilter, apply_filter, paper_filter_query

router = APIRouter(prefix="/papers", tags=["papers"])


def _paper_to_schema(paper: Paper, evidence_rows: list[PaperEvidence] | None = None) -> PaperOut:
    cls_out: ClassificationOut | None = None
    if paper.classification:
        c = paper.classification
        cls_out = ClassificationOut(
            label=c.label,
            confidence=c.confidence,
            author_score=c.author_score,
            institution_score=c.institution_score,
            topic_score=c.topic_score,
            network_score=c.network_score,
            fulltext_evidence_score=c.fulltext_evidence_score or 0.0,
            citation_score=c.citation_score or 0.0,
            matched_people=c.matched_people or [],
            matched_institutions=c.matched_institutions or [],
            matched_topics=c.matched_topics or [],
            reasons=c.reasons or [],
            model_version=c.model_version,
            created_at=c.created_at,
            graph_signals=GraphSignalsOut(**c.graph_signals) if c.graph_signals else None,
            fulltext_evidence=[
                FulltextEvidenceOut(
                    id=e.id,
                    chunk_id=e.chunk_id,
                    evidence_type=e.evidence_type,
                    evidence_source=e.evidence_source,
                    evidence_text=e.evidence_text,
                    score=e.score,
                )
                for e in (evidence_rows or [])
            ],
        )
    review_out: HumanReviewOut | None = None
    if paper.review:
        r = paper.review
        review_out = HumanReviewOut(
            paper_id=paper.id,
            human_label=r.human_label,
            corrected_topics=r.corrected_topics,
            corrected_people=r.corrected_people,
            reviewer=r.reviewer,
            notes=r.notes,
            created_at=r.created_at,
        )
    return PaperOut(
        id=paper.id,
        title=paper.title,
        abstract=paper.abstract,
        year=paper.year,
        venue=paper.venue,
        doi=paper.doi,
        keywords=paper.keywords,
        full_text_available=bool(paper.full_text_available),
        provenance=getattr(paper, "provenance", "csv") or "csv",
        authors=[
            PaperAuthorOut(
                name=pa.author.canonical_name,
                order=pa.author_order,
                affiliation=pa.affiliation_text,
            )
            for pa in paper.authors
        ],
        classification=cls_out,
        review=review_out,
    )


@router.get("", response_model=list[PaperOut])
def list_papers(
    filt: PaperFilter = Depends(paper_filter_query),
    # Back-compat aliases — older clients send `label` and `min_confidence`.
    label: str | None = Query(default=None, deprecated=True),
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0, deprecated=True),
    session: Session = Depends(get_session),
) -> list[PaperOut]:
    if label and not filt.labels:
        filt.labels = [label]
    if min_confidence is not None and filt.min_confidence is None:
        filt.min_confidence = min_confidence

    stmt = apply_filter(select(Paper), filt)
    papers = list(session.execute(stmt).scalars())
    evidence_index = _evidence_by_paper(session, [p.id for p in papers])
    return [_paper_to_schema(p, evidence_index.get(p.id, [])) for p in papers]


def _evidence_by_paper(session: Session, paper_ids: list[str]) -> dict[str, list[PaperEvidence]]:
    if not paper_ids:
        return {}
    rows = (
        session.execute(
            select(PaperEvidence).where(PaperEvidence.paper_id.in_(paper_ids))
        )
        .scalars()
        .all()
    )
    out: dict[str, list[PaperEvidence]] = {}
    for r in rows:
        out.setdefault(r.paper_id, []).append(r)
    return out


@router.get("/stats", response_model=PipelineStats)
def stats(session: Session = Depends(get_session)) -> PipelineStats:
    from app.models import Author, Institution, Topic

    papers = list(session.execute(select(Paper)).scalars())
    label_counts: dict[str, int] = {}
    last_run = None
    for p in papers:
        if p.classification:
            label_counts[p.classification.label] = label_counts.get(p.classification.label, 0) + 1
            if last_run is None or p.classification.created_at > last_run:
                last_run = p.classification.created_at
    return PipelineStats(
        papers=len(papers),
        authors=session.scalar(select(__import__("sqlalchemy").func.count(Author.id))) or 0,
        institutions=session.scalar(
            select(__import__("sqlalchemy").func.count(Institution.id))
        )
        or 0,
        topics=session.scalar(select(__import__("sqlalchemy").func.count(Topic.id))) or 0,
        classifications=label_counts,
        last_run_at=last_run,
    )


@router.get("/export.csv", include_in_schema=True)
def export_csv(
    filt: PaperFilter = Depends(paper_filter_query),
    label: str | None = Query(default=None, deprecated=True),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    if label and not filt.labels:
        filt.labels = [label]
    stmt = apply_filter(select(Paper), filt)
    papers = list(session.execute(stmt).scalars())

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "paper_id",
            "title",
            "year",
            "venue",
            "doi",
            "authors",
            "matched_ac_people",
            "matched_partner_institutions",
            "matched_topics",
            "label",
            "confidence",
            "author_score",
            "institution_score",
            "topic_score",
            "reasons",
            "human_label",
        ]
    )
    for p in papers:
        c = p.classification
        r = p.review
        writer.writerow(
            [
                p.id,
                p.title,
                p.year or "",
                p.venue or "",
                p.doi or "",
                "; ".join(pa.author.canonical_name for pa in p.authors),
                "; ".join(
                    m["name"] for m in (c.matched_people or []) if c
                ) if c else "",
                "; ".join(
                    m["canonical_name"]
                    for m in (c.matched_institutions or [])
                    if c and m.get("is_partner")
                )
                if c
                else "",
                "; ".join(m["name"] for m in (c.matched_topics or []) if c) if c else "",
                c.label if c else "",
                f"{c.confidence:.3f}" if c else "",
                f"{c.author_score:.3f}" if c else "",
                f"{c.institution_score:.3f}" if c else "",
                f"{c.topic_score:.3f}" if c else "",
                " | ".join(c.reasons or []) if c else "",
                r.human_label if r else "",
            ]
        )

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="paper_attribution_export.csv"'
        },
    )


@router.get("/{paper_id}", response_model=PaperOut)
def get_paper(paper_id: str, session: Session = Depends(get_session)) -> PaperOut:
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail=f"Paper {paper_id} not found")
    evidence_rows = _evidence_by_paper(session, [paper.id]).get(paper.id, [])
    return _paper_to_schema(paper, evidence_rows)
