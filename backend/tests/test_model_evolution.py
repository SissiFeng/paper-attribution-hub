from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import (
    HumanReview,
    ModelTrainingRun,
    ModelTrainingState,
    Paper,
    TrainingFeedbackEvent,
)
from app.services.model_evolution import (
    PromotionDecision,
    _claim_training_batch,
    _non_regressing,
    _promotion_gate_config,
    _renew_training_heartbeat_once,
    _runtime_versions,
    _run_is_stale,
    _strictly_improved,
    evaluate_candidate_for_promotion,
    maybe_run_model_evolution,
    minimum_validation_examples,
    minimum_validation_labels,
    pending_review_count,
    reconcile_training_feedback,
    record_training_feedback,
    run_pending_model_evolution,
    validation_readiness,
)
from app.services.relevance_classifier import classify_all


def _configure_learning_paths(tmp_path, monkeypatch) -> None:
    from app.config import settings

    header = "paper_id,gold_label,gold_topics,notes\n"
    training = tmp_path / "training_labels.csv"
    validation = tmp_path / "validation_labels.csv"
    holdout = tmp_path / "eval_labels.csv"
    for path in (training, validation, holdout):
        path.write_text(header, encoding="utf-8")
    monkeypatch.setattr(settings, "training_labels_csv", training)
    monkeypatch.setattr(settings, "validation_labels_csv", validation)
    monkeypatch.setattr(settings, "eval_labels_csv", holdout)


def _add_feedback(
    session,
    paper_id: str,
    label: str,
) -> TrainingFeedbackEvent | None:
    review = HumanReview(
        id=f"rev_{uuid.uuid4().hex[:10]}",
        paper_id=paper_id,
        human_label=label,
        reviewer="test-reviewer",
    )
    session.add(review)
    session.commit()
    paper = session.get(Paper, paper_id)
    return record_training_feedback(
        session,
        paper_id=paper_id,
        review_id=review.id,
        human_label=label,
        reviewer=review.reviewer,
        incumbent_label=paper.classification.label,
        incumbent_confidence=paper.classification.confidence,
    )


def _accepted_decision() -> PromotionDecision:
    return PromotionDecision(
        accepted=True,
        reason="candidate improves the trigger-batch out-of-fold gate",
        evaluation_scope="trigger_batch_oof",
        candidate_metrics={"accuracy": 0.75, "macro_f1": 0.72},
        incumbent_metrics={"accuracy": 0.50, "macro_f1": 0.48},
        validation_candidate_metrics=None,
        validation_incumbent_metrics=None,
    )


def _rejected_decision() -> PromotionDecision:
    return PromotionDecision(
        accepted=False,
        reason="candidate regressed on macro F1",
        evaluation_scope="trigger_batch_oof",
        candidate_metrics={"accuracy": 0.50, "macro_f1": 0.42},
        incumbent_metrics={"accuracy": 0.75, "macro_f1": 0.70},
        validation_candidate_metrics=None,
        validation_incumbent_metrics=None,
    )


def test_default_retrain_batch_is_twenty(monkeypatch):
    from app.services import model_evolution

    monkeypatch.delenv("PAS_ACTIVE_RETRAIN_EVERY", raising=False)

    assert model_evolution.retrain_batch_size() == 20


def test_invalid_batch_configuration_falls_back_safely(monkeypatch):
    from app.services import model_evolution

    monkeypatch.setenv("PAS_ACTIVE_RETRAIN_EVERY", "not-an-integer")

    assert model_evolution.retrain_batch_size() == 20


def test_validation_gate_defaults_fail_closed(monkeypatch):
    monkeypatch.delenv("PAS_MODEL_MIN_VALIDATION_EXAMPLES", raising=False)
    monkeypatch.delenv("PAS_MODEL_MIN_VALIDATION_LABELS", raising=False)

    readiness = validation_readiness([])

    assert minimum_validation_examples() == 20
    assert minimum_validation_labels() == 2
    assert readiness["ready"] is False
    assert "requires at least 20 examples" in readiness["reason"]


def test_training_decision_audit_captures_replay_configuration(monkeypatch):
    monkeypatch.setenv("PAS_BUILD_REVISION", "test-build-revision")

    gate = _promotion_gate_config(
        "sklearn",
        [
            {"label": "CORE_RELEVANT"},
            {"label": "EXCLUDE"},
        ],
    )
    runtime = _runtime_versions("sklearn")

    assert gate["out_of_fold"] == {
        "strategy": "KFold",
        "maximum_splits": 5,
        "shuffle": True,
        "random_state": 42,
    }
    assert gate["hybrid_override"] == {
        "minimum_confidence": 0.75,
        "minimum_margin_over_rules": 0.15,
    }
    assert gate["training"]["feature_order"]
    assert gate["training"]["logistic_regression"]["max_iter"] == 500
    assert runtime["build_revision"] == "test-build-revision"


def test_duplicate_feedback_does_not_advance_the_batch(
    seeded_session,
    tmp_path,
    monkeypatch,
):
    classify_all(seeded_session)
    _configure_learning_paths(tmp_path, monkeypatch)
    review = HumanReview(
        id="rev_duplicate_feedback",
        paper_id="P001",
        human_label="CORE_RELEVANT",
        reviewer="test-reviewer",
    )
    seeded_session.add(review)
    seeded_session.commit()
    paper = seeded_session.get(Paper, "P001")

    first = record_training_feedback(
        seeded_session,
        paper_id=paper.id,
        review_id=review.id,
        human_label=review.human_label,
        reviewer=review.reviewer,
        incumbent_label=paper.classification.label,
        incumbent_confidence=paper.classification.confidence,
    )
    duplicate = record_training_feedback(
        seeded_session,
        paper_id=paper.id,
        review_id=review.id,
        human_label=review.human_label,
        reviewer=review.reviewer,
        incumbent_label=paper.classification.label,
        incumbent_confidence=paper.classification.confidence,
    )

    events = seeded_session.execute(select(TrainingFeedbackEvent)).scalars().all()
    assert first is not None
    assert duplicate is None
    assert len(events) == 1


def test_incomplete_review_never_enters_model_training(
    seeded_session,
    tmp_path,
    monkeypatch,
):
    classify_all(seeded_session)
    _configure_learning_paths(tmp_path, monkeypatch)
    review = HumanReview(
        id="rev_needs_fulltext",
        paper_id="P001",
        human_label="CORE_RELEVANT",
        review_status="NEEDS_FULLTEXT",
        reviewer="test-reviewer",
    )
    seeded_session.add(review)
    seeded_session.commit()
    paper = seeded_session.get(Paper, "P001")

    event = record_training_feedback(
        seeded_session,
        paper_id=paper.id,
        review_id=review.id,
        human_label=review.human_label,
        reviewer=review.reviewer,
        incumbent_label=paper.classification.label,
        incumbent_confidence=paper.classification.confidence,
    )

    assert event is None
    assert pending_review_count(seeded_session) == 0


@pytest.mark.parametrize(
    ("review_status", "eligible"),
    [
        (None, True),
        ("COMPLETED", True),
        ("PENDING", False),
        ("PARTIAL", False),
        ("NEEDS_FULLTEXT", False),
    ],
)
def test_training_materialization_enforces_review_eligibility(
    seeded_session,
    tmp_path,
    monkeypatch,
    review_status,
    eligible,
):
    from app.services.learned_classifier import build_training_set

    classify_all(seeded_session)
    _configure_learning_paths(tmp_path, monkeypatch)
    seeded_session.add(
        HumanReview(
            id=f"rev_materialize_{review_status or 'legacy'}",
            paper_id="P001",
            human_label="CORE_RELEVANT",
            review_status=review_status,
            reviewer="test-reviewer",
        )
    )
    seeded_session.commit()

    paper_ids = {
        example["paper_id"] for example in build_training_set(seeded_session)
    }

    assert ("P001" in paper_ids) is eligible


def test_reconcile_backfills_existing_review_once(
    seeded_session,
    tmp_path,
    monkeypatch,
):
    classify_all(seeded_session)
    _configure_learning_paths(tmp_path, monkeypatch)
    seeded_session.add(
        HumanReview(
            id="rev_before_feedback_events",
            paper_id="P001",
            human_label="CORE_RELEVANT",
            review_status="COMPLETED",
            reviewer="test-reviewer",
        )
    )
    seeded_session.commit()

    assert reconcile_training_feedback(seeded_session) == 1
    assert reconcile_training_feedback(seeded_session) == 0
    assert pending_review_count(seeded_session) == 1
    event = seeded_session.execute(select(TrainingFeedbackEvent)).scalar_one()
    assert event.review_id == "rev_before_feedback_events"
    assert event.human_label == "CORE_RELEVANT"


def test_reconcile_excludes_incomplete_and_reserved_reviews(
    seeded_session,
    tmp_path,
    monkeypatch,
):
    from app.config import settings

    classify_all(seeded_session)
    _configure_learning_paths(tmp_path, monkeypatch)
    settings.validation_labels_csv.write_text(
        "paper_id,gold_label,gold_topics,notes\n"
        "P003,EXCLUDE,,dedicated validation\n",
        encoding="utf-8",
    )
    seeded_session.add_all(
        [
            HumanReview(
                id="rev_reconcile_needs_fulltext",
                paper_id="P001",
                human_label="CORE_RELEVANT",
                review_status="NEEDS_FULLTEXT",
                reviewer="test-reviewer",
            ),
            HumanReview(
                id="rev_reconcile_validation",
                paper_id="P003",
                human_label="EXCLUDE",
                review_status="COMPLETED",
                reviewer="test-reviewer",
            ),
        ]
    )
    seeded_session.commit()

    assert reconcile_training_feedback(seeded_session) == 0
    assert pending_review_count(seeded_session) == 0


def test_full_retrain_promotes_only_after_exact_batch(
    seeded_session,
    tmp_path,
    monkeypatch,
):
    from app.services import model_evolution

    classify_all(seeded_session)
    _configure_learning_paths(tmp_path, monkeypatch)
    monkeypatch.setenv("PAS_ACTIVE_RETRAIN_EVERY", "4")
    monkeypatch.setenv(
        "PAS_LEARNED_MODEL_PATH",
        str(tmp_path / "learned_classifier.joblib"),
    )
    monkeypatch.setenv("PAS_MODEL_REGISTRY_DIR", str(tmp_path / "registry"))
    monkeypatch.setattr(
        model_evolution,
        "evaluate_candidate_for_promotion",
        lambda *args, **kwargs: _accepted_decision(),
    )

    labels = {
        "P001": "CORE_RELEVANT",
        "P003": "EXCLUDE",
        "P006": "CORE_RELEVANT",
        "P007": "EXCLUDE",
    }
    for index, (paper_id, label) in enumerate(labels.items(), start=1):
        _add_feedback(seeded_session, paper_id, label)
        run = maybe_run_model_evolution(seeded_session)
        if index < 4:
            assert run is None

    assert run is not None
    assert run.status == "PROMOTED"
    assert run.trigger_review_count == 4
    assert run.training_example_count == 4
    assert run.model_version
    assert (tmp_path / "learned_classifier.joblib").exists()
    assert (tmp_path / "registry" / run.id / "model.joblib").exists()
    from app.services.learned_classifier import load_default_model, load_model

    promoted = load_model(tmp_path / "learned_classifier.joblib")
    assert promoted is not None
    assert promoted.model_version == run.model_version
    from app.services.relevance_classifier import (
        _configured_model_version,
        papers_needing_classification,
    )

    assert (
        _configured_model_version(
            use_learned=True,
            session=seeded_session,
        )
        == run.model_version
    )
    assert papers_needing_classification(seeded_session)
    (tmp_path / "learned_classifier.joblib").unlink()
    restored = load_default_model(seeded_session)
    assert restored is not None
    assert restored.model_version == run.model_version

    events = seeded_session.execute(select(TrainingFeedbackEvent)).scalars().all()
    assert {event.consumed_by_run_id for event in events} == {run.id}


def test_next_gate_uses_database_incumbent_when_cache_is_missing(
    seeded_session,
    tmp_path,
    monkeypatch,
):
    from app.services import model_evolution

    classify_all(seeded_session)
    _configure_learning_paths(tmp_path, monkeypatch)
    monkeypatch.setenv("PAS_ACTIVE_RETRAIN_EVERY", "4")
    production_path = tmp_path / "learned_classifier.joblib"
    monkeypatch.setenv("PAS_LEARNED_MODEL_PATH", str(production_path))
    monkeypatch.setenv("PAS_MODEL_REGISTRY_DIR", str(tmp_path / "registry"))
    incumbents: list[str | None] = []

    def capture_incumbent(*args, **kwargs):
        incumbent = kwargs["incumbent"]
        incumbents.append(
            incumbent.model_version if incumbent is not None else None
        )
        return _accepted_decision()

    monkeypatch.setattr(
        model_evolution,
        "evaluate_candidate_for_promotion",
        capture_incumbent,
    )
    for paper_id, label in (
        ("P001", "CORE_RELEVANT"),
        ("P003", "EXCLUDE"),
        ("P006", "CORE_RELEVANT"),
        ("P007", "EXCLUDE"),
    ):
        _add_feedback(seeded_session, paper_id, label)
    first = maybe_run_model_evolution(seeded_session)
    assert first is not None and first.status == "PROMOTED"
    production_path.unlink()

    for paper_id, label in (
        ("P008", "CORE_RELEVANT"),
        ("P009", "EXCLUDE"),
        ("P010", "CORE_RELEVANT"),
        ("P011", "EXCLUDE"),
    ):
        _add_feedback(seeded_session, paper_id, label)
    second = maybe_run_model_evolution(seeded_session)

    assert second is not None and second.status == "PROMOTED"
    assert incumbents == [None, first.model_version]
    assert second.incumbent_model_sha256 == first.candidate_model_sha256


def test_corrupt_database_incumbent_fails_closed_without_cache_fallback(
    seeded_session,
    tmp_path,
    monkeypatch,
):
    from app.services import model_evolution

    classify_all(seeded_session)
    _configure_learning_paths(tmp_path, monkeypatch)
    monkeypatch.setenv("PAS_ACTIVE_RETRAIN_EVERY", "4")
    production_path = tmp_path / "learned_classifier.joblib"
    monkeypatch.setenv("PAS_LEARNED_MODEL_PATH", str(production_path))
    monkeypatch.setenv("PAS_MODEL_REGISTRY_DIR", str(tmp_path / "registry"))
    monkeypatch.setattr(
        model_evolution,
        "evaluate_candidate_for_promotion",
        lambda *args, **kwargs: _accepted_decision(),
    )
    for paper_id, label in (
        ("P001", "CORE_RELEVANT"),
        ("P003", "EXCLUDE"),
        ("P006", "CORE_RELEVANT"),
        ("P007", "EXCLUDE"),
    ):
        _add_feedback(seeded_session, paper_id, label)
    first = maybe_run_model_evolution(seeded_session)
    assert first is not None and first.status == "PROMOTED"
    healthy_status = TestClient(app).get("/model-evolution/status").json()
    assert healthy_status["production_authority"]["status"] == "VERIFIED"
    assert healthy_status["production_authority"]["production_run_id"] == first.id
    assert healthy_status["current_model_version"] == first.model_version
    first.model_artifact = b"corrupt-authoritative-model"
    seeded_session.commit()

    unhealthy_status = TestClient(app).get("/model-evolution/status").json()
    assert unhealthy_status["production_authority"]["status"] == "UNHEALTHY"
    assert "hash mismatch" in unhealthy_status["production_authority"]["error"]
    assert unhealthy_status["current_model_version"] is None

    for paper_id, label in (
        ("P008", "CORE_RELEVANT"),
        ("P009", "EXCLUDE"),
        ("P010", "CORE_RELEVANT"),
        ("P011", "EXCLUDE"),
    ):
        _add_feedback(seeded_session, paper_id, label)
    second = maybe_run_model_evolution(seeded_session)

    assert second is not None and second.status == "FAILED"
    assert "artifact hash mismatch" in second.error_message
    assert pending_review_count(seeded_session) == 4


def test_promotion_commit_failure_never_updates_local_cache(
    seeded_session,
    tmp_path,
    monkeypatch,
):
    from app.services import model_evolution

    classify_all(seeded_session)
    _configure_learning_paths(tmp_path, monkeypatch)
    monkeypatch.setenv("PAS_ACTIVE_RETRAIN_EVERY", "4")
    production_path = tmp_path / "learned_classifier.joblib"
    monkeypatch.setenv("PAS_LEARNED_MODEL_PATH", str(production_path))
    monkeypatch.setenv("PAS_MODEL_REGISTRY_DIR", str(tmp_path / "registry"))
    monkeypatch.setattr(
        model_evolution,
        "evaluate_candidate_for_promotion",
        lambda *args, **kwargs: _accepted_decision(),
    )
    for paper_id, label in (
        ("P001", "CORE_RELEVANT"),
        ("P003", "EXCLUDE"),
        ("P006", "CORE_RELEVANT"),
        ("P007", "EXCLUDE"),
    ):
        _add_feedback(seeded_session, paper_id, label)
    original_commit = seeded_session.commit
    commit_count = 0

    def fail_authoritative_commit_once():
        nonlocal commit_count
        commit_count += 1
        if commit_count == 3:
            raise RuntimeError("injected authoritative commit failure")
        return original_commit()

    monkeypatch.setattr(seeded_session, "commit", fail_authoritative_commit_once)

    run = maybe_run_model_evolution(seeded_session)

    assert run is not None and run.status == "FAILED"
    assert "injected authoritative commit failure" in run.error_message
    assert production_path.exists() is False
    state = seeded_session.get(ModelTrainingState, "learned_classifier")
    assert state.production_run_id is None


def test_cache_refresh_failure_keeps_database_promotion_authoritative(
    seeded_session,
    tmp_path,
    monkeypatch,
):
    from app.services import model_evolution
    from app.services.learned_classifier import load_default_model

    classify_all(seeded_session)
    _configure_learning_paths(tmp_path, monkeypatch)
    monkeypatch.setenv("PAS_ACTIVE_RETRAIN_EVERY", "4")
    production_path = tmp_path / "learned_classifier.joblib"
    monkeypatch.setenv("PAS_LEARNED_MODEL_PATH", str(production_path))
    monkeypatch.setenv("PAS_MODEL_REGISTRY_DIR", str(tmp_path / "registry"))
    monkeypatch.setattr(
        model_evolution,
        "evaluate_candidate_for_promotion",
        lambda *args, **kwargs: _accepted_decision(),
    )
    monkeypatch.setattr(
        model_evolution.os,
        "replace",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            OSError("injected cache failure")
        ),
    )
    for paper_id, label in (
        ("P001", "CORE_RELEVANT"),
        ("P003", "EXCLUDE"),
        ("P006", "CORE_RELEVANT"),
        ("P007", "EXCLUDE"),
    ):
        _add_feedback(seeded_session, paper_id, label)

    run = maybe_run_model_evolution(seeded_session)

    assert run is not None and run.status == "PROMOTED"
    assert run.cache_sync_status == "FAILED"
    assert production_path.exists() is False
    assert load_default_model(seeded_session).model_version == run.model_version


def test_ineligible_trigger_retires_only_it_and_rebatches_valid_peers(
    session,
    tmp_path,
    monkeypatch,
):
    from app.services import model_evolution

    _configure_learning_paths(tmp_path, monkeypatch)
    monkeypatch.setenv("PAS_ACTIVE_RETRAIN_EVERY", "20")
    monkeypatch.setenv(
        "PAS_LEARNED_MODEL_PATH",
        str(tmp_path / "learned_classifier.joblib"),
    )
    monkeypatch.setenv("PAS_MODEL_REGISTRY_DIR", str(tmp_path / "registry"))
    papers = [
        Paper(
            id=f"batch_invalidation_{index:02d}",
            title=f"Batch invalidation {index}",
            year=2025,
        )
        for index in range(20)
    ]
    session.add_all(papers)
    session.commit()
    classify_all(session)
    events = []
    for index, paper in enumerate(papers):
        event = _add_feedback(
            session,
            paper.id,
            "CORE_RELEVANT" if index % 2 == 0 else "EXCLUDE",
        )
        assert event is not None
        events.append(event)

    claimed = _claim_training_batch(session)
    assert claimed is not None
    invalid_event = events[0]
    review = session.get(HumanReview, invalid_event.review_id)
    review.review_status = "NEEDS_FULLTEXT"
    session.commit()

    invalidated = model_evolution._execute_training_run(session, claimed.id)

    assert invalidated.status == "INVALIDATED"
    assert "NEEDS_FULLTEXT" in invalidated.promotion_reason
    assert pending_review_count(session) == 19
    session.refresh(invalid_event)
    assert invalid_event.retired_at is not None
    assert "NEEDS_FULLTEXT" in invalid_event.retirement_reason
    assert all(
        event.consumed_by_run_id is None
        for event in events[1:]
    )

    review.review_status = "COMPLETED"
    session.commit()
    replacement = record_training_feedback(
        session,
        paper_id=review.paper_id,
        review_id=review.id,
        human_label=review.human_label,
        reviewer=review.reviewer,
        incumbent_label=None,
        incumbent_confidence=None,
    )
    assert replacement is not None
    assert pending_review_count(session) == 20
    monkeypatch.setattr(
        model_evolution,
        "evaluate_candidate_for_promotion",
        lambda *args, **kwargs: _accepted_decision(),
    )

    trained = maybe_run_model_evolution(session)

    assert trained is not None and trained.status == "PROMOTED"
    assert pending_review_count(session) == 0


def test_recovery_drains_every_complete_review_batch(
    seeded_session,
    tmp_path,
    monkeypatch,
):
    from app.services import model_evolution

    classify_all(seeded_session)
    _configure_learning_paths(tmp_path, monkeypatch)
    monkeypatch.setenv("PAS_ACTIVE_RETRAIN_EVERY", "2")
    monkeypatch.setenv(
        "PAS_LEARNED_MODEL_PATH",
        str(tmp_path / "learned_classifier.joblib"),
    )
    monkeypatch.setenv("PAS_MODEL_REGISTRY_DIR", str(tmp_path / "registry"))
    monkeypatch.setattr(
        model_evolution,
        "evaluate_candidate_for_promotion",
        lambda *args, **kwargs: _accepted_decision(),
    )
    for paper_id, label in (
        ("P001", "CORE_RELEVANT"),
        ("P003", "EXCLUDE"),
        ("P006", "CORE_RELEVANT"),
        ("P007", "EXCLUDE"),
    ):
        _add_feedback(seeded_session, paper_id, label)

    runs = run_pending_model_evolution(seeded_session)

    assert len(runs) == 2
    assert [run.status for run in runs] == ["PROMOTED", "PROMOTED"]
    assert [run.trigger_review_count for run in runs] == [2, 2]
    assert pending_review_count(seeded_session) == 0


def test_rejected_candidate_never_replaces_production_model(
    seeded_session,
    tmp_path,
    monkeypatch,
):
    from app.services import model_evolution

    classify_all(seeded_session)
    _configure_learning_paths(tmp_path, monkeypatch)
    monkeypatch.setenv("PAS_ACTIVE_RETRAIN_EVERY", "4")
    production_path = tmp_path / "learned_classifier.joblib"
    monkeypatch.setenv("PAS_LEARNED_MODEL_PATH", str(production_path))
    monkeypatch.setenv("PAS_MODEL_REGISTRY_DIR", str(tmp_path / "registry"))
    monkeypatch.setattr(
        model_evolution,
        "evaluate_candidate_for_promotion",
        lambda *args, **kwargs: _rejected_decision(),
    )

    for paper_id, label in (
        ("P001", "CORE_RELEVANT"),
        ("P003", "EXCLUDE"),
        ("P006", "CORE_RELEVANT"),
        ("P007", "EXCLUDE"),
    ):
        _add_feedback(seeded_session, paper_id, label)

    run = maybe_run_model_evolution(seeded_session)

    assert run is not None
    assert run.status == "REJECTED"
    assert run.promotion_reason == "candidate regressed on macro F1"
    assert production_path.exists() is False
    assert (tmp_path / "registry" / run.id / "model.joblib").exists()


def test_label_boundary_change_during_training_fails_closed(
    seeded_session,
    tmp_path,
    monkeypatch,
):
    from app.config import settings
    from app.services import model_evolution

    classify_all(seeded_session)
    _configure_learning_paths(tmp_path, monkeypatch)
    monkeypatch.setenv("PAS_ACTIVE_RETRAIN_EVERY", "4")
    production_path = tmp_path / "learned_classifier.joblib"
    monkeypatch.setenv("PAS_LEARNED_MODEL_PATH", str(production_path))
    monkeypatch.setenv("PAS_MODEL_REGISTRY_DIR", str(tmp_path / "registry"))

    def mutate_boundary(*args, **kwargs):
        settings.validation_labels_csv.write_text(
            "paper_id,gold_label,gold_topics,notes\n"
            "P011,EXCLUDE,,changed during training\n",
            encoding="utf-8",
        )
        return _accepted_decision()

    monkeypatch.setattr(
        model_evolution,
        "evaluate_candidate_for_promotion",
        mutate_boundary,
    )
    for paper_id, label in (
        ("P001", "CORE_RELEVANT"),
        ("P003", "EXCLUDE"),
        ("P006", "CORE_RELEVANT"),
        ("P007", "EXCLUDE"),
    ):
        _add_feedback(seeded_session, paper_id, label)

    run = maybe_run_model_evolution(seeded_session)

    assert run is not None
    assert run.status == "FAILED"
    assert "boundary changed" in run.error_message
    assert production_path.exists() is False
    assert pending_review_count(seeded_session) == 4


def test_active_run_prevents_a_double_batch_claim(
    seeded_session,
    tmp_path,
    monkeypatch,
):
    classify_all(seeded_session)
    _configure_learning_paths(tmp_path, monkeypatch)
    monkeypatch.setenv("PAS_ACTIVE_RETRAIN_EVERY", "4")
    for paper_id, label in (
        ("P001", "CORE_RELEVANT"),
        ("P003", "EXCLUDE"),
        ("P006", "CORE_RELEVANT"),
        ("P007", "EXCLUDE"),
    ):
        _add_feedback(seeded_session, paper_id, label)

    first = _claim_training_batch(seeded_session)
    second = _claim_training_batch(seeded_session)

    assert first is not None
    assert first.status == "RUNNING"
    assert second is None


def test_two_sqlite_sessions_claim_one_batch_with_singleton_race(
    seeded_session,
    tmp_path,
    monkeypatch,
):
    from app.db import SessionLocal

    classify_all(seeded_session)
    _configure_learning_paths(tmp_path, monkeypatch)
    monkeypatch.setenv("PAS_ACTIVE_RETRAIN_EVERY", "4")
    for paper_id, label in (
        ("P001", "CORE_RELEVANT"),
        ("P003", "EXCLUDE"),
        ("P006", "CORE_RELEVANT"),
        ("P007", "EXCLUDE"),
    ):
        _add_feedback(seeded_session, paper_id, label)
    barrier = Barrier(2)

    def claim() -> str | None:
        with SessionLocal() as session:
            barrier.wait()
            run = _claim_training_batch(session)
            return run.id if run is not None else None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: claim(), range(2)))

    claimed = [run_id for run_id in results if run_id is not None]
    assert len(claimed) == 1
    events = seeded_session.execute(select(TrainingFeedbackEvent)).scalars()
    assert {event.consumed_by_run_id for event in events} == {claimed[0]}


def test_stale_run_releases_its_feedback_for_retry(
    seeded_session,
    tmp_path,
    monkeypatch,
):
    classify_all(seeded_session)
    _configure_learning_paths(tmp_path, monkeypatch)
    monkeypatch.setenv("PAS_ACTIVE_RETRAIN_EVERY", "4")
    monkeypatch.setenv(
        "PAS_LEARNED_MODEL_PATH",
        str(tmp_path / "learned_classifier.joblib"),
    )
    monkeypatch.setenv("PAS_MODEL_REGISTRY_DIR", str(tmp_path / "registry"))
    for paper_id, label in (
        ("P001", "CORE_RELEVANT"),
        ("P003", "EXCLUDE"),
        ("P006", "CORE_RELEVANT"),
        ("P007", "EXCLUDE"),
    ):
        _add_feedback(seeded_session, paper_id, label)
    stale = _claim_training_batch(seeded_session)
    assert stale is not None
    stale.heartbeat_at = datetime.now(UTC) - timedelta(hours=2)
    seeded_session.commit()
    assert _run_is_stale(stale) is True

    retry = _claim_training_batch(seeded_session)

    assert retry is not None
    assert retry.id != stale.id
    refreshed_stale = seeded_session.get(ModelTrainingRun, stale.id)
    assert refreshed_stale.status == "FAILED"
    events = seeded_session.execute(select(TrainingFeedbackEvent)).scalars()
    assert {event.consumed_by_run_id for event in events} == {retry.id}


def test_training_heartbeat_renews_only_the_fenced_live_lease(
    seeded_session,
    tmp_path,
    monkeypatch,
):
    classify_all(seeded_session)
    _configure_learning_paths(tmp_path, monkeypatch)
    monkeypatch.setenv("PAS_ACTIVE_RETRAIN_EVERY", "4")
    for paper_id, label in (
        ("P001", "CORE_RELEVANT"),
        ("P003", "EXCLUDE"),
        ("P006", "CORE_RELEVANT"),
        ("P007", "EXCLUDE"),
    ):
        _add_feedback(seeded_session, paper_id, label)
    run = _claim_training_batch(seeded_session)
    assert run is not None
    previous = datetime.now(UTC) - timedelta(hours=1)
    run.heartbeat_at = previous
    seeded_session.commit()

    assert _renew_training_heartbeat_once(run.id, run.lease_generation) is True
    seeded_session.expire(run)
    assert run.heartbeat_at > previous.replace(tzinfo=None)
    renewed_at = run.heartbeat_at

    assert _renew_training_heartbeat_once(run.id, run.lease_generation + 1) is False
    seeded_session.expire(run)
    assert run.heartbeat_at == renewed_at


def test_stale_worker_cannot_clear_or_promote_successor_lease(
    seeded_session,
    tmp_path,
    monkeypatch,
):
    from app.services.model_evolution import _execute_training_run

    classify_all(seeded_session)
    _configure_learning_paths(tmp_path, monkeypatch)
    monkeypatch.setenv("PAS_ACTIVE_RETRAIN_EVERY", "4")
    for paper_id, label in (
        ("P001", "CORE_RELEVANT"),
        ("P003", "EXCLUDE"),
        ("P006", "CORE_RELEVANT"),
        ("P007", "EXCLUDE"),
    ):
        _add_feedback(seeded_session, paper_id, label)
    stale = _claim_training_batch(seeded_session)
    assert stale is not None
    stale.heartbeat_at = datetime.now(UTC) - timedelta(hours=2)
    seeded_session.commit()
    successor = _claim_training_batch(seeded_session)
    assert successor is not None

    with pytest.raises(RuntimeError, match="no longer owns a live lease"):
        _execute_training_run(seeded_session, stale.id)

    state = seeded_session.get(ModelTrainingState, "learned_classifier")
    assert state.active_run_id == successor.id
    assert state.lease_generation == successor.lease_generation


def test_model_evolution_status_api_reports_pending_progress(
    seeded_session,
    tmp_path,
    monkeypatch,
):
    classify_all(seeded_session)
    _configure_learning_paths(tmp_path, monkeypatch)
    monkeypatch.setenv("PAS_ACTIVE_RETRAIN_EVERY", "20")
    for paper_id, label in (
        ("P001", "CORE_RELEVANT"),
        ("P003", "EXCLUDE"),
        ("P006", "CORE_RELEVANT"),
    ):
        _add_feedback(seeded_session, paper_id, label)

    response = TestClient(app).get("/model-evolution/status")

    assert response.status_code == 200
    body = response.json()
    assert body["batch_size"] == 20
    assert body["pending_reviews"] == 3
    assert body["reviews_until_retrain"] == 17
    assert body["active_run"] is None
    assert body["latest_run"] is None
    assert body["validation_gate"]["ready"] is False
    assert body["validation_gate"]["required_examples"] == 20


def test_review_api_schedules_model_training_after_feedback_commit(
    seeded_session,
    tmp_path,
    monkeypatch,
):
    classify_all(seeded_session)
    _configure_learning_paths(tmp_path, monkeypatch)
    monkeypatch.setenv("PAS_ACTIVE_LEARNING", "1")
    calls: list[str] = []
    monkeypatch.setattr(
        "app.services.model_evolution.run_model_evolution_background",
        lambda: calls.append("ran"),
    )

    response = TestClient(app).post(
        "/reviews/P001",
        json={
            "human_label": "CORE_RELEVANT",
            "sdl_judgement": "CONFIRMED_SDL",
            "ac_relevance_judgement": "AC_RELEVANT",
            "review_status": "COMPLETED",
            "evidence_level": "ABSTRACT",
            "judgement_basis": "DUAL_REVIEW",
            "reviewer": "test-reviewer",
        },
    )

    assert response.status_code == 200
    assert calls == ["ran"]
    assert pending_review_count(seeded_session) == 1


def test_training_run_audit_keeps_candidate_and_incumbent_metrics(
    seeded_session,
    tmp_path,
    monkeypatch,
):
    from app.services import model_evolution

    classify_all(seeded_session)
    _configure_learning_paths(tmp_path, monkeypatch)
    monkeypatch.setenv("PAS_ACTIVE_RETRAIN_EVERY", "4")
    monkeypatch.setenv(
        "PAS_LEARNED_MODEL_PATH",
        str(tmp_path / "learned_classifier.joblib"),
    )
    monkeypatch.setenv("PAS_MODEL_REGISTRY_DIR", str(tmp_path / "registry"))
    monkeypatch.setattr(
        model_evolution,
        "evaluate_candidate_for_promotion",
        lambda *args, **kwargs: _accepted_decision(),
    )
    for paper_id, label in (
        ("P001", "CORE_RELEVANT"),
        ("P003", "EXCLUDE"),
        ("P006", "CORE_RELEVANT"),
        ("P007", "EXCLUDE"),
    ):
        _add_feedback(seeded_session, paper_id, label)

    maybe_run_model_evolution(seeded_session)
    run = seeded_session.execute(select(ModelTrainingRun)).scalar_one()

    assert run.evaluation_scope == "trigger_batch_oof"
    assert run.candidate_metrics["macro_f1"] == 0.72
    assert run.incumbent_metrics["macro_f1"] == 0.48
    assert run.training_dataset_hash
    assert run.candidate_model_sha256


def test_promotion_gate_rejects_per_label_recall_regression():
    incumbent = {
        "accuracy": 0.8,
        "macro_f1": 0.7,
        "per_label": {
            "CORE_RELEVANT": {"recall": 1.0, "support": 5},
            "EXCLUDE": {"recall": 0.6, "support": 5},
        },
    }
    candidate = {
        "accuracy": 0.9,
        "macro_f1": 0.8,
        "per_label": {
            "CORE_RELEVANT": {"recall": 0.8, "support": 5},
            "EXCLUDE": {"recall": 1.0, "support": 5},
        },
    }

    assert _strictly_improved(candidate, incumbent) is True
    assert _non_regressing(candidate, incumbent) is False


def test_non_regression_tolerance_cannot_be_configured_away(monkeypatch):
    monkeypatch.setenv("PAS_MODEL_PROMOTION_REGRESSION_TOLERANCE", "1")
    incumbent = {
        "accuracy": 0.8,
        "macro_f1": 0.8,
        "per_label": {"EXCLUDE": {"recall": 0.8, "support": 2}},
    }
    candidate = {
        "accuracy": 0.7,
        "macro_f1": 0.9,
        "per_label": {"EXCLUDE": {"recall": 0.8, "support": 2}},
    }

    assert _non_regressing(candidate, incumbent) is False

    candidate["accuracy"] = float("nan")
    assert _non_regressing(candidate, incumbent) is False


def test_out_of_fold_gate_promotes_measured_improvement(monkeypatch):
    class PerfectCandidate:
        def predict(self, example):
            return example["label"], 1.0

    examples = [
        {
            "paper_id": f"P{index}",
            "label": label,
            "base_label": "EXCLUDE",
            "base_confidence": 0.1,
        }
        for index, label in enumerate(
            (
                "CORE_RELEVANT",
                "CORE_RELEVANT",
                "EXCLUDE",
                "EXCLUDE",
            ),
            start=1,
        )
    ]
    monkeypatch.setattr(
        "app.services.learned_classifier.train_from_examples",
        lambda *args, **kwargs: PerfectCandidate(),
    )
    monkeypatch.setenv("PAS_MODEL_MIN_VALIDATION_EXAMPLES", "0")
    monkeypatch.setenv("PAS_MODEL_MIN_VALIDATION_LABELS", "0")

    decision = evaluate_candidate_for_promotion(
        training_examples=examples,
        trigger_paper_ids=[example["paper_id"] for example in examples],
        candidate=PerfectCandidate(),
        incumbent=None,
        validation_examples=[],
        backend="sklearn",
    )

    assert decision.accepted is True
    assert decision.candidate_metrics["accuracy"] == 1.0
    assert decision.incumbent_metrics["accuracy"] == 0.5


def test_empty_fixed_validation_blocks_an_improved_candidate(monkeypatch):
    class PerfectCandidate:
        def predict(self, example):
            return example["label"], 1.0

    examples = [
        {
            "paper_id": f"P{index}",
            "label": label,
            "base_label": "EXCLUDE",
            "base_confidence": 0.1,
        }
        for index, label in enumerate(
            ("CORE_RELEVANT", "CORE_RELEVANT", "EXCLUDE", "EXCLUDE"),
            start=1,
        )
    ]
    monkeypatch.setattr(
        "app.services.learned_classifier.train_from_examples",
        lambda *args, **kwargs: PerfectCandidate(),
    )
    monkeypatch.setenv("PAS_MODEL_MIN_VALIDATION_EXAMPLES", "20")
    monkeypatch.setenv("PAS_MODEL_MIN_VALIDATION_LABELS", "2")

    decision = evaluate_candidate_for_promotion(
        training_examples=examples,
        trigger_paper_ids=[example["paper_id"] for example in examples],
        candidate=PerfectCandidate(),
        incumbent=None,
        validation_examples=[],
        backend="sklearn",
    )

    assert decision.accepted is False
    assert "requires at least 20 examples" in decision.reason
    assert decision.candidate_metrics["accuracy"] == 1.0


def test_dedicated_validation_regression_blocks_batch_improvement(monkeypatch):
    class PerfectFoldCandidate:
        def predict(self, example):
            return example["label"], 1.0

    class RegressingFinalCandidate:
        def predict(self, example):
            return "EXCLUDE", 1.0

    examples = [
        {
            "paper_id": f"P{index}",
            "label": label,
            "base_label": "EXCLUDE",
            "base_confidence": 0.1,
        }
        for index, label in enumerate(
            (
                "CORE_RELEVANT",
                "CORE_RELEVANT",
                "EXCLUDE",
                "EXCLUDE",
            ),
            start=1,
        )
    ]
    validation = [
        {
            "paper_id": "V1",
            "label": "CORE_RELEVANT",
            "base_label": "CORE_RELEVANT",
            "base_confidence": 0.8,
        }
    ]
    monkeypatch.setattr(
        "app.services.learned_classifier.train_from_examples",
        lambda *args, **kwargs: PerfectFoldCandidate(),
    )
    monkeypatch.setenv("PAS_MODEL_MIN_VALIDATION_EXAMPLES", "1")
    monkeypatch.setenv("PAS_MODEL_MIN_VALIDATION_LABELS", "1")

    decision = evaluate_candidate_for_promotion(
        training_examples=examples,
        trigger_paper_ids=[example["paper_id"] for example in examples],
        candidate=RegressingFinalCandidate(),
        incumbent=None,
        validation_examples=validation,
        backend="sklearn",
    )

    assert decision.accepted is False
    assert "dedicated validation" in decision.reason
