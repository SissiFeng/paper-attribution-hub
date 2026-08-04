"""End-to-end calibration comparison for the v0.7 rules and AET scorer.

This test runs the full classification pipeline on the seeded corpus and
the bundled `eval_labels.csv`, then asserts:

  * Rules-only baseline is held fixed with no CORE false positives.
  * AET-assisted rules improve that same calibration cohort.

This is deliberately described as calibration, not an untouched holdout.
"""

from __future__ import annotations

import os

import pytest

from app.config import settings
from app.services.eval_service import run_evaluation
from app.services.relevance_classifier import classify_with_fulltext


def _eval(session, *, use_attribution_evidence: bool = False) -> dict:
    classify_with_fulltext(session, use_attribution_evidence=use_attribution_evidence)
    report = run_evaluation(session, settings.eval_labels_csv)
    return {
        "accuracy": report.accuracy,
        "macro_f1": report.macro_f1,
        "confusion": report.confusion,
    }


def test_rules_only_baseline_has_no_core_false_positives(fulltext_seeded_session):
    """Keep the pre-AET baseline explicit for the assisted comparison."""
    out = _eval(fulltext_seeded_session)
    # CORE column shouldn't have any predictions for non-CORE rows.
    confusion = out["confusion"]
    core_fp = sum(
        confusion.get(gold, {}).get("CORE_RELEVANT", 0)
        for gold in confusion
        if gold != "CORE_RELEVANT"
    )
    assert core_fp == 0, f"CORE false positives: {core_fp} ({confusion})"
    assert out["accuracy"] == pytest.approx(0.818), out


def test_aet_assisted_rules_improve_calibration_without_core_false_positives(
    fulltext_seeded_session,
):
    from sqlalchemy import select

    from app.models import PaperClassification

    baseline = _eval(fulltext_seeded_session, use_attribution_evidence=False)
    assisted = _eval(fulltext_seeded_session, use_attribution_evidence=True)

    core_false_positives = sum(
        assisted["confusion"].get(gold, {}).get("CORE_RELEVANT", 0)
        for gold in assisted["confusion"]
        if gold != "CORE_RELEVANT"
    )
    assert assisted["accuracy"] > baseline["accuracy"]
    assert assisted["accuracy"] >= 0.9
    assert core_false_positives == 0, assisted

    classifications = fulltext_seeded_session.execute(
        select(PaperClassification)
    ).scalars()
    aet_summaries = [
        item
        for classification in classifications
        for item in classification.evidence_summary or []
        if item.get("type") == "attribution_evidence_decision"
    ]
    assert aet_summaries
    assert all(summary["version"] == "aet-score-v0.1" for summary in aet_summaries)
    assert all(summary["generation_id"] for summary in aet_summaries)
    assert all(
        path["path_id"].startswith(f"aet-path:{summary['generation_id']}:")
        for summary in aet_summaries
        for path in summary["paths"]
    )


@pytest.mark.skipif(
    "PAS_RUN_LEARNED_E2E" not in os.environ,
    reason="Set PAS_RUN_LEARNED_E2E=1 to exercise the learned + judge path",
)
def test_learned_plus_judge_hits_high_accuracy(
    fulltext_seeded_session, tmp_path, monkeypatch
):
    """With the learned classifier trained on eval_labels + LLM judge active,
    we expect near-perfect accuracy on the small gold set."""
    from app.services.learned_classifier import (
        build_training_set,
        save_model,
        train_from_examples,
    )
    from app.services.relevance_classifier import classify_all

    classify_with_fulltext(fulltext_seeded_session)
    examples = build_training_set(fulltext_seeded_session)
    if len(examples) < 6:
        pytest.skip("Independent training labels are required for learned E2E")

    model_path = tmp_path / "model.joblib"
    monkeypatch.setenv("PAS_LEARNED_MODEL_PATH", str(model_path))
    save_model(train_from_examples(examples, backend="sklearn"), model_path)

    classify_all(fulltext_seeded_session, use_learned=True, use_judge=True)
    report = run_evaluation(fulltext_seeded_session, settings.eval_labels_csv)
    assert report.accuracy >= 0.95, report
