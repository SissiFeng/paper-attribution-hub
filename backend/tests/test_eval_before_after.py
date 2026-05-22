"""End-to-end eval that locks in the v0.7 quality gains.

This test runs the full classification pipeline on the seeded corpus and
the bundled `eval_labels.csv`, then asserts:

  * Rules-only baseline (no rerank, no judge, no learned override) lands
    accuracy ≥ 0.85 with no CORE false positives.
  * Adding the LLM judge + learned classifier hits ≥ 0.95.

Because it relies on the live evidence pipeline + full-text fixtures, it
needs `fulltext_seeded_session`. Skip without that.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.config import settings
from app.services.eval_service import run_evaluation
from app.services.relevance_classifier import classify_with_fulltext


def _eval(session) -> dict:
    classify_with_fulltext(session)
    report = run_evaluation(session, settings.eval_labels_csv)
    return {
        "accuracy": report.accuracy,
        "macro_f1": report.macro_f1,
        "confusion": report.confusion,
    }


def test_rules_only_no_core_false_positives(fulltext_seeded_session):
    """v0.7 rules alone must not place a non-CORE paper into CORE."""
    out = _eval(fulltext_seeded_session)
    # CORE column shouldn't have any predictions for non-CORE rows.
    confusion = out["confusion"]
    core_fp = sum(
        confusion.get(gold, {}).get("CORE_RELEVANT", 0)
        for gold in confusion
        if gold != "CORE_RELEVANT"
    )
    assert core_fp == 0, f"CORE false positives: {core_fp} ({confusion})"
    assert out["accuracy"] >= 0.85, out


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
    assert len(examples) >= 6

    model_path = tmp_path / "model.joblib"
    monkeypatch.setenv("PAS_LEARNED_MODEL_PATH", str(model_path))
    save_model(train_from_examples(examples, backend="sklearn"), model_path)

    classify_all(fulltext_seeded_session, use_learned=True, use_judge=True)
    report = run_evaluation(fulltext_seeded_session, settings.eval_labels_csv)
    assert report.accuracy >= 0.95, report
