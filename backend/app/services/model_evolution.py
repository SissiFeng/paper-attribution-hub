"""Human-feedback-driven full retraining with auditable promotion gates.

Every eligible review-label change becomes an immutable feedback event. Once
20 distinct reviewed papers are pending (configurable for tests/operations),
the service claims one batch under a database lock, retrains the learned
classifier from scratch on the complete allowed training set, evaluates the
candidate without training on the evaluation fold, and promotes it only when
it improves without regressing protected metrics.

The frozen holdout is never consulted here. It remains a release-only gate.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from threading import Event, Thread

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.classification_labels import normalize_classification_label
from app.config import settings
from app.label_dataset import load_reserved_evaluation_ids
from app.models import (
    HumanReview,
    ModelTrainingRun,
    ModelTrainingState,
    Paper,
    TrainingFeedbackEvent,
)

_STATE_ID = "learned_classifier"
_OOF_MAX_SPLITS = 5
_OOF_RANDOM_STATE = 42
_HYBRID_MIN_CONFIDENCE = 0.75
_HYBRID_MIN_MARGIN = 0.15


@dataclass(frozen=True)
class PromotionDecision:
    accepted: bool
    reason: str
    evaluation_scope: str
    candidate_metrics: dict
    incumbent_metrics: dict
    validation_candidate_metrics: dict | None
    validation_incumbent_metrics: dict | None


def retrain_batch_size() -> int:
    return _positive_int_env("PAS_ACTIVE_RETRAIN_EVERY", 20)


def minimum_validation_examples() -> int:
    return _nonnegative_int_env("PAS_MODEL_MIN_VALIDATION_EXAMPLES", 20)


def minimum_validation_labels() -> int:
    return _nonnegative_int_env("PAS_MODEL_MIN_VALIDATION_LABELS", 2)


def auto_promotion_enabled() -> bool:
    """Return whether a passing candidate may replace production authority."""
    return os.environ.get("PAS_MODEL_AUTO_PROMOTE", "0").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def validation_readiness(validation_examples: list[dict]) -> dict:
    observed_examples = len(validation_examples)
    observed_labels = sorted(
        {example["label"] for example in validation_examples}
    )
    required_examples = minimum_validation_examples()
    required_labels = minimum_validation_labels()
    ready = (
        observed_examples >= required_examples
        and len(observed_labels) >= required_labels
    )
    if ready:
        reason = "fixed validation gate is ready"
    elif observed_examples < required_examples:
        reason = (
            "fixed validation gate requires at least "
            f"{required_examples} examples; found {observed_examples}"
        )
    else:
        reason = (
            "fixed validation gate requires at least "
            f"{required_labels} labels; found {len(observed_labels)}"
        )
    return {
        "ready": ready,
        "required_examples": required_examples,
        "observed_examples": observed_examples,
        "required_labels": required_labels,
        "observed_labels": observed_labels,
        "reason": reason,
    }


def record_training_feedback(
    session: Session,
    *,
    paper_id: str,
    review_id: str,
    human_label: str,
    reviewer: str | None,
    incumbent_label: str | None,
    incumbent_confidence: float | None,
    commit: bool = True,
) -> TrainingFeedbackEvent | None:
    """Persist one immutable label-change event.

    Re-submitting the same current label is idempotent. A later correction to
    another label creates a new event and can trigger a future full retrain.
    """
    normalized = normalize_classification_label(human_label)
    if normalized is None:
        raise ValueError(f"unsupported training label: {human_label!r}")
    review = session.get(HumanReview, review_id)
    if review is None or review.paper_id != paper_id:
        raise ValueError("training feedback must reference its persisted review")
    if review.review_status not in {None, "COMPLETED"}:
        return None
    reserved_paper_ids = load_reserved_evaluation_ids(
        validation_path=settings.validation_labels_csv,
        holdout_path=settings.eval_labels_csv,
    )
    if paper_id in reserved_paper_ids:
        return None

    latest = _latest_feedback_for_paper(session, paper_id)
    if latest is not None and latest.human_label == normalized:
        return None

    event = _new_feedback_event(
        review=review,
        human_label=normalized,
        reviewer=reviewer,
        incumbent_label=incumbent_label,
        incumbent_confidence=incumbent_confidence,
    )
    session.add(event)
    if commit:
        session.commit()
        session.refresh(event)
    else:
        session.flush()
    return event


def reconcile_training_feedback(session: Session) -> int:
    """Backfill missing events for eligible persisted reviews, idempotently."""
    reserved_paper_ids = load_reserved_evaluation_ids(
        validation_path=settings.validation_labels_csv,
        holdout_path=settings.eval_labels_csv,
    )
    latest_by_paper: dict[str, TrainingFeedbackEvent] = {}
    for event in session.execute(
        select(TrainingFeedbackEvent)
        .where(TrainingFeedbackEvent.retired_at.is_(None))
        .order_by(
            TrainingFeedbackEvent.created_at.asc(),
            TrainingFeedbackEvent.id.asc(),
        )
    ).scalars():
        latest_by_paper[event.paper_id] = event

    added = 0
    reviews = session.execute(select(HumanReview)).scalars()
    for review in reviews:
        normalized = normalize_classification_label(review.human_label)
        if (
            normalized is None
            or review.review_status not in {None, "COMPLETED"}
            or review.paper_id in reserved_paper_ids
        ):
            continue
        latest = latest_by_paper.get(review.paper_id)
        if latest is not None and latest.human_label == normalized:
            continue
        paper = session.get(Paper, review.paper_id)
        classification = paper.classification if paper is not None else None
        event = _new_feedback_event(
            review=review,
            human_label=normalized,
            reviewer=review.reviewer,
            incumbent_label=(
                classification.label if classification is not None else None
            ),
            incumbent_confidence=(
                classification.confidence
                if classification is not None
                else None
            ),
        )
        session.add(event)
        latest_by_paper[review.paper_id] = event
        added += 1
    if added:
        session.commit()
    return added


def _latest_feedback_for_paper(
    session: Session,
    paper_id: str,
) -> TrainingFeedbackEvent | None:
    return session.execute(
        select(TrainingFeedbackEvent)
        .where(
            TrainingFeedbackEvent.paper_id == paper_id,
            TrainingFeedbackEvent.retired_at.is_(None),
        )
        .order_by(
            TrainingFeedbackEvent.created_at.desc(),
            TrainingFeedbackEvent.id.desc(),
        )
        .limit(1)
    ).scalar_one_or_none()


def _new_feedback_event(
    *,
    review: HumanReview,
    human_label: str,
    reviewer: str | None,
    incumbent_label: str | None,
    incumbent_confidence: float | None,
) -> TrainingFeedbackEvent:
    return TrainingFeedbackEvent(
        id=f"feedback_{uuid.uuid4().hex}",
        review_id=review.id,
        paper_id=review.paper_id,
        human_label=human_label,
        reviewer=reviewer,
        incumbent_label=normalize_classification_label(incumbent_label),
        incumbent_confidence=incumbent_confidence,
    )


def _reserved_evaluation_ids() -> set[str]:
    return load_reserved_evaluation_ids(
        validation_path=settings.validation_labels_csv,
        holdout_path=settings.eval_labels_csv,
    )


def _feedback_ineligibility_reason(
    session: Session,
    event: TrainingFeedbackEvent,
    *,
    reserved_paper_ids: set[str],
) -> str | None:
    review = session.get(HumanReview, event.review_id)
    if review is None or review.paper_id != event.paper_id:
        return "review missing or reassigned"
    normalized = normalize_classification_label(review.human_label)
    if normalized is None:
        return "review label missing or unsupported"
    if review.review_status not in {None, "COMPLETED"}:
        return f"review status changed to {review.review_status}"
    if normalized != event.human_label:
        return f"feedback superseded by label {normalized}"
    if event.paper_id in reserved_paper_ids:
        return "paper moved into a reserved evaluation dataset"
    return None


def _invalid_trigger_reasons(
    session: Session,
    run: ModelTrainingRun,
) -> dict[str, str]:
    reserved_paper_ids = _reserved_evaluation_ids()
    events = session.execute(
        select(TrainingFeedbackEvent).where(
            TrainingFeedbackEvent.id.in_(run.trigger_event_ids)
        )
    ).scalars()
    reasons: dict[str, str] = {}
    for event in events:
        reason = (
            event.retirement_reason or "feedback event was retired"
            if event.retired_at is not None
            else _feedback_ineligibility_reason(
            session,
            event,
            reserved_paper_ids=reserved_paper_ids,
        )
        )
        if reason is not None:
            reasons[event.paper_id] = reason
    return reasons


def pending_review_count(session: Session) -> int:
    events = session.execute(
        select(TrainingFeedbackEvent).where(
            TrainingFeedbackEvent.consumed_by_run_id.is_(None),
            TrainingFeedbackEvent.retired_at.is_(None),
        )
    ).scalars()
    reserved_paper_ids = _reserved_evaluation_ids()
    return len(
        {
            event.paper_id
            for event in events
            if _feedback_ineligibility_reason(
                session,
                event,
                reserved_paper_ids=reserved_paper_ids,
            )
            is None
        }
    )


def maybe_run_model_evolution(session: Session) -> ModelTrainingRun | None:
    """Claim one complete review batch and execute a full retraining attempt."""
    run = _claim_training_batch(session)
    if run is None:
        return None
    try:
        return _execute_training_run(session, run.id)
    except Exception as exc:
        _mark_run_failed(session, run.id, exc)
        return session.get(ModelTrainingRun, run.id)


def run_pending_model_evolution(session: Session) -> list[ModelTrainingRun]:
    """Drain every complete batch, stopping when a failed batch needs retry."""
    completed: list[ModelTrainingRun] = []
    while True:
        run = maybe_run_model_evolution(session)
        if run is None:
            return completed
        completed.append(run)
        if run.status == "FAILED":
            return completed


def _training_state(
    session: Session,
    *,
    for_update: bool = False,
) -> ModelTrainingState:
    _ensure_training_state_row(session)
    query = select(ModelTrainingState).where(ModelTrainingState.id == _STATE_ID)
    if for_update:
        query = query.with_for_update()
    return session.execute(query).scalar_one()


def _ensure_training_state_row(session: Session) -> None:
    """Create the singleton state row with a dialect-safe upsert."""
    values = {
        "id": _STATE_ID,
        "batch_size": retrain_batch_size(),
        "lease_generation": 0,
        "updated_at": datetime.now(UTC),
    }
    dialect = session.get_bind().dialect.name
    if dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert

        statement = insert(ModelTrainingState).values(**values)
        statement = statement.on_conflict_do_nothing(index_elements=["id"])
    elif dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert

        statement = insert(ModelTrainingState).values(**values)
        statement = statement.on_conflict_do_nothing(index_elements=["id"])
    else:
        if session.get(ModelTrainingState, _STATE_ID) is not None:
            return
        session.add(ModelTrainingState(**values))
        session.flush()
        return
    session.execute(statement)


def _claim_training_batch(session: Session) -> ModelTrainingRun | None:
    state = _training_state(session, for_update=True)
    state.batch_size = retrain_batch_size()
    if state.active_run_id:
        active = session.get(ModelTrainingRun, state.active_run_id)
        if active is not None and active.status == "RUNNING":
            if not _run_is_stale(active):
                session.commit()
                return None
            active.status = "FAILED"
            active.finished_at = datetime.now(UTC)
            active.error_message = "stale training run recovered by the next review"
            _release_feedback_events(session, active.id)
            session.flush()
        state.active_run_id = None
        session.flush()

    pending = list(
        session.execute(
            select(TrainingFeedbackEvent)
            .where(
                TrainingFeedbackEvent.consumed_by_run_id.is_(None),
                TrainingFeedbackEvent.retired_at.is_(None),
            )
            .order_by(
                TrainingFeedbackEvent.created_at.asc(),
                TrainingFeedbackEvent.id.asc(),
            )
            .with_for_update()
        ).scalars()
    )
    reserved_paper_ids = _reserved_evaluation_ids()
    now = datetime.now(UTC)
    eligible_pending: list[TrainingFeedbackEvent] = []
    for event in pending:
        reason = _feedback_ineligibility_reason(
            session,
            event,
            reserved_paper_ids=reserved_paper_ids,
        )
        if reason is None:
            eligible_pending.append(event)
        else:
            event.retired_at = now
            event.retirement_reason = reason
    pending = eligible_pending
    ordered_paper_ids: list[str] = []
    seen_paper_ids: set[str] = set()
    for event in pending:
        if event.paper_id not in seen_paper_ids:
            ordered_paper_ids.append(event.paper_id)
            seen_paper_ids.add(event.paper_id)
    if len(ordered_paper_ids) < state.batch_size:
        session.commit()
        return None

    trigger_paper_ids = ordered_paper_ids[: state.batch_size]
    trigger_paper_id_set = set(trigger_paper_ids)
    selected_events = [
        event for event in pending if event.paper_id in trigger_paper_id_set
    ]
    observed_generation = state.lease_generation
    lease_generation = observed_generation + 1
    run = ModelTrainingRun(
        id=f"train_{uuid.uuid4().hex}",
        status="RUNNING",
        trigger_review_count=len(trigger_paper_ids),
        trigger_event_ids=[event.id for event in selected_events],
        trigger_paper_ids=trigger_paper_ids,
        backend=os.environ.get("PAS_LEARNED_BACKEND", "sklearn").lower(),
        lease_generation=lease_generation,
        heartbeat_at=now,
    )
    session.add(run)
    session.flush()
    claim = session.execute(
        update(ModelTrainingState)
        .where(
            ModelTrainingState.id == _STATE_ID,
            ModelTrainingState.active_run_id.is_(None),
            ModelTrainingState.lease_generation == observed_generation,
        )
        .values(
            active_run_id=run.id,
            lease_generation=lease_generation,
            batch_size=retrain_batch_size(),
            updated_at=now,
        )
    )
    if claim.rowcount != 1:
        session.rollback()
        return None
    for event in selected_events:
        event.consumed_by_run_id = run.id
    session.commit()
    session.refresh(run)
    return run


def _run_is_stale(run: ModelTrainingRun) -> bool:
    cutoff = datetime.now(UTC) - timedelta(
        seconds=max(
            60,
            _positive_int_env("PAS_MODEL_TRAINING_STALE_SECONDS", 3600),
        )
    )
    heartbeat = run.heartbeat_at or run.started_at
    if heartbeat.tzinfo is None:
        heartbeat = heartbeat.replace(tzinfo=UTC)
    return heartbeat < cutoff


def _renew_training_heartbeat_once(run_id: str, lease_generation: int) -> bool:
    """Renew a live lease using an independent transaction and fencing CAS."""
    from app.db import SessionLocal

    now = datetime.now(UTC)
    with SessionLocal() as heartbeat_session:
        renewed_run = heartbeat_session.execute(
            update(ModelTrainingRun)
            .where(
                ModelTrainingRun.id == run_id,
                ModelTrainingRun.status == "RUNNING",
                ModelTrainingRun.lease_generation == lease_generation,
            )
            .values(heartbeat_at=now)
        )
        renewed_state = heartbeat_session.execute(
            update(ModelTrainingState)
            .where(
                ModelTrainingState.id == _STATE_ID,
                ModelTrainingState.active_run_id == run_id,
                ModelTrainingState.lease_generation == lease_generation,
            )
            .values(updated_at=now)
        )
        if renewed_run.rowcount != 1 or renewed_state.rowcount != 1:
            heartbeat_session.rollback()
            return False
        heartbeat_session.commit()
        return True


@contextmanager
def _training_heartbeat(run_id: str, lease_generation: int):
    stale_seconds = max(
        60,
        _positive_int_env("PAS_MODEL_TRAINING_STALE_SECONDS", 3600),
    )
    interval = min(
        30,
        max(
            1,
            _positive_int_env(
                "PAS_MODEL_TRAINING_HEARTBEAT_SECONDS",
                stale_seconds // 3,
            ),
        ),
    )
    stop = Event()

    def renew() -> None:
        while not stop.wait(interval):
            try:
                if not _renew_training_heartbeat_once(run_id, lease_generation):
                    return
            except Exception:
                # Promotion remains fenced even if a transient renewal fails.
                continue

    thread = Thread(
        target=renew,
        name=f"model-heartbeat-{run_id}",
        daemon=True,
    )
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=5)


def _execute_training_run(
    session: Session,
    run_id: str,
) -> ModelTrainingRun:
    run = session.get(ModelTrainingRun, run_id)
    if run is None:
        raise ValueError(f"training run {run_id} not found")
    if run.status != "RUNNING":
        raise RuntimeError(f"training run {run_id} no longer owns a live lease")
    run.heartbeat_at = datetime.now(UTC)
    session.commit()
    with _training_heartbeat(run.id, run.lease_generation):
        return _execute_training_run_with_lease(session, run)


def _execute_training_run_with_lease(
    session: Session,
    run: ModelTrainingRun,
) -> ModelTrainingRun:
    from app.services.learned_classifier import (
        build_training_set,
        build_validation_set,
        load_authoritative_model,
        load_model,
        save_model,
        train_from_examples,
    )

    boundary_hashes = _label_boundary_hashes()
    run.label_boundary_hashes = boundary_hashes
    invalid_trigger_reasons = _invalid_trigger_reasons(session, run)
    if invalid_trigger_reasons:
        return _invalidate_run(
            session,
            run,
            invalid_paper_reasons=invalid_trigger_reasons,
            reason="trigger review eligibility changed before training",
            training_examples=[],
        )
    training_examples = build_training_set(session)
    labels = {example["label"] for example in training_examples}
    if len(training_examples) < 4 or len(labels) < 2:
        return _reject_run(
            session,
            run,
            "full retraining requires at least four examples across two labels",
            training_examples=training_examples,
        )
    missing_trigger_papers = set(run.trigger_paper_ids) - {
        example["paper_id"] for example in training_examples
    }
    if missing_trigger_papers:
        return _invalidate_run(
            session,
            run,
            invalid_paper_reasons={
                paper_id: "trigger review is missing from the materialized "
                "training set"
                for paper_id in missing_trigger_papers
            },
            reason="trigger reviews are missing from the materialized training set: "
            f"{sorted(missing_trigger_papers)}",
            training_examples=training_examples,
        )

    validation_examples = build_validation_set(session)
    run.heartbeat_at = datetime.now(UTC)
    session.commit()
    candidate = train_from_examples(training_examples, backend=run.backend)
    candidate.model_version = f"learned-{run.id}"
    candidate_path = _candidate_model_path(run.id)
    save_model(candidate, candidate_path)
    production_path = _production_model_path()
    state = _training_state(session)
    if state.production_run_id:
        incumbent, incumbent_hash = load_authoritative_model(session)
    else:
        incumbent = load_model(production_path)
        incumbent_hash = (
            _sha256_file(production_path) if production_path.exists() else None
        )
    run.heartbeat_at = datetime.now(UTC)
    session.commit()
    decision = evaluate_candidate_for_promotion(
        training_examples=training_examples,
        trigger_paper_ids=list(run.trigger_paper_ids),
        candidate=candidate,
        incumbent=incumbent,
        validation_examples=validation_examples,
        backend=run.backend,
    )
    if _label_boundary_hashes() != boundary_hashes:
        raise RuntimeError("label dataset boundary changed during model training")

    run.training_example_count = len(training_examples)
    run.validation_example_count = len(validation_examples)
    run.training_dataset_hash = _examples_hash(training_examples)
    run.validation_dataset_hash = (
        _examples_hash(validation_examples) if validation_examples else None
    )
    run.evaluation_scope = decision.evaluation_scope
    run.candidate_metrics = decision.candidate_metrics
    run.incumbent_metrics = decision.incumbent_metrics
    run.validation_candidate_metrics = decision.validation_candidate_metrics
    run.validation_incumbent_metrics = decision.validation_incumbent_metrics
    run.candidate_model_path = str(candidate_path)
    run.production_model_path = str(production_path)
    run.candidate_model_sha256 = _sha256_file(candidate_path)
    run.model_artifact = candidate_path.read_bytes()
    run.incumbent_model_sha256 = incumbent_hash
    run.model_version = candidate.model_version
    run.promotion_reason = decision.reason
    run.promotion_gate_config = _promotion_gate_config(
        run.backend,
        training_examples,
    )
    run.runtime_versions = _runtime_versions(run.backend)
    run.finished_at = datetime.now(UTC)
    run.heartbeat_at = run.finished_at

    promotion_accepted = decision.accepted and auto_promotion_enabled()
    if decision.accepted and not promotion_accepted:
        run.promotion_reason = (
            f"{decision.reason}; automatic production promotion is disabled, "
            "candidate retained for shadow evaluation"
        )

    if promotion_accepted:
        run.status = "PROMOTED"
        run.promoted_at = datetime.now(UTC)
        run.cache_sync_status = "PENDING"
    elif decision.accepted:
        run.status = "STAGED"
        run.cache_sync_status = "NOT_APPLICABLE"
    else:
        run.status = "REJECTED"
        run.cache_sync_status = "NOT_APPLICABLE"
    _finalize_training_lease(session, run, promoted=promotion_accepted)
    session.commit()
    if promotion_accepted:
        _refresh_production_cache_after_commit(session, run.id, production_path)
    session.refresh(run)
    return run


def _reject_run(
    session: Session,
    run: ModelTrainingRun,
    reason: str,
    *,
    training_examples: list[dict],
) -> ModelTrainingRun:
    run.status = "REJECTED"
    run.promotion_reason = reason
    run.training_example_count = len(training_examples)
    run.training_dataset_hash = (
        _examples_hash(training_examples) if training_examples else None
    )
    run.finished_at = datetime.now(UTC)
    run.cache_sync_status = "NOT_APPLICABLE"
    run.promotion_gate_config = _promotion_gate_config(
        run.backend,
        training_examples,
    )
    run.runtime_versions = _runtime_versions(run.backend)
    _finalize_training_lease(session, run, promoted=False)
    session.commit()
    session.refresh(run)
    return run


def _invalidate_run(
    session: Session,
    run: ModelTrainingRun,
    *,
    invalid_paper_reasons: dict[str, str],
    reason: str,
    training_examples: list[dict],
) -> ModelTrainingRun:
    """Retire invalid triggers and release every still-valid peer."""
    now = datetime.now(UTC)
    events = list(
        session.execute(
            select(TrainingFeedbackEvent).where(
                TrainingFeedbackEvent.consumed_by_run_id == run.id
            )
        ).scalars()
    )
    for event in events:
        if event.paper_id in invalid_paper_reasons:
            event.retired_at = now
            event.retirement_reason = invalid_paper_reasons[event.paper_id]
        else:
            event.consumed_by_run_id = None
    run.status = "INVALIDATED"
    invalidation_detail = "; ".join(
        f"{paper_id}: {invalid_paper_reasons[paper_id]}"
        for paper_id in sorted(invalid_paper_reasons)
    )
    run.promotion_reason = f"{reason}: {invalidation_detail}"
    run.training_example_count = len(training_examples)
    run.training_dataset_hash = (
        _examples_hash(training_examples) if training_examples else None
    )
    run.finished_at = now
    run.heartbeat_at = now
    run.cache_sync_status = "NOT_APPLICABLE"
    run.promotion_gate_config = _promotion_gate_config(
        run.backend,
        training_examples,
    )
    run.runtime_versions = _runtime_versions(run.backend)
    _finalize_training_lease(session, run, promoted=False)
    session.commit()
    session.refresh(run)
    return run


def evaluate_candidate_for_promotion(
    *,
    training_examples: list[dict],
    trigger_paper_ids: list[str],
    candidate,
    incumbent,
    validation_examples: list[dict],
    backend: str,
) -> PromotionDecision:
    """Compare incumbent and candidate on leakage-safe, identical cohorts."""
    from sklearn.model_selection import KFold

    trigger_examples = [
        example
        for example in training_examples
        if example["paper_id"] in set(trigger_paper_ids)
    ]
    if len(trigger_examples) < 4:
        return PromotionDecision(
            accepted=False,
            reason="fewer than four trigger papers have evaluable features",
            evaluation_scope="trigger_batch_oof",
            candidate_metrics={},
            incumbent_metrics={},
            validation_candidate_metrics=None,
            validation_incumbent_metrics=None,
        )

    incumbent_predictions = {
        example["paper_id"]: _hybrid_prediction(incumbent, example)
        for example in trigger_examples
    }
    gold = {
        example["paper_id"]: example["label"] for example in trigger_examples
    }
    candidate_predictions: dict[str, str] = {}
    split_count = min(_OOF_MAX_SPLITS, len(trigger_examples))
    splitter = KFold(
        n_splits=split_count,
        shuffle=True,
        random_state=_OOF_RANDOM_STATE,
    )
    for _, evaluation_indices in splitter.split(trigger_examples):
        evaluation_ids = {
            trigger_examples[index]["paper_id"] for index in evaluation_indices
        }
        fold_training = [
            example
            for example in training_examples
            if example["paper_id"] not in evaluation_ids
        ]
        if len({example["label"] for example in fold_training}) < 2:
            return PromotionDecision(
                accepted=False,
                reason="an out-of-fold training split contains fewer than two labels",
                evaluation_scope="trigger_batch_oof",
                candidate_metrics={},
                incumbent_metrics=_classification_metrics(
                    incumbent_predictions,
                    gold,
                ),
                validation_candidate_metrics=None,
                validation_incumbent_metrics=None,
            )
        from app.services.learned_classifier import train_from_examples

        fold_candidate = train_from_examples(fold_training, backend=backend)
        for example in trigger_examples:
            if example["paper_id"] in evaluation_ids:
                candidate_predictions[example["paper_id"]] = _hybrid_prediction(
                    fold_candidate,
                    example,
                )

    candidate_metrics = _classification_metrics(candidate_predictions, gold)
    incumbent_metrics = _classification_metrics(incumbent_predictions, gold)
    batch_non_regression = _non_regressing(
        candidate_metrics,
        incumbent_metrics,
    )
    batch_improved = _strictly_improved(
        candidate_metrics,
        incumbent_metrics,
    )

    validation_candidate_metrics = None
    validation_incumbent_metrics = None
    validation_non_regression = True
    validation_improved = False
    evaluation_scope = "trigger_batch_oof"
    validation_gate = validation_readiness(validation_examples)
    if validation_examples:
        validation_gold = {
            example["paper_id"]: example["label"]
            for example in validation_examples
        }
        validation_candidate_metrics = _classification_metrics(
            {
                example["paper_id"]: _hybrid_prediction(candidate, example)
                for example in validation_examples
            },
            validation_gold,
        )
        validation_incumbent_metrics = _classification_metrics(
            {
                example["paper_id"]: _hybrid_prediction(incumbent, example)
                for example in validation_examples
            },
            validation_gold,
        )
        validation_non_regression = _non_regressing(
            validation_candidate_metrics,
            validation_incumbent_metrics,
        )
        validation_improved = _strictly_improved(
            validation_candidate_metrics,
            validation_incumbent_metrics,
        )
        evaluation_scope += "+dedicated_validation"
    else:
        evaluation_scope += "+validation_required"

    accepted = (
        validation_gate["ready"]
        and
        batch_non_regression
        and validation_non_regression
        and (batch_improved or validation_improved)
    )
    if not validation_gate["ready"]:
        reason = validation_gate["reason"] + "; candidate retained for audit"
    elif not batch_non_regression:
        reason = "candidate regressed on the trigger-batch out-of-fold gate"
    elif not validation_non_regression:
        reason = "candidate regressed on the dedicated validation gate"
    elif not (batch_improved or validation_improved):
        reason = "candidate did not strictly improve any protected metric"
    else:
        reason = (
            "candidate improved a protected metric with no accuracy, macro-F1, "
            "or per-label recall regression"
        )
    return PromotionDecision(
        accepted=accepted,
        reason=reason,
        evaluation_scope=evaluation_scope,
        candidate_metrics=candidate_metrics,
        incumbent_metrics=incumbent_metrics,
        validation_candidate_metrics=validation_candidate_metrics,
        validation_incumbent_metrics=validation_incumbent_metrics,
    )


def _hybrid_prediction(model, example: dict) -> str:
    base_label = example["base_label"]
    if model is None:
        return base_label
    predicted_label, predicted_confidence = model.predict(example)
    if (
        predicted_label != base_label
        and predicted_confidence >= _HYBRID_MIN_CONFIDENCE
        and predicted_confidence - float(example["base_confidence"])
        >= _HYBRID_MIN_MARGIN
    ):
        return predicted_label
    return base_label


def _classification_metrics(
    predictions: dict[str, str],
    gold: dict[str, str],
) -> dict:
    from app.services.eval_service import compute_metrics

    report = compute_metrics(predictions, gold)
    return {
        "n_evaluated": report.n_evaluated,
        "accuracy": report.accuracy,
        "macro_precision": report.macro_precision,
        "macro_recall": report.macro_recall,
        "macro_f1": report.macro_f1,
        "per_label": {
            metric.label: {
                "precision": metric.precision,
                "recall": metric.recall,
                "f1": metric.f1,
                "support": metric.support,
            }
            for metric in report.per_label
        },
        "confusion": report.confusion,
    }


def _non_regressing(candidate: dict, incumbent: dict) -> bool:
    for metric in ("accuracy", "macro_f1"):
        candidate_value = float(candidate.get(metric, 0.0))
        incumbent_value = float(incumbent.get(metric, 0.0))
        if (
            not math.isfinite(candidate_value)
            or not math.isfinite(incumbent_value)
            or candidate_value < incumbent_value
        ):
            return False
    candidate_labels = candidate.get("per_label", {})
    for label, incumbent_metric in incumbent.get("per_label", {}).items():
        if int(incumbent_metric.get("support", 0)) == 0:
            continue
        candidate_recall = float(
            candidate_labels.get(label, {}).get("recall", 0.0)
        )
        incumbent_recall = float(incumbent_metric["recall"])
        if (
            not math.isfinite(candidate_recall)
            or not math.isfinite(incumbent_recall)
            or candidate_recall < incumbent_recall
        ):
            return False
    return True


def _strictly_improved(candidate: dict, incumbent: dict) -> bool:
    delta = _nonnegative_float_env(
        "PAS_MODEL_PROMOTION_MIN_DELTA",
        0.0,
    )
    epsilon = 1e-12
    return any(
        float(candidate.get(metric, 0.0))
        > float(incumbent.get(metric, 0.0)) + delta + epsilon
        for metric in ("macro_f1", "accuracy")
    )


def _examples_hash(examples: list[dict]) -> str:
    normalized = [
        {
            key: value
            for key, value in sorted(example.items())
            if key != "notes"
        }
        for example in sorted(examples, key=lambda item: item["paper_id"])
    ]
    payload = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _production_model_path() -> Path:
    from app.services.learned_classifier import _model_path

    return _model_path()


def _candidate_model_path(run_id: str) -> Path:
    production_path = _production_model_path()
    registry = Path(
        os.environ.get(
            "PAS_MODEL_REGISTRY_DIR",
            str(production_path.parent / "model_registry"),
        )
    )
    path = registry / run_id / "model.joblib"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _finalize_training_lease(
    session: Session,
    run: ModelTrainingRun,
    *,
    promoted: bool,
) -> None:
    values: dict = {
        "active_run_id": None,
        "updated_at": datetime.now(UTC),
    }
    if promoted:
        values.update(
            production_run_id=run.id,
            current_model_version=run.model_version,
        )
    fenced = session.execute(
        update(ModelTrainingState)
        .where(
            ModelTrainingState.id == _STATE_ID,
            ModelTrainingState.active_run_id == run.id,
            ModelTrainingState.lease_generation == run.lease_generation,
        )
        .values(**values)
    )
    if fenced.rowcount != 1:
        raise RuntimeError("training lease was lost before promotion")


def _refresh_production_cache_after_commit(
    session: Session,
    run_id: str,
    production_path: Path,
) -> None:
    """Best-effort cache refresh after the DB authority is committed."""
    temporary = production_path.with_name(
        f".{production_path.name}.{run_id}.tmp"
    )
    try:
        run = session.get(ModelTrainingRun, run_id)
        if (
            run is None
            or run.status != "PROMOTED"
            or not run.model_artifact
            or not run.candidate_model_sha256
        ):
            raise RuntimeError("promoted database artifact is incomplete")
        production_path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_bytes(run.model_artifact)
        if _sha256_file(temporary) != run.candidate_model_sha256:
            raise RuntimeError("production cache hash verification failed")
        os.replace(temporary, production_path)
        run.cache_sync_status = "SYNCED"
        session.commit()
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        session.rollback()
        run = session.get(ModelTrainingRun, run_id)
        if run is None or run.status != "PROMOTED":
            return
        run.cache_sync_status = "FAILED"
        run.error_message = f"cache refresh failed: {type(exc).__name__}: {exc}"
        try:
            session.commit()
        except Exception:
            session.rollback()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _label_boundary_hashes() -> dict[str, str]:
    return {
        "training": _sha256_file(settings.training_labels_csv),
        "validation": _sha256_file(settings.validation_labels_csv),
        "frozen_holdout": _sha256_file(settings.eval_labels_csv),
    }


def _positive_int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


def _nonnegative_int_env(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


def _nonnegative_float_env(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
        return max(0.0, value) if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def _promotion_gate_config(
    backend: str | None = None,
    training_examples: list[dict] | None = None,
) -> dict:
    from app.services.learned_classifier import training_configuration

    resolved_backend = backend or os.environ.get(
        "PAS_LEARNED_BACKEND",
        "sklearn",
    ).lower()
    return {
        "protected_metrics": [
            "accuracy",
            "macro_f1",
            "supported_per_label_recall",
        ],
        "regression_tolerance": 0.0,
        "minimum_improvement_delta": _nonnegative_float_env(
            "PAS_MODEL_PROMOTION_MIN_DELTA",
            0.0,
        ),
        "minimum_validation_examples": minimum_validation_examples(),
        "minimum_validation_labels": minimum_validation_labels(),
        "comparison": "candidate must not regress any protected metric",
        "out_of_fold": {
            "strategy": "KFold",
            "maximum_splits": _OOF_MAX_SPLITS,
            "shuffle": True,
            "random_state": _OOF_RANDOM_STATE,
        },
        "hybrid_override": {
            "minimum_confidence": _HYBRID_MIN_CONFIDENCE,
            "minimum_margin_over_rules": _HYBRID_MIN_MARGIN,
        },
        "training": training_configuration(
            resolved_backend,
            training_examples,
        ),
    }


def _runtime_versions(backend: str) -> dict:
    packages = ["numpy", "scikit-learn", "joblib"]
    if backend == "lightgbm":
        packages.append("lightgbm")
    resolved: dict[str, str] = {}
    for package in packages:
        try:
            resolved[package] = version(package)
        except PackageNotFoundError:
            resolved[package] = "not-installed"
    return {
        "python": platform.python_version(),
        "backend": backend,
        "build_revision": next(
            (
                os.environ[name]
                for name in ("PAS_BUILD_REVISION", "GIT_COMMIT", "SOURCE_VERSION")
                if os.environ.get(name)
            ),
            "unavailable",
        ),
        "packages": resolved,
    }


def _release_feedback_events(session: Session, run_id: str) -> None:
    events = session.execute(
        select(TrainingFeedbackEvent).where(
            TrainingFeedbackEvent.consumed_by_run_id == run_id,
            TrainingFeedbackEvent.retired_at.is_(None),
        )
    ).scalars()
    for event in events:
        event.consumed_by_run_id = None


def _mark_run_failed(
    session: Session,
    run_id: str,
    error: Exception,
) -> None:
    session.rollback()
    run = session.get(ModelTrainingRun, run_id)
    if run is None:
        return
    if run.status == "PROMOTED":
        return
    run.status = "FAILED"
    run.finished_at = datetime.now(UTC)
    run.error_message = f"{type(error).__name__}: {error}"
    _release_feedback_events(session, run_id)
    session.execute(
        update(ModelTrainingState)
        .where(
            ModelTrainingState.id == _STATE_ID,
            ModelTrainingState.active_run_id == run_id,
            ModelTrainingState.lease_generation == run.lease_generation,
        )
        .values(active_run_id=None, updated_at=datetime.now(UTC))
    )
    session.commit()


def training_run_to_dict(run: ModelTrainingRun | None) -> dict | None:
    if run is None:
        return None
    return {
        "run_id": run.id,
        "status": run.status,
        "trigger_review_count": run.trigger_review_count,
        "trigger_event_ids": run.trigger_event_ids,
        "trigger_paper_ids": run.trigger_paper_ids,
        "lease_generation": run.lease_generation,
        "training_example_count": run.training_example_count,
        "validation_example_count": run.validation_example_count,
        "backend": run.backend,
        "model_version": run.model_version,
        "evaluation_scope": run.evaluation_scope,
        "candidate_metrics": run.candidate_metrics,
        "incumbent_metrics": run.incumbent_metrics,
        "validation_candidate_metrics": run.validation_candidate_metrics,
        "validation_incumbent_metrics": run.validation_incumbent_metrics,
        "promotion_reason": run.promotion_reason,
        "promotion_gate_config": run.promotion_gate_config,
        "runtime_versions": run.runtime_versions,
        "cache_sync_status": run.cache_sync_status,
        "training_dataset_hash": run.training_dataset_hash,
        "validation_dataset_hash": run.validation_dataset_hash,
        "label_boundary_hashes": run.label_boundary_hashes,
        "candidate_model_sha256": run.candidate_model_sha256,
        "incumbent_model_sha256": run.incumbent_model_sha256,
        "error_message": run.error_message,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "promoted_at": run.promoted_at,
        "heartbeat_at": run.heartbeat_at,
    }


def _production_authority_status(
    session: Session,
    state: ModelTrainingState,
) -> dict:
    from app.services.learned_classifier import (
        load_authoritative_model,
        load_model,
    )

    cache_path = _production_model_path()
    cache_sha256: str | None = None
    cache_error: str | None = None
    if cache_path.exists():
        try:
            cache_sha256 = _sha256_file(cache_path)
        except Exception as exc:
            cache_error = f"{type(exc).__name__}: {exc}"

    result = {
        "production_run_id": state.production_run_id,
        "status": "RULES_ONLY",
        "model_version": None,
        "artifact_sha256": None,
        "cache_sync_status": None,
        "cache_present": cache_path.exists(),
        "cache_sha256": cache_sha256,
        "cache_matches_authority": None,
        "error": cache_error,
    }
    if not state.production_run_id:
        try:
            legacy = load_model(cache_path)
            if legacy is not None:
                result.update(
                    status="LEGACY_CACHE",
                    model_version=legacy.model_version or "learned-v0.7",
                    artifact_sha256=cache_sha256,
                    cache_matches_authority=True,
                )
        except Exception as exc:
            result["error"] = f"legacy cache verification failed: {exc}"
        return result

    run = session.get(ModelTrainingRun, state.production_run_id)
    if run is not None:
        result["artifact_sha256"] = run.candidate_model_sha256
        result["cache_sync_status"] = run.cache_sync_status
    try:
        model, artifact_sha256 = load_authoritative_model(session)
        result.update(
            status="VERIFIED",
            model_version=model.model_version,
            artifact_sha256=artifact_sha256,
            cache_matches_authority=(
                cache_sha256 == artifact_sha256 if cache_sha256 else False
            ),
            error=cache_error,
        )
    except Exception as exc:
        result.update(
            status="UNHEALTHY",
            model_version=None,
            cache_matches_authority=False,
            error=f"{type(exc).__name__}: {exc}",
        )
    return result


def model_evolution_status(session: Session) -> dict:
    state = _training_state(session)
    pending = pending_review_count(session)
    latest = session.execute(
        select(ModelTrainingRun)
        .order_by(ModelTrainingRun.started_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    active = (
        session.get(ModelTrainingRun, state.active_run_id)
        if state.active_run_id
        else None
    )
    batch_size = retrain_batch_size()
    production_authority = _production_authority_status(session, state)
    from app.services.learned_classifier import build_validation_set

    validation_gate = validation_readiness(build_validation_set(session))
    return {
        "batch_size": batch_size,
        "pending_reviews": pending,
        "reviews_until_retrain": max(0, batch_size - pending),
        "progress": min(1.0, pending / batch_size),
        "current_model_version": production_authority["model_version"],
        "production_authority": production_authority,
        "validation_gate": validation_gate,
        "active_run": training_run_to_dict(active),
        "latest_run": training_run_to_dict(latest),
    }
