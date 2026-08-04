from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
import pytest

from app.services.extractor_data_factory import (
    FactoryError,
    ProfileError,
    _select_best,
    audit_training_boundary,
    load_factory_profile,
    run_extractor_data_factory,
)
from app.services.extractor_factory_validation import audit_structured_records


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _record(
    record_id: str,
    paper_id: str,
    chunk_id: str,
    text: str,
    *,
    kind: str,
    split: str,
    source_record_ids: list[str] | None = None,
    case_type: str = "standard",
    domain: str = "materials",
) -> dict:
    return {
        "record_id": record_id,
        "paper_id": paper_id,
        "chunk_id": chunk_id,
        "input_text": text,
        "provenance": {
            "kind": kind,
            "source_split": split,
            "source_record_ids": source_record_ids or [],
        },
        "evaluation_case": {
            "case_type": case_type,
            "domain": domain,
        },
        "target": {"research_strategy": {"strategy": "bayesian_optimization"}},
    }


def _factory_fixture(tmp_path: Path, *, max_attempts: int = 2) -> Path:
    _write_json(
        tmp_path / "schema.json",
        {
            "$id": "cross-sdl-extraction.test.v1",
            "type": "object",
            "required": ["research_strategy"],
            "properties": {
                "research_strategy": {
                    "type": "object",
                    "required": ["strategy"],
                    "properties": {"strategy": {"type": "string"}},
                }
            },
        },
    )
    _write_json(
        tmp_path / "ontology.json",
        {
            "ontology_id": "strategy-ontology.test.v1",
            "normalization_contract": {
                "research_strategy.problem_type": "research_goals",
                "research_strategy.strategy": "strategy_concepts",
                "research_strategy.decision": "decision_operators",
                "research_strategy.constraints": "context_conditions",
                "transferable_pattern.required_conditions": (
                    "context_conditions"
                ),
                "transferable_pattern.failure_conditions": (
                    "context_conditions"
                ),
                "evidence_spans.evidence_type": "evidence_types",
            },
            "research_goals": ["optimization"],
            "strategy_concepts": ["bayesian_optimization"],
            "decision_operators": ["exploit"],
            "context_conditions": ["measurement_noise"],
            "evidence_types": ["decision"],
        },
    )
    _write_json(tmp_path / "model_config.json", {"base_model": "example/model"})
    (tmp_path / "prompt.txt").write_text("Extract only from evidence spans.", encoding="utf-8")
    _write_jsonl(
        tmp_path / "seed_train.jsonl",
        [
            _record(
                "train-root-1",
                "paper-train",
                "chunk-train",
                "The model selected the next experiment.",
                kind="human_gold",
                split="train",
            )
        ],
    )
    _write_jsonl(
        tmp_path / "gold_test.jsonl",
        [
            _record(
                "test-1",
                "paper-test",
                "chunk-test",
                "A held-out benchmark example.",
                kind="synthetic_smoke",
                split="test",
            )
        ],
    )
    profile = {
        "profile_version": "structured-extractor-factory.v1",
        "profile_id": "cross_sdl_strategy_test",
        "inputs": {
            "seed_train": "seed_train.jsonl",
            "benchmark_test": "gold_test.jsonl",
            "extraction_schema": "schema.json",
            "ontology_version": "ontology.json",
            "prompt_version": "prompt.txt",
            "model_config": "model_config.json",
        },
        "boundary": {
            "identity_fields": ["record_id", "paper_id", "chunk_id"],
            "content_fields": ["input_text"],
            "provenance_kind_field": "provenance.kind",
            "source_split_field": "provenance.source_split",
            "source_record_ids_field": "provenance.source_record_ids",
            "allowed_provenance_kinds": [
                "human_gold",
                "hard_negative",
                "counterfactual",
                "cross_domain_paraphrase",
                "synthetic_smoke",
            ],
            "trusted_root_kinds": ["human_gold"],
            "generated_kinds": [
                "hard_negative",
                "counterfactual",
                "cross_domain_paraphrase",
            ],
            "near_duplicate_threshold": 0.92,
        },
        "budget": {
            "max_attempts": max_attempts,
            "max_wall_clock_seconds": 120,
            "max_cost_usd": 10,
            "max_tokens": 10000,
            "max_human_review_records": 100,
            "max_training_records": 100,
        },
        "effectiveness": {
            "benchmark_tier": "smoke",
            "required_case_types": ["standard"],
            "min_records_per_case": 1,
            "min_domains": 1,
        },
        "selection": {
            "primary_metric": "structured.macro_f1",
            "direction": "maximize",
            "gates": [
                {
                    "metric": "evidence.unsupported_claim_rate",
                    "operator": "<=",
                    "value": 0.05,
                }
            ],
            "tie_breakers": [
                {
                    "metric": "evidence.unsupported_claim_rate",
                    "direction": "minimize",
                }
            ],
        },
        "execution": {
            "allowed_executables": ["python"],
            "allowed_python_module_prefixes": ["pas_factory_adapters."],
        },
        "commands": {
            "generate": [
                "python",
                "-m",
                "pas_factory_adapters.generate",
                "--seed-train",
                "{seed_train}",
                "--previous-train",
                "{previous_train_records}",
                "--previous-errors",
                "{previous_error_analysis}",
                "--out",
                "{train_records}",
                "--remaining-cost-usd",
                "{remaining_cost_usd}",
                "--remaining-human-review-records",
                "{remaining_human_review_records}",
            ],
            "train_lora": [
                "python",
                "-m",
                "pas_factory_adapters.train",
                "--train",
                "{train_records}",
                "--model-config",
                "{model_config}",
                "--out",
                "{checkpoint_dir}",
            ],
            "evaluate": [
                "python",
                "-m",
                "pas_factory_adapters.evaluate",
                "--checkpoint",
                "{checkpoint_dir}",
                "--benchmark",
                "{benchmark_inputs}",
                "--checkpoint-sha256",
                "{checkpoint_sha256}",
                "--predictions-out",
                "{predictions}",
            ],
            "verify": [
                "python",
                "-m",
                "pas_factory_adapters.verify",
                "--benchmark",
                "{benchmark_test}",
                "--predictions",
                "{predictions}",
                "--predictions-sha256",
                "{predictions_sha256}",
                "--schema",
                "{extraction_schema}",
                "--ontology",
                "{ontology_version}",
                "--evaluation-profile-sha256",
                "{evaluation_profile_sha256}",
                "--checkpoint-sha256",
                "{checkpoint_sha256}",
                "--verification-records-out",
                "{verification_records}",
                "--metrics-out",
                "{metrics}",
            ],
            "analyze": [
                "python",
                "-m",
                "pas_factory_adapters.analyze",
                "--predictions",
                "{predictions}",
                "--metrics",
                "{metrics}",
                "--verification-records",
                "{verification_records}",
                "--out",
                "{error_analysis}",
            ],
        },
    }
    path = tmp_path / "profile.yaml"
    path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")
    return path


class _FakeExecutor:
    def __init__(
        self,
        *,
        metric_by_attempt: dict[int, tuple[float, float]] | None = None,
        cost_usd: float = 0.2,
    ):
        self.calls: list[tuple[str, int, dict[str, str]]] = []
        self.metric_by_attempt = metric_by_attempt or {
            1: (0.60, 0.01),
            2: (0.82, 0.02),
        }
        self.cost_usd = cost_usd

    def run(
        self,
        step: str,
        command: list[str],
        context: dict[str, str],
        timeout_seconds: float,
    ) -> None:
        attempt = int(context["attempt_number"])
        self.calls.append((step, attempt, dict(context)))
        usage = {
            "usage_nonce": context["usage_nonce"],
            "cost_usd": self.cost_usd if step == "train_lora" else 0,
            "tokens": 100 if step == "train_lora" else 0,
            "training_seconds": 1.5 if step == "train_lora" else 0,
            "human_review_records": 0,
        }
        _write_json(Path(context["step_usage"]), usage)
        if step == "generate":
            rows = [
                _record(
                    "train-root-1",
                    "paper-train",
                    "chunk-train",
                    "The model selected the next experiment.",
                    kind="human_gold",
                    split="train",
                ),
                _record(
                    f"synthetic-{attempt}",
                    f"paper-synthetic-{attempt}",
                    f"chunk-synthetic-{attempt}",
                    f"Counterfactual training example {attempt}.",
                    kind="counterfactual",
                    split="train",
                    source_record_ids=["train-root-1"],
                ),
            ]
            _write_jsonl(Path(context["train_records"]), rows)
        elif step == "train_lora":
            checkpoint = Path(context["checkpoint_dir"])
            checkpoint.mkdir()
            (checkpoint / "adapter_model.safetensors").write_bytes(b"adapter")
        elif step == "evaluate":
            _write_jsonl(
                Path(context["predictions"]),
                [
                    {
                        "record_id": "test-1",
                        "prediction": {
                            "research_strategy": {
                                "strategy": "bayesian_optimization"
                            }
                        },
                        "is_correct": attempt == 2,
                        "error_types": []
                        if attempt == 2
                        else ["research_strategy.strategy"],
                    }
                ],
            )
        elif step == "verify":
            macro_f1, unsupported_rate = self.metric_by_attempt[attempt]
            _write_jsonl(
                Path(context["verification_records"]),
                [
                    {
                        "record_id": "test-1",
                        "is_correct": attempt == 2,
                        "error_types": []
                        if attempt == 2
                        else ["research_strategy.strategy"],
                        "field_errors": {},
                    }
                ],
            )
            _write_json(
                Path(context["metrics"]),
                {
                    "evaluation_profile_sha256": context[
                        "evaluation_profile_sha256"
                    ],
                    "checkpoint_sha256": context["checkpoint_sha256"],
                    "predictions_sha256": context["predictions_sha256"],
                    "verification_records_sha256": hashlib.sha256(
                        Path(context["verification_records"]).read_bytes()
                    ).hexdigest(),
                    "structured": {"macro_f1": macro_f1},
                    "evidence": {"unsupported_claim_rate": unsupported_rate},
                },
            )
        elif step == "analyze":
            _write_json(
                Path(context["error_analysis"]),
                {
                    "analysis_version": "structured-extractor-errors.v1",
                    "total_predictions": 1,
                    "failed_predictions": 0 if attempt == 2 else 1,
                    "error_type_counts": {}
                    if attempt == 2
                    else {"research_strategy.strategy": 1},
                    "targeting_priorities": []
                    if attempt == 2
                    else [
                        {
                            "category": "research_strategy.strategy",
                            "count": 1,
                        }
                    ],
                },
            )


def test_factory_runs_closed_loop_and_selects_best_checkpoint(tmp_path):
    profile = load_factory_profile(_factory_fixture(tmp_path))
    executor = _FakeExecutor()

    report = run_extractor_data_factory(
        profile,
        tmp_path / "run",
        executor=executor,
    )

    assert report["selected"]["attempt_id"] == "attempt_002"
    assert report["selected"]["primary_metric"] == 0.82
    assert report["selected"]["checkpoint"] == "attempt_002/checkpoint"
    assert report["termination_reason"] == "attempt_budget_exhausted"
    assert [call[:2] for call in executor.calls] == [
        ("generate", 1),
        ("train_lora", 1),
        ("evaluate", 1),
        ("verify", 1),
        ("analyze", 1),
        ("generate", 2),
        ("train_lora", 2),
        ("evaluate", 2),
        ("verify", 2),
        ("analyze", 2),
    ]

    second_generate = executor.calls[5][2]
    assert second_generate["previous_error_analysis"].endswith(
        "attempt_001/error_analysis.json"
    )
    for attempt_id in ("attempt_001", "attempt_002"):
        attempt_dir = tmp_path / "run" / attempt_id
        for name in (
            "train_records.jsonl",
            "extraction_schema.json",
            "ontology_version.json",
            "prompt_version.txt",
            "model_config.json",
            "predictions.jsonl",
            "verification_records.jsonl",
            "error_analysis.json",
            "metrics.json",
            "system_effectiveness.json",
            "cost.json",
            "checkpoint_manifest.json",
            "boundary_report.json",
            "data_lineage.json",
            "verifier.json",
            "attempt_manifest.json",
        ):
            assert (attempt_dir / name).exists(), (attempt_id, name)

    first_analysis = json.loads(
        (tmp_path / "run/attempt_001/error_analysis.json").read_text()
    )
    assert first_analysis["error_type_counts"] == {
        "research_strategy.strategy": 1
    }
    assert (tmp_path / "run/selection.json").exists()
    assert len((tmp_path / "run/trajectory.jsonl").read_text().splitlines()) == 2
    lineage = json.loads(
        (tmp_path / "run/attempt_002/data_lineage.json").read_text()
    )
    generated = next(
        row
        for row in lineage["record_lineage"]
        if row["record_id"] == "synthetic-2"
    )
    assert generated["source_records"][0]["record_id"] == "train-root-1"
    assert len(generated["source_records"][0]["trusted_record_sha256"]) == 64


def test_boundary_rejects_test_identity_content_and_lineage_leakage(tmp_path):
    profile = load_factory_profile(_factory_fixture(tmp_path))
    leaking_train = tmp_path / "leaking.jsonl"
    _write_jsonl(
        leaking_train,
        [
            _record(
                "test-1",
                "paper-test",
                "chunk-other",
                "A held-out benchmark example.",
                kind="counterfactual",
                split="train",
                source_record_ids=["test-1"],
            )
        ],
    )

    report = audit_training_boundary(
        leaking_train,
        profile.inputs.benchmark_test,
        profile.inputs.seed_train,
        profile.boundary,
    )

    assert report["passed"] is False
    codes = {violation["code"] for violation in report["violations"]}
    assert "identity_overlap" in codes
    assert "content_overlap" in codes
    assert "untrusted_lineage" in codes


def test_boundary_requires_auditable_identity_and_content_fields(tmp_path):
    profile = load_factory_profile(_factory_fixture(tmp_path))
    incomplete_train = tmp_path / "incomplete.jsonl"
    _write_jsonl(
        incomplete_train,
        [
            {
                "record_id": "incomplete-1",
                "provenance": {
                    "kind": "human_gold",
                    "source_split": "train",
                    "source_record_ids": [],
                },
            }
        ],
    )

    report = audit_training_boundary(
        incomplete_train,
        profile.inputs.benchmark_test,
        profile.inputs.seed_train,
        profile.boundary,
    )

    codes = {violation["code"] for violation in report["violations"]}
    assert report["passed"] is False
    assert "missing_identity_field" in codes
    assert "missing_content_field" in codes


def test_boundary_rejects_new_or_mutated_human_gold(tmp_path):
    profile = load_factory_profile(_factory_fixture(tmp_path))
    train = tmp_path / "fake_gold.jsonl"
    _write_jsonl(
        train,
        [
            _record(
                "train-root-1",
                "paper-train",
                "chunk-train",
                "Mutated gold content.",
                kind="human_gold",
                split="train",
            ),
            _record(
                "invented-gold",
                "paper-new",
                "chunk-new",
                "An invented human label.",
                kind="human_gold",
                split="train",
            ),
        ],
    )

    report = audit_training_boundary(
        train,
        profile.inputs.benchmark_test,
        profile.inputs.seed_train,
        profile.boundary,
    )

    codes = {violation["code"] for violation in report["violations"]}
    assert "mutated_trusted_root" in codes
    assert "new_trusted_root" in codes


def test_boundary_rejects_near_duplicate_benchmark_text(tmp_path):
    profile = load_factory_profile(_factory_fixture(tmp_path))
    train = tmp_path / "near_duplicate.jsonl"
    _write_jsonl(
        train,
        [
            _record(
                "near-1",
                "paper-near",
                "chunk-near",
                "A held-out benchmark example!",
                kind="counterfactual",
                split="train",
                source_record_ids=["train-root-1"],
            )
        ],
    )

    report = audit_training_boundary(
        train,
        profile.inputs.benchmark_test,
        profile.inputs.seed_train,
        profile.boundary,
    )

    assert "near_content_overlap" in {
        violation["code"] for violation in report["violations"]
    }


def test_boundary_rejects_padded_and_context_chunk_benchmark_leakage(
    tmp_path,
):
    profile = load_factory_profile(_factory_fixture(tmp_path))
    benchmark_text = "A held-out benchmark example."
    train = tmp_path / "padded_context_leak.jsonl"
    padded = _record(
        "padded-1",
        "paper-padded",
        "chunk-padded",
        benchmark_text + " " + "unrelated filler " * 30,
        kind="counterfactual",
        split="train",
        source_record_ids=["train-root-1"],
    )
    context_leak = _record(
        "context-1",
        "paper-context",
        "chunk-context",
        "A distinct training sentence.",
        kind="counterfactual",
        split="train",
        source_record_ids=["train-root-1"],
    )
    context_leak["context_chunks"] = {"chunk-test": benchmark_text}
    _write_jsonl(train, [padded, context_leak])

    report = audit_training_boundary(
        train,
        profile.inputs.benchmark_test,
        profile.inputs.seed_train,
        profile.boundary,
    )

    codes = {violation["code"] for violation in report["violations"]}
    assert "near_content_overlap" in codes
    assert "context_chunk_identity_overlap" in codes
    assert "content_overlap" in codes


def test_boundary_rejects_duplicate_benchmark_records(tmp_path):
    profile = load_factory_profile(_factory_fixture(tmp_path))
    benchmark_rows = [
        json.loads(line)
        for line in profile.inputs.benchmark_test.read_text().splitlines()
    ]
    _write_jsonl(profile.inputs.benchmark_test, benchmark_rows * 2)

    report = audit_training_boundary(
        profile.inputs.seed_train,
        profile.inputs.benchmark_test,
        profile.inputs.seed_train,
        profile.boundary,
    )

    codes = {violation["code"] for violation in report["violations"]}
    assert "duplicate_benchmark_record_id" in codes
    assert "duplicate_benchmark_content" in codes


def test_unsupported_claim_gate_beats_higher_field_f1(tmp_path):
    profile = load_factory_profile(_factory_fixture(tmp_path))
    executor = _FakeExecutor(
        metric_by_attempt={
            1: (0.70, 0.01),
            2: (0.95, 0.20),
        }
    )

    report = run_extractor_data_factory(
        profile,
        tmp_path / "run",
        executor=executor,
    )

    assert report["selected"]["attempt_id"] == "attempt_001"
    second = report["attempts"][1]
    assert second["eligible"] is False
    assert "evidence.unsupported_claim_rate <= 0.05" in second["rejection_reasons"]


def test_cost_budget_stops_before_another_attempt(tmp_path):
    profile = load_factory_profile(_factory_fixture(tmp_path, max_attempts=4))
    profile = profile.with_budget(max_cost_usd=1.0)
    executor = _FakeExecutor(cost_usd=1.0)

    report = run_extractor_data_factory(
        profile,
        tmp_path / "run",
        executor=executor,
    )

    assert report["termination_reason"] == "cost_budget_exhausted"
    assert {attempt for _step, attempt, _context in executor.calls} == {1}
    assert report["totals"]["cost_usd"] == 1.0


def test_non_finite_usage_fails_closed_as_unknown_spend(tmp_path):
    profile = load_factory_profile(_factory_fixture(tmp_path, max_attempts=1))

    class _NanUsage(_FakeExecutor):
        def run(self, step, command, context, timeout_seconds):
            super().run(step, command, context, timeout_seconds)
            if step == "train_lora":
                usage = json.loads(Path(context["step_usage"]).read_text())
                usage["cost_usd"] = float("nan")
                _write_json(Path(context["step_usage"]), usage)

    report = run_extractor_data_factory(
        profile,
        tmp_path / "run",
        executor=_NanUsage(),
    )

    assert report["selected"] is None
    assert report["totals"]["usage_complete"] is False
    assert "spend is unknown" in report["attempts"][0]["error"]


def test_non_finite_selection_metric_rejects_attempt(tmp_path):
    profile = load_factory_profile(_factory_fixture(tmp_path, max_attempts=1))
    executor = _FakeExecutor(
        metric_by_attempt={1: (float("nan"), 0.01)}
    )

    report = run_extractor_data_factory(
        profile,
        tmp_path / "run",
        executor=executor,
    )

    assert report["selected"] is None
    assert "finite numeric metric" in report["attempts"][0]["error"]


def test_benchmark_mutation_invalidates_attempt(tmp_path):
    profile = load_factory_profile(_factory_fixture(tmp_path, max_attempts=1))

    class _MutatingEvaluator(_FakeExecutor):
        def run(self, step, command, context, timeout_seconds):
            super().run(step, command, context, timeout_seconds)
            if step == "evaluate":
                assert "benchmark_test" not in context
            if step == "verify":
                Path(context["benchmark_test"]).write_text(
                    '{"record_id":"changed"}\n',
                    encoding="utf-8",
                )

    report = run_extractor_data_factory(
        profile,
        tmp_path / "run",
        executor=_MutatingEvaluator(),
    )

    assert report["selected"] is None
    assert report["termination_reason"] == "attempt_failed"
    assert report["attempts"][0]["error"] in {
        "verification_records.jsonl must cover every benchmark record once.",
        "Frozen input changed during the run: benchmark_test.",
    }


def test_invalid_generated_target_fails_before_training(tmp_path):
    profile = load_factory_profile(_factory_fixture(tmp_path, max_attempts=1))

    class _InvalidGenerator(_FakeExecutor):
        def run(self, step, command, context, timeout_seconds):
            super().run(step, command, context, timeout_seconds)
            if step == "generate":
                rows = [
                    json.loads(line)
                    for line in Path(context["train_records"])
                    .read_text(encoding="utf-8")
                    .splitlines()
                ]
                rows[0]["target"] = {}
                _write_jsonl(Path(context["train_records"]), rows)

    executor = _InvalidGenerator()
    report = run_extractor_data_factory(
        profile,
        tmp_path / "run",
        executor=executor,
    )

    assert report["selected"] is None
    assert [step for step, _attempt, _context in executor.calls] == ["generate"]
    assert "research_strategy is required" in report["attempts"][0]["error"]


def test_profile_rejects_command_outside_reviewed_allowlist(tmp_path):
    profile_path = _factory_fixture(tmp_path)
    raw = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    raw["commands"]["generate"] = ["/usr/bin/env"]
    profile_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    with pytest.raises(ProfileError, match="not in execution.allowed_executables"):
        load_factory_profile(profile_path)


def test_profile_rejects_literal_command_output_path(tmp_path):
    profile_path = _factory_fixture(tmp_path)
    raw = yaml.safe_load(profile_path.read_text())
    command = raw["commands"]["generate"]
    command[command.index("{train_records}")] = "/tmp/outside.jsonl"
    profile_path.write_text(yaml.safe_dump(raw, sort_keys=False))

    with pytest.raises(ProfileError, match="reviewed step contract"):
        load_factory_profile(profile_path)


def test_profile_rejects_gold_fields_in_inference_boundary(tmp_path):
    profile_path = _factory_fixture(tmp_path)
    raw = yaml.safe_load(profile_path.read_text())
    raw["boundary"]["content_fields"].append("target")
    profile_path.write_text(yaml.safe_dump(raw, sort_keys=False))

    with pytest.raises(ProfileError, match="boundary must audit"):
        load_factory_profile(profile_path)


def test_profile_cannot_weaken_required_leakage_checks(tmp_path):
    profile_path = _factory_fixture(tmp_path)
    raw = yaml.safe_load(profile_path.read_text())
    raw["boundary"]["identity_fields"] = ["record_id"]
    raw["boundary"]["content_fields"] = ["context_chunks"]
    raw["boundary"]["near_duplicate_threshold"] = 1.0
    profile_path.write_text(yaml.safe_dump(raw, sort_keys=False))

    with pytest.raises(ProfileError, match="must audit record_id"):
        load_factory_profile(profile_path)


def test_profile_rejects_input_role_alias_with_benchmark(tmp_path):
    profile_path = _factory_fixture(tmp_path)
    raw = yaml.safe_load(profile_path.read_text())
    raw["inputs"]["prompt_version"] = raw["inputs"]["benchmark_test"]
    profile_path.write_text(yaml.safe_dump(raw, sort_keys=False))

    with pytest.raises(ProfileError, match="must be distinct files"):
        load_factory_profile(profile_path)


def test_profile_rejects_benchmark_content_copied_into_prompt(tmp_path):
    profile_path = _factory_fixture(tmp_path)
    (tmp_path / "prompt.txt").write_text(
        "Instructions plus A held-out benchmark example.",
        encoding="utf-8",
    )

    with pytest.raises(ProfileError, match="held-out benchmark input"):
        load_factory_profile(profile_path)


def test_factory_rejects_python_path_environment_injection(tmp_path):
    profile = load_factory_profile(_factory_fixture(tmp_path))

    with pytest.raises(ProfileError, match="cannot be passed"):
        run_extractor_data_factory(
            profile,
            tmp_path / "run",
            executor=_FakeExecutor(),
            pass_environment=("PYTHONPATH",),
        )


def test_release_profile_requires_system_effectiveness_gates(tmp_path):
    profile_path = _factory_fixture(tmp_path)
    raw = yaml.safe_load(profile_path.read_text())
    raw["effectiveness"] = {
        "benchmark_tier": "release",
        "required_case_types": [
            "standard",
            "hard_negative",
            "counterfactual",
            "cross_domain_transfer",
        ],
        "min_records_per_case": 1,
        "min_domains": 2,
    }
    profile_path.write_text(yaml.safe_dump(raw, sort_keys=False))

    with pytest.raises(ProfileError, match="Release effectiveness requires"):
        load_factory_profile(profile_path)


def test_resume_preserves_interrupted_attempt_and_continues(tmp_path):
    profile = load_factory_profile(_factory_fixture(tmp_path, max_attempts=2))

    class _InterruptingTrainer(_FakeExecutor):
        def run(self, step, command, context, timeout_seconds):
            super().run(step, command, context, timeout_seconds)
            if step == "train_lora":
                raise KeyboardInterrupt

    run_dir = tmp_path / "run"
    with pytest.raises(KeyboardInterrupt):
        run_extractor_data_factory(
            profile,
            run_dir,
            executor=_InterruptingTrainer(),
        )

    resumed_executor = _FakeExecutor(metric_by_attempt={2: (0.81, 0.01)})
    report = run_extractor_data_factory(
        profile,
        run_dir,
        executor=resumed_executor,
        resume=True,
    )

    assert report["attempts"][0]["status"] == "interrupted"
    assert report["selected"]["attempt_id"] == "attempt_002"
    assert {attempt for _step, attempt, _context in resumed_executor.calls} == {2}


def test_resume_rejects_unknown_active_step_spend(tmp_path):
    profile = load_factory_profile(_factory_fixture(tmp_path, max_attempts=2))

    class _UnmeteredInterruption(_FakeExecutor):
        def run(self, step, command, context, timeout_seconds):
            if step == "train_lora":
                raise KeyboardInterrupt
            super().run(step, command, context, timeout_seconds)

    run_dir = tmp_path / "run"
    with pytest.raises(KeyboardInterrupt):
        run_extractor_data_factory(
            profile,
            run_dir,
            executor=_UnmeteredInterruption(),
        )

    with pytest.raises(FactoryError, match="exact usage ledger"):
        run_extractor_data_factory(
            profile,
            run_dir,
            executor=_FakeExecutor(),
            resume=True,
        )


def test_resume_rejects_forged_nonce_for_prior_step(tmp_path):
    profile = load_factory_profile(_factory_fixture(tmp_path, max_attempts=2))

    class _InterruptingTrainer(_FakeExecutor):
        def run(self, step, command, context, timeout_seconds):
            super().run(step, command, context, timeout_seconds)
            if step == "train_lora":
                raise KeyboardInterrupt

    run_dir = tmp_path / "run"
    with pytest.raises(KeyboardInterrupt):
        run_extractor_data_factory(
            profile,
            run_dir,
            executor=_InterruptingTrainer(),
        )
    usage_path = run_dir / "attempt_001/usage/generate.json"
    usage = json.loads(usage_path.read_text())
    usage["usage_nonce"] = "forged-prior-step-nonce"
    _write_json(usage_path, usage)

    with pytest.raises(FactoryError, match="invalid usage_nonce"):
        run_extractor_data_factory(
            profile,
            run_dir,
            executor=_FakeExecutor(),
            resume=True,
        )


def test_resume_charges_interrupted_attempt_wall_clock(tmp_path):
    profile = load_factory_profile(_factory_fixture(tmp_path, max_attempts=2))

    class _InterruptingTrainer(_FakeExecutor):
        def run(self, step, command, context, timeout_seconds):
            super().run(step, command, context, timeout_seconds)
            if step == "train_lora":
                raise KeyboardInterrupt

    run_dir = tmp_path / "run"
    with pytest.raises(KeyboardInterrupt):
        run_extractor_data_factory(
            profile,
            run_dir,
            executor=_InterruptingTrainer(),
        )
    state_path = run_dir / "run_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["attempt_started_at"] = "2020-01-01T00:00:00+00:00"
    _write_json(state_path, state)

    report = run_extractor_data_factory(
        profile,
        run_dir,
        executor=_FakeExecutor(),
        resume=True,
    )

    assert report["termination_reason"] == "wall_clock_budget_exhausted"
    assert report["attempts"][0]["cost"]["wall_clock_seconds"] > 120


def test_resume_revalidates_completed_attempt_artifacts(tmp_path):
    profile = load_factory_profile(_factory_fixture(tmp_path, max_attempts=1))
    run_dir = tmp_path / "run"
    run_extractor_data_factory(profile, run_dir, executor=_FakeExecutor())
    checkpoint = run_dir / "attempt_001/checkpoint/adapter_model.safetensors"
    checkpoint.write_bytes(b"tampered")

    with pytest.raises(FactoryError, match="Checkpoint changed"):
        run_extractor_data_factory(
            profile,
            run_dir,
            executor=_FakeExecutor(),
            resume=True,
        )


def test_resume_of_finished_run_revalidates_final_selection(tmp_path):
    profile = load_factory_profile(_factory_fixture(tmp_path, max_attempts=1))
    run_dir = tmp_path / "run"
    report = run_extractor_data_factory(
        profile,
        run_dir,
        executor=_FakeExecutor(),
    )

    resumed = run_extractor_data_factory(
        profile,
        run_dir,
        executor=_FakeExecutor(),
        resume=True,
    )

    assert resumed == report


def test_resume_rejects_tampered_finished_manifest(tmp_path):
    profile = load_factory_profile(_factory_fixture(tmp_path, max_attempts=1))
    run_dir = tmp_path / "run"
    run_extractor_data_factory(profile, run_dir, executor=_FakeExecutor())
    manifest_path = run_dir / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["selected"]["checkpoint_sha256"] = "forged"
    _write_json(manifest_path, manifest)

    with pytest.raises(FactoryError, match="manifest does not reconcile"):
        run_extractor_data_factory(
            profile,
            run_dir,
            executor=_FakeExecutor(),
            resume=True,
        )


def test_final_selection_revalidates_earlier_checkpoint(tmp_path):
    profile = load_factory_profile(_factory_fixture(tmp_path, max_attempts=2))

    class _MutateEarlierCheckpoint(_FakeExecutor):
        def run(self, step, command, context, timeout_seconds):
            super().run(step, command, context, timeout_seconds)
            if step == "generate" and context["attempt_number"] == "2":
                checkpoint = (
                    Path(context["attempt_dir"]).parent
                    / "attempt_001/checkpoint/adapter_model.safetensors"
                )
                checkpoint.write_bytes(b"tampered-after-completion")

    with pytest.raises(FactoryError, match="Checkpoint changed"):
        run_extractor_data_factory(
            profile,
            tmp_path / "run",
            executor=_MutateEarlierCheckpoint(),
        )


def test_checkpoint_selection_ignores_non_completed_attempts(tmp_path):
    profile = load_factory_profile(_factory_fixture(tmp_path))
    attempts = [
        {
            "attempt_id": "attempt_001",
            "attempt_number": 1,
            "status": "failed",
            "eligible": True,
            "primary_metric": 1.0,
            "tie_breaker_metrics": {
                "evidence.unsupported_claim_rate": 0.0
            },
        }
    ]

    assert _select_best(attempts, profile.selection) is None


def test_local_system_gate_overrides_false_green_verifier(tmp_path):
    profile_path = _factory_fixture(tmp_path, max_attempts=1)
    raw = yaml.safe_load(profile_path.read_text())
    raw["effectiveness"]["required_case_types"] = ["hard_negative"]
    raw["selection"]["gates"].append(
        {
            "metric": (
                "system.hard_negative_transfer_false_positive_rate"
            ),
            "operator": "<=",
            "value": 0.0,
        }
    )
    profile_path.write_text(yaml.safe_dump(raw, sort_keys=False))
    benchmark_path = tmp_path / "gold_test.jsonl"
    benchmark = json.loads(benchmark_path.read_text())
    benchmark["evaluation_case"]["case_type"] = "hard_negative"
    benchmark["target"]["research_strategy"]["strategy"] = ""
    _write_jsonl(benchmark_path, [benchmark])
    profile = load_factory_profile(profile_path)

    class _FalseGreenVerifier(_FakeExecutor):
        def run(self, step, command, context, timeout_seconds):
            super().run(step, command, context, timeout_seconds)
            if step == "evaluate":
                predictions = [
                    json.loads(line)
                    for line in Path(context["predictions"])
                    .read_text()
                    .splitlines()
                ]
                predictions[0]["prediction"]["transferable_pattern"] = {
                    "target_capability": {
                        "value": "invented transfer",
                    }
                }
                _write_jsonl(Path(context["predictions"]), predictions)

    report = run_extractor_data_factory(
        profile,
        tmp_path / "run",
        executor=_FalseGreenVerifier(
            metric_by_attempt={1: (1.0, 0.0)}
        ),
    )

    assert report["selected"] is None
    assert (
        "system.hard_negative_transfer_false_positive_rate <= 0.0"
        in report["attempts"][0]["rejection_reasons"]
    )


def test_grounded_claim_requires_span_and_layer_specific_concept(tmp_path):
    root = Path(__file__).parents[2]
    contract_dir = (
        root / "experiments/structured_extractor_autoresearch/contracts"
    )
    fixture = root / (
        "experiments/structured_extractor_autoresearch/fixtures/"
        "seed_train.example.jsonl"
    )
    row = json.loads(fixture.read_text(encoding="utf-8"))
    row["target"]["research_strategy"]["decision"]["evidence_spans"] = []
    row["target"]["research_strategy"]["strategy"][
        "canonical_concept"
    ] = "explore"
    records = tmp_path / "invalid_grounding.jsonl"
    _write_jsonl(records, [row])

    report = audit_structured_records(
        records,
        payload_field="target",
        schema_path=contract_dir / "extraction_schema.json",
        ontology_path=contract_dir / "ontology_version.json",
    )

    messages = {error["message"] for error in report["errors"]}
    assert (
        "a non-null claim requires at least one evidence span" in messages
    )
    assert (
        "unknown strategy_concepts canonical_concept 'explore'" in messages
    )


def test_grounding_rejects_empty_span_and_unbound_surface_form(tmp_path):
    root = Path(__file__).parents[2]
    contract_dir = (
        root / "experiments/structured_extractor_autoresearch/contracts"
    )
    fixture = root / (
        "experiments/structured_extractor_autoresearch/fixtures/"
        "seed_train.example.jsonl"
    )
    row = json.loads(fixture.read_text(encoding="utf-8"))
    decision = row["target"]["research_strategy"]["decision"]
    decision["surface_form"] = "an invented decision"
    decision["evidence_spans"][0].update(
        {
            "text_span": "",
            "start_offset": 0,
            "end_offset": 0,
        }
    )
    records = tmp_path / "empty_span.jsonl"
    _write_jsonl(records, [row])

    report = audit_structured_records(
        records,
        payload_field="target",
        schema_path=contract_dir / "extraction_schema.json",
        ontology_path=contract_dir / "ontology_version.json",
    )

    messages = {error["message"] for error in report["errors"]}
    assert "offsets are outside the cited chunk" in messages
    assert "surface_form is not bound to a cited evidence span" in messages


def test_ontology_normalization_contract_cannot_drift_from_layers(tmp_path):
    root = Path(__file__).parents[2]
    contract_dir = (
        root / "experiments/structured_extractor_autoresearch/contracts"
    )
    fixture = root / (
        "experiments/structured_extractor_autoresearch/fixtures/"
        "seed_train.example.jsonl"
    )
    ontology = json.loads(
        (contract_dir / "ontology_version.json").read_text()
    )
    ontology["normalization_contract"]["research_strategy.strategy"] = (
        "decision_operators"
    )
    ontology_path = tmp_path / "drifted_ontology.json"
    _write_json(ontology_path, ontology)

    report = audit_structured_records(
        fixture,
        payload_field="target",
        schema_path=contract_dir / "extraction_schema.json",
        ontology_path=ontology_path,
    )

    assert report["passed"] is False
    assert (
        "must map to ontology layer 'strategy_concepts'"
        in {error["message"] for error in report["errors"]}
    )


def test_structured_validation_rejects_non_finite_confidence(tmp_path):
    root = Path(__file__).parents[2]
    contract_dir = (
        root / "experiments/structured_extractor_autoresearch/contracts"
    )
    fixture = root / (
        "experiments/structured_extractor_autoresearch/fixtures/"
        "seed_train.example.jsonl"
    )
    row = json.loads(fixture.read_text(encoding="utf-8"))
    row["target"]["research_strategy"]["decision"]["evidence_spans"][0][
        "confidence"
    ] = float("nan")
    records = tmp_path / "non_finite_confidence.jsonl"
    _write_jsonl(records, [row])

    report = audit_structured_records(
        records,
        payload_field="target",
        schema_path=contract_dir / "extraction_schema.json",
        ontology_path=contract_dir / "ontology_version.json",
    )

    assert report["passed"] is False
    assert "must be finite" in {
        error["message"] for error in report["errors"]
    }
