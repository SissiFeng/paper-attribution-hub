from __future__ import annotations

import json
from pathlib import Path

from app.services.extractor_system_validation import (
    EffectivenessPolicy,
    audit_effectiveness_benchmark,
    evaluate_system_effectiveness,
)


def _fixture_path() -> Path:
    return (
        Path(__file__).parents[2]
        / "experiments"
        / "structured_extractor_autoresearch"
        / "fixtures"
        / "gold_test.example.jsonl"
    )


def _policy() -> EffectivenessPolicy:
    return EffectivenessPolicy(
        benchmark_tier="smoke",
        required_case_types=(
            "standard",
            "hard_negative",
            "counterfactual",
            "cross_domain_transfer",
        ),
        min_records_per_case=1,
        min_domains=2,
    )


def _read_rows(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_rows(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_smoke_gold_covers_adversarial_and_cross_domain_slices():
    report = audit_effectiveness_benchmark(_fixture_path(), _policy())

    assert report["passed"] is True
    assert report["case_counts"] == {
        "counterfactual": 2,
        "cross_domain_transfer": 1,
        "hard_negative": 1,
        "standard": 1,
    }
    assert len(report["domain_counts"]) >= 2


def test_system_metrics_are_recomputed_from_record_level_outputs(tmp_path):
    benchmark = _read_rows(_fixture_path())
    predictions = [
        {
            "record_id": row["record_id"],
            "prediction": row["target"],
        }
        for row in benchmark
    ]
    verification = [
        {
            "record_id": row["record_id"],
            "is_correct": True,
            "error_types": [],
            "field_errors": {},
        }
        for row in benchmark
    ]
    prediction_path = tmp_path / "predictions.jsonl"
    verification_path = tmp_path / "verification.jsonl"
    _write_rows(prediction_path, predictions)
    _write_rows(verification_path, verification)

    report = evaluate_system_effectiveness(
        _fixture_path(),
        prediction_path,
        verification_path,
        _policy(),
    )

    assert report["passed"] is True
    assert report["metrics"]["overall_accuracy"] == 1.0
    assert report["metrics"]["verifier_gold_exact_agreement"] == 1.0
    assert report["metrics"]["counterfactual_pair_accuracy"] == 1.0
    assert report["metrics"]["counterfactual_sensitivity"] == 1.0
    assert (
        report["metrics"]["hard_negative_claim_false_positive_rate"]
        == 0.0
    )
    assert (
        report["metrics"]["hard_negative_transfer_false_positive_rate"]
        == 0.0
    )
    assert report["metrics"]["cross_domain_transfer_accuracy"] == 1.0


def test_system_metrics_expose_false_green_verifier_outputs(tmp_path):
    benchmark = _read_rows(_fixture_path())
    predictions = [
        {
            "record_id": row["record_id"],
            "prediction": row["target"],
        }
        for row in benchmark
    ]
    by_id = {row["record_id"]: row for row in predictions}
    hard_negative = by_id["gold-hard-negative-001"]["prediction"]
    hard_negative["transferable_pattern"] = {
        "target_capability": {
            "value": "invented transfer",
            "evidence_spans": [],
        }
    }
    by_id["gold-counterfactual-001b"]["prediction"] = by_id[
        "gold-counterfactual-001a"
    ]["prediction"]
    verification = [
        {
            "record_id": row["record_id"],
            "is_correct": True,
            "error_types": [],
            "field_errors": {},
        }
        for row in benchmark
    ]
    prediction_path = tmp_path / "predictions.jsonl"
    verification_path = tmp_path / "verification.jsonl"
    _write_rows(prediction_path, predictions)
    _write_rows(verification_path, verification)

    report = evaluate_system_effectiveness(
        _fixture_path(),
        prediction_path,
        verification_path,
        _policy(),
    )

    assert report["metrics"]["overall_accuracy"] == 0.6
    assert report["metrics"]["verifier_gold_exact_agreement"] == 0.6
    assert (
        report["metrics"]["hard_negative_claim_false_positive_rate"]
        == 1.0
    )
    assert (
        report["metrics"]["hard_negative_transfer_false_positive_rate"]
        == 1.0
    )
    assert report["metrics"]["counterfactual_sensitivity"] == 0.0


def test_hard_negative_detects_non_transfer_hallucination(tmp_path):
    benchmark = _read_rows(_fixture_path())
    predictions = [
        {
            "record_id": row["record_id"],
            "prediction": row["target"],
        }
        for row in benchmark
    ]
    by_id = {row["record_id"]: row for row in predictions}
    hard_negative = by_id["gold-hard-negative-001"]["prediction"]
    hard_negative["research_strategy"]["decision"] = {
        "value": "invented decision",
        "evidence_spans": [],
    }
    verification = [
        {
            "record_id": row["record_id"],
            "is_correct": True,
            "error_types": [],
            "field_errors": {},
        }
        for row in benchmark
    ]
    prediction_path = tmp_path / "predictions.jsonl"
    verification_path = tmp_path / "verification.jsonl"
    _write_rows(prediction_path, predictions)
    _write_rows(verification_path, verification)

    report = evaluate_system_effectiveness(
        _fixture_path(),
        prediction_path,
        verification_path,
        _policy(),
    )

    assert (
        report["metrics"]["hard_negative_claim_false_positive_rate"]
        == 1.0
    )
    assert (
        report["metrics"]["hard_negative_transfer_false_positive_rate"]
        == 0.0
    )


def test_release_policy_cannot_omit_adversarial_slices(tmp_path):
    rows = _read_rows(_fixture_path())
    for row in rows:
        row["provenance"]["kind"] = "human_gold"
    benchmark = tmp_path / "release_gold.jsonl"
    _write_rows(benchmark, rows)
    policy = EffectivenessPolicy(
        benchmark_tier="release",
        required_case_types=("standard",),
        min_records_per_case=1,
        min_domains=1,
    )

    report = audit_effectiveness_benchmark(benchmark, policy)

    codes = {violation["code"] for violation in report["violations"]}
    assert report["passed"] is False
    assert "release_policy_missing_case_types" in codes
    assert "release_policy_requires_multiple_domains" in codes
    assert "release_policy_sample_floor_too_low" in codes


def test_benchmark_audit_rejects_degenerate_counterfactual_pair(tmp_path):
    rows = _read_rows(_fixture_path())
    first = next(
        row
        for row in rows
        if row["record_id"] == "gold-counterfactual-001a"
    )
    second = next(
        row
        for row in rows
        if row["record_id"] == "gold-counterfactual-001b"
    )
    second["input_text"] = first["input_text"]
    second["target"] = first["target"]
    benchmark = tmp_path / "degenerate.jsonl"
    _write_rows(benchmark, rows)

    report = audit_effectiveness_benchmark(benchmark, _policy())

    assert report["passed"] is False
    assert "degenerate_counterfactual_pair" in {
        violation["code"] for violation in report["violations"]
    }
