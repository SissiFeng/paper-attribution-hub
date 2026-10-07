"""Persist the staged screening decision for every classified paper.

This layer does not replace the classifier. It turns classifier output and
human-review state into an explicit route so broad-corpus scoring does not
silently become a request to review every paper.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.classification_labels import (
    LABEL_CORE,
    LABEL_RELATED,
    LABEL_SDL_FIELD,
    LABEL_UNCERTAIN,
    normalize_classification_label,
)
from app.config import settings
from app.label_dataset import (
    ensure_distinct_label_paths,
    load_label_dataset,
    load_reserved_evaluation_ids,
)
from app.models import Paper, PaperClassification

STAGE_SEED_REFERENCE = "SEED_REFERENCE"
STAGE_BROAD_SCORED = "BROAD_SCORED"
STAGE_HUMAN_REVIEW = "HUMAN_REVIEW"
STAGE_HUMAN_RESOLVED = "HUMAN_RESOLVED"

ROUTE_SEED = "SEED"
ROUTE_POSITIVE_REVIEW = "POSITIVE_REVIEW"
ROUTE_UNCERTAIN_REVIEW = "UNCERTAIN_REVIEW"
ROUTE_FULLTEXT_REVIEW = "FULLTEXT_REVIEW"
ROUTE_SCREENED_OUT = "SCREENED_OUT"
ROUTE_RESOLVED = "RESOLVED"

REVIEW_ROUTES = frozenset(
    {
        ROUTE_POSITIVE_REVIEW,
        ROUTE_UNCERTAIN_REVIEW,
        ROUTE_FULLTEXT_REVIEW,
    }
)
ROUTE_PRIORITY_FLOORS = {
    ROUTE_POSITIVE_REVIEW: 0.25,
    ROUTE_UNCERTAIN_REVIEW: 0.45,
    ROUTE_FULLTEXT_REVIEW: 0.45,
}
POSITIVE_LABELS = frozenset({LABEL_CORE, LABEL_RELATED, LABEL_SDL_FIELD})
DEFAULT_UNCERTAINTY_THRESHOLD = 0.75


@dataclass(frozen=True)
class ScreeningDecision:
    stage: str
    route: str
    reason: str


@dataclass(frozen=True)
class ScreeningSummary:
    scored: int
    stage_counts: dict[str, int]
    route_counts: dict[str, int]

    @property
    def review_subset(self) -> int:
        return sum(self.route_counts.get(route, 0) for route in REVIEW_ROUTES)

    def pipeline_fields(self) -> dict[str, int]:
        return {
            "scored": self.scored,
            "seed_reference": self.route_counts.get(ROUTE_SEED, 0),
            "positive_review": self.route_counts.get(
                ROUTE_POSITIVE_REVIEW, 0
            ),
            "uncertain_review": self.route_counts.get(
                ROUTE_UNCERTAIN_REVIEW, 0
            ),
            "fulltext_review": self.route_counts.get(
                ROUTE_FULLTEXT_REVIEW, 0
            ),
            "screened_out": self.route_counts.get(ROUTE_SCREENED_OUT, 0),
            "resolved": self.route_counts.get(ROUTE_RESOLVED, 0),
            "review_subset": self.review_subset,
        }


def _screening_boundaries(session: Session) -> tuple[set[str], set[str]]:
    if settings.sdl_stage1_only:
        from app.services.sdl_stage1_service import (
            stage1_assignment_ids,
            stage1_label_map,
        )

        training_ids = set(stage1_label_map(session, role="train"))
        reserved_ids = stage1_assignment_ids(
            session,
            roles={"validation", "frozen_test"},
        )
        return training_ids, reserved_ids
    ensure_distinct_label_paths(
        training=settings.training_labels_csv,
        validation=settings.validation_labels_csv,
        frozen_holdout=settings.eval_labels_csv,
    )
    training_ids = set(
        load_label_dataset(
            settings.training_labels_csv,
            role="training",
            allow_missing=True,
        )
    )
    reserved_ids = load_reserved_evaluation_ids(
        validation_path=settings.validation_labels_csv,
        holdout_path=settings.eval_labels_csv,
    )
    overlap = training_ids & reserved_ids
    if overlap:
        raise ValueError(
            "training seeds overlap validation or frozen holdout ids: "
            f"{sorted(overlap)}"
        )
    return training_ids, reserved_ids


def decide_screening_route(
    paper: Paper,
    classification: PaperClassification,
    *,
    training_ids: set[str],
    reserved_ids: set[str],
    uncertainty_threshold: float = DEFAULT_UNCERTAINTY_THRESHOLD,
) -> ScreeningDecision:
    """Return the single current route derived from auditable persisted state."""
    review = paper.review
    if review and review.review_status == "NEEDS_FULLTEXT":
        return ScreeningDecision(
            STAGE_HUMAN_REVIEW,
            ROUTE_FULLTEXT_REVIEW,
            "First-pass review found insufficient evidence; full text or "
            "supporting information is required.",
        )

    if paper.id in training_ids or (
        review and review.human_label and paper.id not in reserved_ids
    ):
        return ScreeningDecision(
            STAGE_SEED_REFERENCE,
            ROUTE_SEED,
            "Explicit training feedback; retained as a labeled seed and not "
            "returned to the review queue.",
        )

    if (
        classification.human_confirmed
        or (review and review.review_status == "COMPLETED")
        or (review and review.human_label and paper.id in reserved_ids)
    ):
        return ScreeningDecision(
            STAGE_HUMAN_RESOLVED,
            ROUTE_RESOLVED,
            "Human judgement is complete; excluded from automated re-routing.",
        )

    if settings.sdl_stage1_only:
        from app.services.sdl_stage1_service import stage1_assignment

        assignment = stage1_assignment(paper)
        if not assignment:
            return ScreeningDecision(
                STAGE_BROAD_SCORED,
                ROUTE_SCREENED_OUT,
                "SDL Stage 1 split manifest is not frozen; do not send this "
                "paper to human review yet.",
            )
        role = str(assignment.get("role") or "")
        if role == "pool":
            return ScreeningDecision(
                STAGE_BROAD_SCORED,
                ROUTE_SCREENED_OUT,
                "Unlabelled SDL Stage 1 reserve-pool paper; excluded from the "
                "current review batches.",
            )
        round_number = assignment.get("round")
        suffix = f" round {round_number}" if round_number is not None else ""
        return ScreeningDecision(
            STAGE_HUMAN_REVIEW,
            ROUTE_UNCERTAIN_REVIEW,
            f"Selected for the frozen SDL Stage 1 {role}{suffix} review batch.",
        )

    normalized_label = normalize_classification_label(classification.label)
    confidence = classification.confidence
    if (
        normalized_label is None
        or not math.isfinite(confidence)
        or not 0.0 <= confidence <= 1.0
    ):
        return ScreeningDecision(
            STAGE_HUMAN_REVIEW,
            ROUTE_UNCERTAIN_REVIEW,
            f"Unsupported classifier output ({classification.label}, "
            f"confidence {confidence}); human review required.",
        )

    if normalized_label in POSITIVE_LABELS:
        return ScreeningDecision(
            STAGE_HUMAN_REVIEW,
            ROUTE_POSITIVE_REVIEW,
            f"Predicted positive ({normalized_label}); route the positive "
            "subset to human review.",
        )

    if (
        normalized_label == LABEL_UNCERTAIN
        or confidence < uncertainty_threshold
    ):
        return ScreeningDecision(
            STAGE_HUMAN_REVIEW,
            ROUTE_UNCERTAIN_REVIEW,
            f"Uncertain prediction ({normalized_label}, confidence "
            f"{confidence:.2f}); human review required.",
        )

    return ScreeningDecision(
        STAGE_BROAD_SCORED,
        ROUTE_SCREENED_OUT,
        f"High-confidence non-positive prediction ({normalized_label}, "
        f"confidence {confidence:.2f}); retained in the scored "
        "corpus without entering the human queue.",
    )


def apply_staged_screening(
    session: Session,
    *,
    uncertainty_threshold: float = DEFAULT_UNCERTAINTY_THRESHOLD,
    commit: bool = True,
) -> ScreeningSummary:
    training_ids, reserved_ids = _screening_boundaries(session)
    stage_counts: Counter[str] = Counter()
    route_counts: Counter[str] = Counter()
    scored = 0

    classifications = session.execute(
        select(PaperClassification)
        .options(
            selectinload(PaperClassification.paper).selectinload(Paper.review),
        )
        .with_for_update()
    ).scalars()
    for classification in classifications:
        paper = classification.paper
        decision = _apply_decision(
            paper,
            classification,
            training_ids=training_ids,
            reserved_ids=reserved_ids,
            uncertainty_threshold=uncertainty_threshold,
        )
        scored += 1
        stage_counts[decision.stage] += 1
        route_counts[decision.route] += 1

    if commit:
        session.commit()
    else:
        session.flush()
    return ScreeningSummary(
        scored=scored,
        stage_counts=dict(stage_counts),
        route_counts=dict(route_counts),
    )


def apply_paper_screening(
    session: Session,
    paper: Paper,
    *,
    uncertainty_threshold: float = DEFAULT_UNCERTAINTY_THRESHOLD,
    commit: bool = True,
) -> ScreeningDecision | None:
    """Re-route one paper after review without weakening label boundaries.

    If the dataset boundary cannot be loaded, explicit feedback is treated as
    resolved but never promoted to a training seed. Bulk pipeline routing stays
    strict and fails so the audit log exposes the configuration problem.
    """
    classification = paper.classification
    if classification is None:
        return None
    try:
        training_ids, reserved_ids = _screening_boundaries(session)
    except (OSError, ValueError):
        training_ids, reserved_ids = set(), {paper.id}
    decision = _apply_decision(
        paper,
        classification,
        training_ids=training_ids,
        reserved_ids=reserved_ids,
        uncertainty_threshold=uncertainty_threshold,
    )
    if commit:
        session.commit()
    else:
        session.flush()
    return decision


def _apply_decision(
    paper: Paper,
    classification: PaperClassification,
    *,
    training_ids: set[str],
    reserved_ids: set[str],
    uncertainty_threshold: float,
) -> ScreeningDecision:
    decision = decide_screening_route(
        paper,
        classification,
        training_ids=training_ids,
        reserved_ids=reserved_ids,
        uncertainty_threshold=uncertainty_threshold,
    )
    classification.screening_stage = decision.stage
    classification.screening_route = decision.route
    classification.screening_reason = decision.reason
    classification.needs_review = decision.route in REVIEW_ROUTES
    if classification.needs_review:
        classification.review_priority = max(
            classification.review_priority,
            ROUTE_PRIORITY_FLOORS[decision.route],
        )
    else:
        classification.review_priority = 0.0
    return decision


def staged_screening_summary(session: Session) -> ScreeningSummary:
    stage_counts: Counter[str] = Counter()
    route_counts: Counter[str] = Counter()
    rows = session.execute(
        select(
            PaperClassification.screening_stage,
            PaperClassification.screening_route,
        )
    ).all()
    for stage, route in rows:
        if stage:
            stage_counts[stage] += 1
        if route:
            route_counts[route] += 1
    return ScreeningSummary(
        scored=len(rows),
        stage_counts=dict(stage_counts),
        route_counts=dict(route_counts),
    )
