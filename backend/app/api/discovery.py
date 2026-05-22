from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import DiscoveryCandidate
from app.schemas import (
    DiscoveryCandidateOut,
    DiscoveryReviewIn,
    DiscoveryRunRequest,
    DiscoveryRunResult,
    DiscoveryTriggerOut,
)
from app.services.discovery_service import (
    approve_candidate,
    reject_candidate,
    run_discovery,
)

router = APIRouter(prefix="/discovery", tags=["discovery"])


def _to_out(row: DiscoveryCandidate) -> DiscoveryCandidateOut:
    return DiscoveryCandidateOut(
        id=row.id,
        external_id=row.external_id,
        doi=row.doi,
        title=row.title,
        abstract=row.abstract,
        year=row.year,
        venue=row.venue,
        authors=list(row.authors or []),
        affiliations=list(row.affiliations or []),
        source=row.source,
        triggers=[DiscoveryTriggerOut(**t) for t in (row.triggers or [])],
        confidence=row.confidence,
        auto_eligible=row.auto_eligible,
        status=row.status,
        reviewer=row.reviewer,
        review_notes=row.review_notes,
        resulting_paper_id=row.resulting_paper_id,
        created_at=row.created_at,
        reviewed_at=row.reviewed_at,
    )


@router.post("/run", response_model=DiscoveryRunResult)
def run(
    payload: DiscoveryRunRequest = DiscoveryRunRequest(),
    session: Session = Depends(get_session),
) -> DiscoveryRunResult:
    """Kick off a discovery cycle. Hits external APIs (cached). May take seconds."""
    result = run_discovery(
        session,
        strategies=payload.strategies,
        max_candidates=payload.max_candidates,
    )
    return DiscoveryRunResult(
        candidates_seen=result.candidates_seen,
        auto_ingested=result.auto_ingested,
        queued=result.queued,
        skipped_already_in_corpus=result.skipped_already_in_corpus,
        by_strategy=result.by_strategy,
    )


@router.get("/queue", response_model=list[DiscoveryCandidateOut])
def list_queue(
    status: str = Query(default="queued"),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[DiscoveryCandidateOut]:
    stmt = (
        select(DiscoveryCandidate)
        .where(DiscoveryCandidate.status == status)
        .order_by(DiscoveryCandidate.confidence.desc(), DiscoveryCandidate.created_at.desc())
        .limit(limit)
    )
    return [_to_out(r) for r in session.execute(stmt).scalars()]


@router.post("/queue/{candidate_id}/approve", response_model=DiscoveryCandidateOut)
def approve(
    candidate_id: str,
    payload: DiscoveryReviewIn = DiscoveryReviewIn(),
    session: Session = Depends(get_session),
) -> DiscoveryCandidateOut:
    try:
        approve_candidate(
            session, candidate_id, reviewer=payload.reviewer, notes=payload.notes
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    row = session.get(DiscoveryCandidate, candidate_id)
    assert row is not None
    return _to_out(row)


@router.post("/queue/{candidate_id}/reject", response_model=DiscoveryCandidateOut)
def reject(
    candidate_id: str,
    payload: DiscoveryReviewIn = DiscoveryReviewIn(),
    session: Session = Depends(get_session),
) -> DiscoveryCandidateOut:
    try:
        reject_candidate(
            session, candidate_id, reviewer=payload.reviewer, notes=payload.notes
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    row = session.get(DiscoveryCandidate, candidate_id)
    assert row is not None
    return _to_out(row)
