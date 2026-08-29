from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _model(alias: str, model_id: str):
    from app.domain_adaptation.model_benchmark import TeacherModelCandidate

    return TeacherModelCandidate(
        alias=alias,
        model_id=model_id,
        region="us-east-1",
        required_for_final=alias in {"opus", "sol"},
    )


def _package(
    root: Path,
    *,
    model_id: str,
    selection_marker: str = "shared-source",
    reviewed_protocol_count: int = 0,
    precision: float | None = None,
    recall: float | None = None,
) -> Path:
    _write_json(
        root / "manifest.json",
        {
            "package_id": "oer-electrocatalysis",
            "package_version": "benchmark",
            "extraction": {
                "mode": "teacher",
                "model": model_id,
                "region": "us-east-1",
                "prompt_version": "oer-protocol-teacher-v0.2",
                "inference_config": {
                    "temperature": 0.0,
                    "max_output_tokens": 14000,
                },
            },
            "counts": {
                "paper_count": 4,
                "corpus_record_count": 20,
                "protocol_count": 3,
                "task_count": 2,
            },
        },
    )
    _write_json(
        root / "source/selection_manifest.json",
        {"schema_version": "test", "marker": selection_marker},
    )
    _write_json(
        root / "reports/quality_report.json",
        {
            "papers_with_protocols": 3,
            "paper_coverage_by_selection_tier": {
                "primary_oer": {
                    "paper_count": 2,
                    "papers_with_protocols": 2,
                    "coverage_rate": 1.0,
                },
                "oer_review": {
                    "paper_count": 2,
                    "papers_with_protocols": 1,
                    "coverage_rate": 0.5,
                },
            },
            "evidence_span_count": 12,
            "entity_counts": {"materials": 5, "steps": 7},
            "teacher_field_audit": {
                "proposed_field_count": 20,
                "accepted_field_count": 12,
                "rejected_field_count": 8,
                "field_acceptance_rate": 0.6,
                "rejection_reason_counts": {"over_generalized": 8},
            },
            "teacher_runtime": {
                "invocation_count": 4,
                "input_token_count": 100,
                "output_token_count": 50,
                "latency_ms_total": 1234,
                "response_schema_failure_count": 0,
                "salvaged_response_count": 0,
            },
            "teacher_paper_outcome_counts": {
                "model_abstained": 1,
                "retained_protocols": 3,
            },
        },
    )
    _write_json(
        root / "reports/gold_score.json",
        {
            "reviewed_protocol_count": reviewed_protocol_count,
            "precision": precision,
            "recall": recall,
            "span_alignment_rate": precision,
        },
    )
    return root


def test_comparison_reports_operational_metrics_but_blocks_scientific_ranking(
    tmp_path,
):
    from app.domain_adaptation.model_benchmark import compare_teacher_packages

    models = [
        _model("kimi", "moonshotai.kimi-k2.5"),
        _model("opus", "us.anthropic.claude-opus-4-6-v1"),
    ]
    packages = {
        "kimi": _package(tmp_path / "kimi", model_id=models[0].model_id),
        "opus": _package(tmp_path / "opus", model_id=models[1].model_id),
    }

    report = compare_teacher_packages(
        benchmark_id="oer-teachers-v0.1",
        models=models,
        package_dirs=packages,
    )

    assert report["comparability"]["same_source_selection"] is True
    assert report["comparability"]["same_prompt_version"] is True
    assert report["scientific_ranking"]["eligible"] is False
    assert report["scientific_ranking"]["reason"] == "shared_gold_required"
    assert report["runs"][0]["metrics"]["field_acceptance_rate"] == 0.6
    assert report["runs"][0]["metrics"]["latency_ms_total"] == 1234
    assert report["runs"][0]["metrics"]["paper_coverage_by_selection_tier"] == {
        "primary_oer": {
            "paper_count": 2,
            "papers_with_protocols": 2,
            "coverage_rate": 1.0,
        },
        "oer_review": {
            "paper_count": 2,
            "papers_with_protocols": 1,
            "coverage_rate": 0.5,
        },
    }
    assert report["runs"][0]["metrics"]["teacher_paper_outcome_counts"] == {
        "model_abstained": 1,
        "retained_protocols": 3,
    }
    assert "rank" not in report["runs"][0]


def test_comparison_rejects_different_source_selections(tmp_path):
    from app.domain_adaptation.model_benchmark import compare_teacher_packages

    models = [
        _model("kimi", "moonshotai.kimi-k2.5"),
        _model("opus", "us.anthropic.claude-opus-4-6-v1"),
    ]
    packages = {
        "kimi": _package(
            tmp_path / "kimi",
            model_id=models[0].model_id,
            selection_marker="selection-a",
        ),
        "opus": _package(
            tmp_path / "opus",
            model_id=models[1].model_id,
            selection_marker="selection-b",
        ),
    }

    with pytest.raises(ValueError, match="same source selection"):
        compare_teacher_packages(
            benchmark_id="oer-teachers-v0.1",
            models=models,
            package_dirs=packages,
        )


def test_shared_gold_is_model_neutral_and_enables_scientific_ranking(tmp_path):
    from app.domain_adaptation.model_benchmark import compare_teacher_packages

    models = [
        _model("kimi", "moonshotai.kimi-k2.5"),
        _model("opus", "us.anthropic.claude-opus-4-6-v1"),
    ]
    packages = {
        "kimi": _package(tmp_path / "kimi", model_id=models[0].model_id),
        "opus": _package(tmp_path / "opus", model_id=models[1].model_id),
    }
    shared_scores = {
        "schema_version": "domain-teacher-shared-gold-scores-v0.1",
        "gold_set_id": "oer-source-first-gold-v0.1",
        "candidate_model": None,
        "annotation_complete": True,
        "scores": {
            "kimi": {
                "precision": 0.8,
                "recall": 0.7,
                "span_alignment_rate": 0.9,
            },
            "opus": {
                "precision": 0.9,
                "recall": 0.8,
                "span_alignment_rate": 0.95,
            },
        },
    }

    report = compare_teacher_packages(
        benchmark_id="oer-teachers-v0.1",
        models=models,
        package_dirs=packages,
        shared_gold_scores=shared_scores,
    )

    assert report["scientific_ranking"] == {
        "eligible": True,
        "gold_set_id": "oer-source-first-gold-v0.1",
        "metric": "f1",
        "order": ["opus", "kimi"],
    }
    assert report["runs"][0]["shared_gold"]["f1"] == pytest.approx(0.746667)
    assert report["runs"][1]["shared_gold"]["f1"] == pytest.approx(0.847059)


def test_preflight_distinguishes_access_from_structured_output():
    from app.domain_adaptation.model_benchmark import preflight_bedrock_models

    models = [
        _model("available", "model.available"),
        _model("blocked", "model.blocked"),
    ]

    class FakeClient:
        def converse(self, *, modelId, **_kwargs):
            if modelId == "model.blocked":
                error = RuntimeError("not available for this account")
                error.response = {
                    "Error": {
                        "Code": "AccessDeniedException",
                        "Message": "not available for this account",
                    }
                }
                raise error
            return {
                "output": {
                    "message": {
                        "content": [{"text": '{"protocols":[]}'}]
                    }
                },
                "stopReason": "end_turn",
                "usage": {"inputTokens": 10, "outputTokens": 5},
            }

    report = preflight_bedrock_models(
        benchmark_id="preflight",
        models=models,
        client_factory=lambda _region: FakeClient(),
    )

    assert report["models"][0]["access_status"] == "available"
    assert report["models"][0]["structured_output_status"] == "valid"
    assert report["models"][1]["access_status"] == "access_denied"
    assert report["models"][1]["structured_output_status"] == "not_tested"


def test_repository_benchmark_spec_includes_frontier_and_open_controls():
    from app.domain_adaptation.model_benchmark import load_benchmark_spec

    spec = load_benchmark_spec(
        Path(__file__).resolve().parents[2]
        / "data/domain_adapters/oer_teacher_benchmark.json"
    )
    candidates = {item.alias: item for item in spec.models}

    assert candidates["claude-opus-5"].required_for_final is True
    assert candidates["gpt-5-6-sol"].required_for_final is True
    assert candidates["kimi-k2-5"].required_for_final is True
    assert "deepseek-v3-2" in candidates
    assert "qwen3-next-80b" in candidates


def test_benchmark_cli_parses_alias_package_paths(tmp_path):
    from app.scripts.benchmark_domain_teachers import parse_package_dirs

    left = tmp_path / "left"
    right = tmp_path / "right"

    assert parse_package_dirs([f"kimi={left}", f"opus={right}"]) == {
        "kimi": left,
        "opus": right,
    }
    with pytest.raises(ValueError, match="ALIAS=PATH"):
        parse_package_dirs([str(left)])
