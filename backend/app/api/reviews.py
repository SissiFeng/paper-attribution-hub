from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.auth import require_api_key
from app.classification_labels import REVIEW_LABELS
from app.config import settings
from app.db import get_session
from app.models import HumanReview, Paper
from app.schemas import HumanReviewIn, HumanReviewOut
from app.services.active_learning import on_review_submitted
from app.services.staged_screening import apply_paper_screening
from app.services.stage1_readiness import (
    STAGE1_NOT_READY_DETAIL,
    derived_views_available,
)

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post(
    "/{paper_id}",
    response_model=HumanReviewOut,
    dependencies=[Depends(require_api_key)],
)
def submit_review(
    paper_id: str,
    payload: HumanReviewIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> HumanReviewOut:
    if not derived_views_available(session):
        raise HTTPException(status_code=409, detail=STAGE1_NOT_READY_DETAIL)
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail=f"Paper {paper_id} not found")
    normalized_human_label = (
        payload.human_label.upper() if payload.human_label else None
    )
    if (
        normalized_human_label is not None
        and normalized_human_label not in REVIEW_LABELS
    ):
        raise HTTPException(
            status_code=422,
            detail=f"human_label must be one of {sorted(REVIEW_LABELS)}",
        )

    review = paper.review
    previous_label = (
        review.human_label
        if review and review.human_label
        else (paper.classification.label if paper.classification else None)
    )
    if review is None:
        review = HumanReview(id=f"rev_{uuid.uuid4().hex[:12]}", paper_id=paper_id)
        paper.review = review
        session.add(review)
    if payload.human_label is not None:
        review.human_label = normalized_human_label
    dimensional_review = any(
        (
            payload.sdl_judgement,
            payload.ac_relevance_judgement,
            payload.ai_for_science_judgement,
        )
    )
    if dimensional_review:
        review.sdl_judgement = payload.sdl_judgement
        review.ac_relevance_judgement = payload.ac_relevance_judgement
        review.ai_for_science_judgement = payload.ai_for_science_judgement
        if settings.sdl_stage1_only:
            review.review_status = payload.review_status or (
                "NEEDS_FULLTEXT"
                if payload.sdl_judgement == "INSUFFICIENT_EVIDENCE"
                else "COMPLETED"
            )
        else:
            review.review_status = payload.review_status or (
                "NEEDS_FULLTEXT"
                if "INSUFFICIENT_EVIDENCE"
                in {
                    payload.sdl_judgement,
                    payload.ac_relevance_judgement,
                }
                else (
                    "COMPLETED"
                    if payload.sdl_judgement
                    and payload.ac_relevance_judgement
                    else "PARTIAL"
                )
            )
        review.evidence_level = payload.evidence_level
        review.judgement_basis = payload.judgement_basis
    review.corrected_topics = payload.corrected_topics
    review.corrected_people = payload.corrected_people
    review.reviewer = payload.reviewer
    review.notes = payload.notes
    review.disagreement_type = payload.disagreement_type
    review.rationale = payload.rationale
    review.evidence = payload.evidence
    review.future_rule_update = payload.future_rule_update

    if paper.classification is not None and normalized_human_label is not None:
        cls = paper.classification
        cls.disagreement_type = payload.disagreement_type
        cls.future_rule_update = payload.future_rule_update
        cls.model_agreement_status = (
            "human_confirmed"
            if previous_label == normalized_human_label
            else "human_corrected"
        )
    if (
        paper.classification is not None
        and review.review_status == "COMPLETED"
    ):
        paper.classification.needs_review = False
        paper.classification.review_priority = 0.0
    session.commit()
    session.refresh(review)

    # Stage 1 labels flow through the frozen batch manifest, never through the
    # legacy AC-oriented active-learning path.
    learning_actions = None
    if (
        not settings.sdl_stage1_only
        and normalized_human_label is not None
        and os.environ.get("PAS_ACTIVE_LEARNING", "1") == "1"
    ):
        try:
            learning_actions = on_review_submitted(
                session,
                paper_id,
                new_label=normalized_human_label,
                previous_label=previous_label,
                reviewer=review.reviewer,
                run_retraining=False,
            )
            if learning_actions["training_feedback_recorded"]:
                from app.services.model_evolution import (
                    run_model_evolution_background,
                )

                background_tasks.add_task(run_model_evolution_background)
        except Exception:
            # Active learning must never break submit.
            pass
    apply_paper_screening(session, paper)

    return HumanReviewOut(
        paper_id=review.paper_id,
        human_label=review.human_label,
        sdl_judgement=review.sdl_judgement,
        ac_relevance_judgement=review.ac_relevance_judgement,
        ai_for_science_judgement=review.ai_for_science_judgement,
        review_status=review.review_status,
        evidence_level=review.evidence_level,
        judgement_basis=review.judgement_basis,
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
