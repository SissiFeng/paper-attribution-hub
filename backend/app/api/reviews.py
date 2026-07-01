from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.auth import require_api_key
from app.db import get_session
from app.models import HumanReview, Paper
from app.schemas import HumanReviewIn, HumanReviewOut
from app.services.active_learning import on_review_submitted

router = APIRouter(prefix="/reviews", tags=["reviews"])

VALID_LABELS = {
    "CORE_RELEVANT",
    "RELATED_RELEVANT",
    "ADJACENT",
    "UNCERTAIN",
    "EXCLUDE",
    "INCLUDE",
    "SDL_FIELD_RELEVANT",
}


@router.post(
    "/{paper_id}",
    response_model=HumanReviewOut,
    dependencies=[Depends(require_api_key)],
)
def submit_review(
    paper_id: str, payload: HumanReviewIn, session: Session = Depends(get_session)
) -> HumanReviewOut:
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail=f"Paper {paper_id} not found")
    if payload.human_label.upper() not in VALID_LABELS:
        raise HTTPException(
            status_code=422,
            detail=f"human_label must be one of {sorted(VALID_LABELS)}",
        )

    review = paper.review
    previous_label = review.human_label if review else (
        paper.classification.label if paper.classification else None
    )
    if review is None:
        review = HumanReview(id=f"rev_{uuid.uuid4().hex[:12]}", paper_id=paper_id)
        session.add(review)
    review.human_label = payload.human_label.upper()
    review.corrected_topics = payload.corrected_topics
    review.corrected_people = payload.corrected_people
    review.reviewer = payload.reviewer
    review.notes = payload.notes
    review.disagreement_type = payload.disagreement_type
    review.rationale = payload.rationale
    review.evidence = payload.evidence
    review.future_rule_update = payload.future_rule_update

    if paper.classification is not None:
        cls = paper.classification
        cls.disagreement_type = payload.disagreement_type
        cls.future_rule_update = payload.future_rule_update
        cls.model_agreement_status = (
            "human_confirmed"
            if previous_label == review.human_label
            else "human_corrected"
        )
    session.commit()
    session.refresh(review)

    # v0.7: active learning is on by default; tests/ops can opt out with
    # PAS_ACTIVE_LEARNING=0.
    if os.environ.get("PAS_ACTIVE_LEARNING", "1") == "1":
        try:
            on_review_submitted(
                session,
                paper_id,
                new_label=review.human_label,
                previous_label=previous_label,
                reviewer=review.reviewer,
            )
        except Exception:
            # Active learning must never break submit.
            pass

    return HumanReviewOut(
        paper_id=review.paper_id,
        human_label=review.human_label,
        corrected_topics=review.corrected_topics,
        corrected_people=review.corrected_people,
        reviewer=review.reviewer,
        notes=review.notes,
        disagreement_type=review.disagreement_type,
        rationale=review.rationale,
        evidence=review.evidence,
        future_rule_update=review.future_rule_update,
        created_at=review.created_at,
    )
