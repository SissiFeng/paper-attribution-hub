"""Comparable, fail-closed evaluation of domain-adaptation teacher models."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from pydantic import Field, model_validator

from app.domain_adaptation.models import DomainModel
from app.domain_adaptation.teacher import parse_teacher_response


class TeacherModelCandidate(DomainModel):
    """One Bedrock teacher candidate in a frozen benchmark matrix."""

    alias: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    provider: str = "amazon_bedrock"
    model_id: str = Field(min_length=1)
    region: str = Field(min_length=1)
    max_output_tokens: int = Field(default=14000, gt=0)
    required_for_final: bool = False


class TeacherBenchmarkSpec(DomainModel):
    schema_version: str = "domain-teacher-benchmark-spec-v0.1"
    benchmark_id: str = Field(min_length=1)
    source_selection: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    temperature: float = 0.0
    models: list[TeacherModelCandidate] = Field(min_length=2)

    @model_validator(mode="after")
    def unique_candidates(self) -> "TeacherBenchmarkSpec":
        aliases = [item.alias for item in self.models]
        if len(aliases) != len(set(aliases)):
            raise ValueError("Teacher model aliases must be unique")
        identities = [(item.region, item.model_id) for item in self.models]
        if len(identities) != len(set(identities)):
            raise ValueError("Teacher model region/model pairs must be unique")
        return self


def load_benchmark_spec(path: str | Path) -> TeacherBenchmarkSpec:
    return TeacherBenchmarkSpec.model_validate(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )


def _response_error(error: Exception) -> tuple[str, str]:
    response = getattr(error, "response", {})
    error_payload = response.get("Error", {}) if isinstance(response, dict) else {}
    code = str(error_payload.get("Code") or error.__class__.__name__)
    message = str(error_payload.get("Message") or error)
    return code, message[:1000]


def preflight_bedrock_models(
    *,
    benchmark_id: str,
    models: list[TeacherModelCandidate],
    client_factory: Callable[[str], Any],
) -> dict[str, Any]:
    """Check account access and minimal JSON behavior without claiming quality."""
    clients: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    for model in models:
        client = clients.setdefault(model.region, client_factory(model.region))
        row: dict[str, Any] = {
            "alias": model.alias,
            "provider": model.provider,
            "model_id": model.model_id,
            "region": model.region,
            "required_for_final": model.required_for_final,
            "access_status": "error",
            "structured_output_status": "not_tested",
        }
        try:
            response = client.converse(
                modelId=model.model_id,
                system=[
                    {
                        "text": (
                            "Return only valid JSON. Do not use markdown."
                        )
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "text": (
                                    "Return exactly this JSON object: "
                                    '{"protocols":[]}'
                                )
                            }
                        ],
                    }
                ],
                inferenceConfig={"temperature": 0.0, "maxTokens": 64},
            )
        except Exception as error:  # provider exceptions share no stable base
            code, message = _response_error(error)
            row["access_status"] = (
                "access_denied"
                if code in {"AccessDeniedException", "UnauthorizedException"}
                else "error"
            )
            row["error_code"] = code
            row["error_message"] = message
        else:
            text = "".join(
                block.get("text", "")
                for block in response["output"]["message"]["content"]
            )
            parsed = parse_teacher_response(text)
            row.update(
                {
                    "access_status": "available",
                    "structured_output_status": (
                        "valid" if not parsed.schema_invalid else "invalid"
                    ),
                    "stop_reason": response.get("stopReason"),
                    "usage": response.get("usage", {}),
                }
            )
        rows.append(row)
    return {
        "schema_version": "domain-teacher-preflight-v0.1",
        "benchmark_id": benchmark_id,
        "claims_boundary": (
            "Preflight proves account access and minimal JSON behavior only; "
            "it does not measure scientific extraction quality."
        ),
        "models": rows,
    }


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_summary(
    model: TeacherModelCandidate,
    package_dir: Path,
) -> tuple[dict[str, Any], str, str, str]:
    manifest = _read_json(package_dir / "manifest.json")
    quality = _read_json(package_dir / "reports/quality_report.json")
    extraction = manifest.get("extraction", {})
    if extraction.get("mode") != "teacher":
        raise ValueError(f"{model.alias} is not a teacher-model package")
    if extraction.get("model") != model.model_id:
        raise ValueError(
            f"{model.alias} package model does not match the benchmark spec"
        )
    if extraction.get("region") != model.region:
        raise ValueError(
            f"{model.alias} package region does not match the benchmark spec"
        )

    audit = quality.get("teacher_field_audit", {})
    runtime = quality.get("teacher_runtime", {})
    counts = manifest.get("counts", {})
    entity_counts = quality.get("entity_counts", {})
    metrics = {
        "paper_count": counts.get("paper_count", 0),
        "papers_with_protocols": quality.get("papers_with_protocols", 0),
        "paper_coverage_by_selection_tier": quality.get(
            "paper_coverage_by_selection_tier", {}
        ),
        "protocol_count": counts.get("protocol_count", 0),
        "evidence_span_count": quality.get("evidence_span_count", 0),
        "entity_count": sum(
            int(value)
            for key, value in entity_counts.items()
            if key != "relations"
        ),
        "task_count": counts.get("task_count", 0),
        "proposed_field_count": audit.get("proposed_field_count", 0),
        "accepted_field_count": audit.get("accepted_field_count", 0),
        "rejected_field_count": audit.get("rejected_field_count", 0),
        "field_acceptance_rate": audit.get("field_acceptance_rate"),
        "rejection_reason_counts": audit.get("rejection_reason_counts", {}),
        "response_schema_failure_count": runtime.get(
            "response_schema_failure_count", 0
        ),
        "salvaged_response_count": runtime.get("salvaged_response_count", 0),
        "input_token_count": runtime.get("input_token_count", 0),
        "output_token_count": runtime.get("output_token_count", 0),
        "latency_ms_total": runtime.get("latency_ms_total"),
        "teacher_paper_outcome_counts": quality.get(
            "teacher_paper_outcome_counts", {}
        ),
    }
    summary = {
        "alias": model.alias,
        "provider": model.provider,
        "model_id": model.model_id,
        "region": model.region,
        "required_for_final": model.required_for_final,
        "package_dir": str(package_dir),
        "metrics": metrics,
    }
    inference_config = extraction.get("inference_config")
    return (
        summary,
        _file_sha256(package_dir / "source/selection_manifest.json"),
        str(extraction.get("prompt_version")),
        json.dumps(inference_config, sort_keys=True),
    )


def _shared_gold_ranking(
    runs: list[dict[str, Any]],
    shared_gold_scores: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if shared_gold_scores is None:
        return {"eligible": False, "reason": "shared_gold_required"}
    if shared_gold_scores.get("candidate_model") is not None:
        raise ValueError("Shared gold must be independent of a candidate model")
    if not shared_gold_scores.get("annotation_complete"):
        return {"eligible": False, "reason": "shared_gold_incomplete"}
    scores = shared_gold_scores.get("scores", {})
    aliases = {run["alias"] for run in runs}
    if set(scores) != aliases:
        raise ValueError("Shared-gold scores must cover every compared model")

    for run in runs:
        score = dict(scores[run["alias"]])
        precision = score.get("precision")
        recall = score.get("recall")
        if precision is None or recall is None:
            raise ValueError("Shared-gold precision and recall must be present")
        denominator = precision + recall
        score["f1"] = round(
            2 * precision * recall / denominator if denominator else 0.0,
            6,
        )
        run["shared_gold"] = score
    order = [
        run["alias"]
        for run in sorted(
            runs,
            key=lambda item: (-item["shared_gold"]["f1"], item["alias"]),
        )
    ]
    return {
        "eligible": True,
        "gold_set_id": shared_gold_scores.get("gold_set_id"),
        "metric": "f1",
        "order": order,
    }


def compare_teacher_packages(
    *,
    benchmark_id: str,
    models: list[TeacherModelCandidate],
    package_dirs: Mapping[str, str | Path],
    shared_gold_scores: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare identical package runs and refuse model-local gold ranking."""
    model_by_alias = {item.alias: item for item in models}
    unknown = set(package_dirs) - set(model_by_alias)
    if unknown:
        raise ValueError(f"Unknown benchmark aliases: {sorted(unknown)}")
    runs: list[dict[str, Any]] = []
    selection_hashes: set[str] = set()
    prompt_versions: set[str] = set()
    inference_configs: set[str] = set()
    for model in models:
        if model.alias not in package_dirs:
            continue
        summary, selection_hash, prompt_version, inference_config = _run_summary(
            model, Path(package_dirs[model.alias])
        )
        runs.append(summary)
        selection_hashes.add(selection_hash)
        prompt_versions.add(prompt_version)
        inference_configs.add(inference_config)
    if len(runs) < 2:
        raise ValueError("At least two teacher packages are required")
    if len(selection_hashes) != 1:
        raise ValueError("Teacher packages must use the same source selection")
    if len(prompt_versions) != 1:
        raise ValueError("Teacher packages must use the same prompt version")
    if len(inference_configs) != 1:
        raise ValueError("Teacher packages must use the same inference config")

    missing_required = sorted(
        model.alias
        for model in models
        if model.required_for_final and model.alias not in package_dirs
    )
    return {
        "schema_version": "domain-teacher-comparison-v0.1",
        "benchmark_id": benchmark_id,
        "claims_boundary": (
            "Validator acceptance, coverage, tokens, and latency are operational "
            "metrics. Scientific accuracy ranking requires a shared, source-first "
            "human gold set that is independent of every candidate model."
        ),
        "comparability": {
            "same_source_selection": True,
            "same_prompt_version": True,
            "same_inference_config": True,
            "source_selection_sha256": next(iter(selection_hashes)),
            "prompt_version": next(iter(prompt_versions)),
            "missing_required_models": missing_required,
            "final_matrix_complete": not missing_required,
        },
        "scientific_ranking": _shared_gold_ranking(
            runs, shared_gold_scores
        ),
        "runs": runs,
    }
