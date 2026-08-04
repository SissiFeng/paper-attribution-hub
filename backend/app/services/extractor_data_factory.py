"""Budgeted, auditable optimization loop for structured extractors.

The factory is deliberately trainer-agnostic. A benchmark profile pins the
data, schema, ontology, prompt, model configuration, metric gates, and five
reviewed command adapters:

    generate/select data -> train LoRA -> infer -> verify -> analyze

Commands run without a shell and receive only step-scoped paths. In particular,
the generation and training steps are not given the held-out benchmark path.
Every generated training set is still checked for identity, content, split, and
lineage leakage before training starts.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import shutil
import string
import subprocess
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Protocol

import yaml

from app.services.extractor_factory_validation import (
    audit_structured_records,
    require_structured_records,
)
from app.services.extractor_system_validation import (
    EffectivenessPolicy,
    audit_effectiveness_benchmark,
    evaluate_system_effectiveness,
)


class FactoryError(RuntimeError):
    """Base error for a failed or invalid factory run."""


class ProfileError(FactoryError):
    """The benchmark profile is incomplete or unsafe."""


class StepExecutionError(FactoryError):
    """An external generation, training, evaluation, or analysis step failed."""


class BudgetExhausted(FactoryError):
    def __init__(self, reason: str):
        super().__init__(reason.replace("_", " "))
        self.reason = reason


@dataclass(frozen=True)
class FactoryInputs:
    seed_train: Path
    benchmark_test: Path
    extraction_schema: Path
    ontology_version: Path
    prompt_version: Path
    model_config: Path


@dataclass(frozen=True)
class BoundaryPolicy:
    identity_fields: tuple[str, ...]
    content_fields: tuple[str, ...]
    provenance_kind_field: str
    source_split_field: str
    source_record_ids_field: str
    allowed_provenance_kinds: tuple[str, ...]
    trusted_root_kinds: tuple[str, ...]
    generated_kinds: tuple[str, ...]
    record_id_field: str = "record_id"
    near_duplicate_threshold: float = 0.92


@dataclass(frozen=True)
class FactoryBudget:
    max_attempts: int
    max_wall_clock_seconds: float
    max_cost_usd: float
    max_tokens: int
    max_human_review_records: int
    max_training_records: int


@dataclass(frozen=True)
class MetricGate:
    metric: str
    operator: str
    value: float


@dataclass(frozen=True)
class TieBreaker:
    metric: str
    direction: str


@dataclass(frozen=True)
class SelectionPolicy:
    primary_metric: str
    direction: str
    gates: tuple[MetricGate, ...]
    tie_breakers: tuple[TieBreaker, ...]


@dataclass(frozen=True)
class FactoryCommands:
    generate: tuple[str, ...]
    train_lora: tuple[str, ...]
    evaluate: tuple[str, ...]
    verify: tuple[str, ...]
    analyze: tuple[str, ...]


@dataclass(frozen=True)
class ExecutionPolicy:
    allowed_executables: tuple[str, ...]
    allowed_python_module_prefixes: tuple[str, ...]


@dataclass(frozen=True)
class FactoryProfile:
    source_path: Path
    profile_version: str
    profile_id: str
    inputs: FactoryInputs
    boundary: BoundaryPolicy
    budget: FactoryBudget
    effectiveness: EffectivenessPolicy
    selection: SelectionPolicy
    execution: ExecutionPolicy
    commands: FactoryCommands
    working_directory: Path

    def with_budget(self, **changes) -> "FactoryProfile":
        """Return a test/CLI override without mutating the frozen profile."""
        return replace(self, budget=replace(self.budget, **changes))


class StepExecutor(Protocol):
    def run(
        self,
        step: str,
        command: list[str],
        context: dict[str, str],
        timeout_seconds: float,
    ) -> None: ...


_ALLOWED_PLACEHOLDERS = {
    "generate": {
        "attempt_dir",
        "attempt_number",
        "train_records",
        "seed_train",
        "previous_train_records",
        "previous_error_analysis",
        "extraction_schema",
        "ontology_version",
        "prompt_version",
        "model_config",
        "cost",
        "step_usage",
        "usage_nonce",
        "remaining_cost_usd",
        "remaining_tokens",
        "remaining_human_review_records",
        "remaining_wall_clock_seconds",
    },
    "train_lora": {
        "attempt_dir",
        "attempt_number",
        "train_records",
        "checkpoint_dir",
        "extraction_schema",
        "ontology_version",
        "prompt_version",
        "model_config",
        "cost",
        "step_usage",
        "usage_nonce",
        "remaining_cost_usd",
        "remaining_tokens",
        "remaining_human_review_records",
        "remaining_wall_clock_seconds",
    },
    "evaluate": {
        "attempt_dir",
        "attempt_number",
        "benchmark_inputs",
        "checkpoint_dir",
        "checkpoint_sha256",
        "predictions",
        "predictions_sha256",
        "extraction_schema",
        "ontology_version",
        "cost",
        "step_usage",
        "usage_nonce",
        "evaluation_profile_sha256",
        "remaining_cost_usd",
        "remaining_tokens",
        "remaining_human_review_records",
        "remaining_wall_clock_seconds",
    },
    "verify": {
        "attempt_dir",
        "attempt_number",
        "benchmark_test",
        "checkpoint_sha256",
        "predictions",
        "predictions_sha256",
        "verification_records",
        "verification_records_sha256",
        "metrics",
        "extraction_schema",
        "ontology_version",
        "cost",
        "step_usage",
        "usage_nonce",
        "evaluation_profile_sha256",
        "remaining_cost_usd",
        "remaining_tokens",
        "remaining_human_review_records",
        "remaining_wall_clock_seconds",
    },
    "analyze": {
        "attempt_dir",
        "attempt_number",
        "predictions",
        "predictions_sha256",
        "verification_records",
        "metrics",
        "error_analysis",
        "cost",
        "step_usage",
        "usage_nonce",
        "remaining_cost_usd",
        "remaining_tokens",
        "remaining_human_review_records",
        "remaining_wall_clock_seconds",
    },
}
_SYSTEM_EXECUTABLE_ALLOWLIST = {"python", "python3"}
_SYSTEM_PYTHON_MODULE_PREFIXES = (
    "pas_factory_adapters.",
)
_SAFE_IDENTITY_FIELDS = frozenset({"record_id", "paper_id", "chunk_id"})
_SAFE_CONTENT_FIELDS = frozenset({"input_text", "context_chunks"})
_MAX_NEAR_DUPLICATE_THRESHOLD = 0.92
_BLOCKED_ENVIRONMENT_NAMES = frozenset(
    {
        "PATH",
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "PYTHONINSPECT",
        "PYTHONUSERBASE",
        "VIRTUAL_ENV",
        "__PYVENV_LAUNCHER__",
        "LD_PRELOAD",
    }
)
_COMMAND_TAIL_SCHEMAS = {
    "generate": (
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
    ),
    "train_lora": (
        "--train",
        "{train_records}",
        "--model-config",
        "{model_config}",
        "--out",
        "{checkpoint_dir}",
    ),
    "evaluate": (
        "--checkpoint",
        "{checkpoint_dir}",
        "--benchmark",
        "{benchmark_inputs}",
        "--checkpoint-sha256",
        "{checkpoint_sha256}",
        "--predictions-out",
        "{predictions}",
    ),
    "verify": (
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
    ),
    "analyze": (
        "--predictions",
        "{predictions}",
        "--metrics",
        "{metrics}",
        "--verification-records",
        "{verification_records}",
        "--out",
        "{error_analysis}",
    ),
}
_RELEASE_GATE_LIMITS = {
    "system.overall_accuracy": ("minimum", 0.75),
    "system.hard_negative_claim_false_positive_rate": ("maximum", 0.05),
    "system.counterfactual_pair_accuracy": ("minimum", 0.8),
    "system.counterfactual_sensitivity": ("minimum", 0.8),
    "system.cross_domain_transfer_accuracy": ("minimum", 0.7),
    "system.worst_domain_accuracy": ("minimum", 0.7),
    "system.verifier_gold_exact_agreement": ("minimum", 0.8),
}


class SubprocessStepExecutor:
    """Run profile commands as argv lists, never through a shell."""

    def __init__(
        self,
        working_directory: Path,
        execution_policy: ExecutionPolicy,
        commands: FactoryCommands,
        pass_environment: tuple[str, ...] = (),
    ):
        self.working_directory = working_directory
        self.execution_policy = execution_policy
        self.adapter_digests = _resolve_adapter_digests(commands)
        self.pass_environment = pass_environment

    def run(
        self,
        step: str,
        command: list[str],
        context: dict[str, str],
        timeout_seconds: float,
    ) -> None:
        module = command[2]
        observed = _resolve_python_module(module)
        if observed != self.adapter_digests.get(module):
            raise StepExecutionError(
                f"Reviewed adapter changed before {step}: {module}"
            )
        inherited_names = {
            "TMPDIR",
            "LANG",
            "LC_ALL",
            "CUDA_VISIBLE_DEVICES",
            *self.pass_environment,
        }
        env = {
            name: value
            for name in inherited_names
            if (value := os.environ.get(name)) is not None
        }
        env["PATH"] = str(Path(sys.executable).parent)
        for key, value in context.items():
            env[f"PAS_FACTORY_{key.upper()}"] = value
        if command[0] not in {"python", "python3"}:
            raise StepExecutionError("Factory adapters must use the Python runtime.")
        command = [sys.executable, "-I", *command[1:]]
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=self.working_directory,
                env=env,
                text=True,
                capture_output=True,
                check=False,
                timeout=max(0.1, timeout_seconds),
            )
        except subprocess.TimeoutExpired as exc:
            raise StepExecutionError(
                f"{step} exceeded its remaining wall-clock budget"
            ) from exc

        elapsed = round(time.monotonic() - started, 3)
        log_path = Path(context["attempt_dir"]) / f"{step}.log"
        secret_values = [
            env[name] for name in self.pass_environment if name in env
        ]
        log_path.write_text(
            json.dumps(
                {
                    "command": [
                        _redact(value, secret_values) for value in command
                    ],
                    "returncode": completed.returncode,
                    "elapsed_seconds": elapsed,
                    "stdout": _redact(completed.stdout, secret_values),
                    "stderr": _redact(completed.stderr, secret_values),
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        if completed.returncode != 0:
            raise StepExecutionError(
                f"{step} failed with exit code {completed.returncode}; see {log_path}"
            )


def load_factory_profile(path: str | Path) -> FactoryProfile:
    """Load and fully validate a benchmark-specific factory profile."""
    source_path = Path(path).resolve()
    raw = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ProfileError("Factory profile must be a YAML object.")
    if raw.get("profile_version") != "structured-extractor-factory.v1":
        raise ProfileError(
            "profile_version must be 'structured-extractor-factory.v1'."
        )
    profile_id = _required_string(raw, "profile_id")
    base = source_path.parent

    inputs_raw = _required_mapping(raw, "inputs")
    inputs = FactoryInputs(
        **{
            name: _existing_path(base, _required_string(inputs_raw, name), name)
            for name in (
                "seed_train",
                "benchmark_test",
                "extraction_schema",
                "ontology_version",
                "prompt_version",
                "model_config",
            )
        }
    )
    _validate_input_roles(inputs)

    boundary_raw = _required_mapping(raw, "boundary")
    boundary = BoundaryPolicy(
        identity_fields=_required_string_tuple(boundary_raw, "identity_fields"),
        content_fields=_required_string_tuple(boundary_raw, "content_fields"),
        provenance_kind_field=_required_string(
            boundary_raw, "provenance_kind_field"
        ),
        source_split_field=_required_string(boundary_raw, "source_split_field"),
        source_record_ids_field=_required_string(
            boundary_raw, "source_record_ids_field"
        ),
        allowed_provenance_kinds=_required_string_tuple(
            boundary_raw, "allowed_provenance_kinds"
        ),
        trusted_root_kinds=_required_string_tuple(
            boundary_raw, "trusted_root_kinds"
        ),
        generated_kinds=_required_string_tuple(boundary_raw, "generated_kinds"),
        record_id_field=str(boundary_raw.get("record_id_field") or "record_id"),
        near_duplicate_threshold=_unit_interval(
            boundary_raw.get("near_duplicate_threshold", 0.92),
            "boundary.near_duplicate_threshold",
        ),
    )
    if (
        set(boundary.identity_fields) != _SAFE_IDENTITY_FIELDS
        or not set(boundary.content_fields) <= _SAFE_CONTENT_FIELDS
        or "input_text" not in boundary.content_fields
        or boundary.record_id_field != "record_id"
        or boundary.near_duplicate_threshold
        > _MAX_NEAR_DUPLICATE_THRESHOLD
    ):
        raise ProfileError(
            "boundary must audit record_id, paper_id, chunk_id, and input_text; "
            "may additionally audit context_chunks; must use record_id as the "
            "record ID; and cannot weaken near_duplicate_threshold above "
            f"{_MAX_NEAR_DUPLICATE_THRESHOLD}."
        )
    if not set(boundary.trusted_root_kinds) <= set(
        boundary.allowed_provenance_kinds
    ):
        raise ProfileError("trusted_root_kinds must be allowed provenance kinds.")
    if not set(boundary.generated_kinds) <= set(boundary.allowed_provenance_kinds):
        raise ProfileError("generated_kinds must be allowed provenance kinds.")

    budget_raw = _required_mapping(raw, "budget")
    budget = FactoryBudget(
        max_attempts=_positive_int(budget_raw, "max_attempts"),
        max_wall_clock_seconds=_positive_number(
            budget_raw, "max_wall_clock_seconds"
        ),
        max_cost_usd=_positive_number(budget_raw, "max_cost_usd"),
        max_tokens=_positive_int(budget_raw, "max_tokens"),
        max_human_review_records=_positive_int(
            budget_raw, "max_human_review_records"
        ),
        max_training_records=_positive_int(budget_raw, "max_training_records"),
    )

    effectiveness_raw = _required_mapping(raw, "effectiveness")
    benchmark_tier = effectiveness_raw.get("benchmark_tier")
    if benchmark_tier not in {"smoke", "release"}:
        raise ProfileError(
            "effectiveness.benchmark_tier must be smoke or release."
        )
    effectiveness = EffectivenessPolicy(
        benchmark_tier=str(benchmark_tier),
        required_case_types=_required_string_tuple(
            effectiveness_raw,
            "required_case_types",
        ),
        min_records_per_case=_positive_int(
            effectiveness_raw,
            "min_records_per_case",
        ),
        min_domains=_positive_int(effectiveness_raw, "min_domains"),
    )

    selection_raw = _required_mapping(raw, "selection")
    direction = _direction(selection_raw.get("direction"), "selection.direction")
    gates = tuple(
        MetricGate(
            metric=_required_string(gate, "metric"),
            operator=_operator(gate.get("operator")),
            value=_finite_number(
                gate.get("value"),
                "selection.gates.value",
            ),
        )
        for gate in _mapping_list(selection_raw.get("gates"), "selection.gates")
    )
    tie_breakers = tuple(
        TieBreaker(
            metric=_required_string(item, "metric"),
            direction=_direction(
                item.get("direction"), "selection.tie_breakers.direction"
            ),
        )
        for item in _mapping_list(
            selection_raw.get("tie_breakers", []),
            "selection.tie_breakers",
        )
    )
    selection = SelectionPolicy(
        primary_metric=_required_string(selection_raw, "primary_metric"),
        direction=direction,
        gates=gates,
        tie_breakers=tie_breakers,
    )
    _validate_release_effectiveness_gates(effectiveness, selection)

    execution_raw = _required_mapping(raw, "execution")
    execution = ExecutionPolicy(
        allowed_executables=_required_string_tuple(
            execution_raw, "allowed_executables"
        ),
        allowed_python_module_prefixes=_required_string_tuple(
            execution_raw, "allowed_python_module_prefixes"
        ),
    )
    commands_raw = _required_mapping(raw, "commands")
    commands = FactoryCommands(
        generate=_command(commands_raw, "generate"),
        train_lora=_command(commands_raw, "train_lora"),
        evaluate=_command(commands_raw, "evaluate"),
        verify=_command(commands_raw, "verify"),
        analyze=_command(commands_raw, "analyze"),
    )
    for step in ("generate", "train_lora", "evaluate", "verify", "analyze"):
        command = getattr(commands, step)
        if command:
            _validate_placeholders(step, command)
            _validate_command_policy(step, command, execution)
    for step in ("generate", "train_lora", "evaluate"):
        command = getattr(commands, step)
        if any(
            str(inputs.benchmark_test) in argument
            or Path(argument).name == inputs.benchmark_test.name
            for argument in command
        ):
            raise ProfileError(
                f"{step} command must not receive or name the benchmark test set."
            )

    working_directory_raw = str(raw.get("working_directory") or ".")
    working_directory = (base / working_directory_raw).resolve()
    if not working_directory.is_dir():
        raise ProfileError(
            f"working_directory does not exist: {working_directory}"
        )
    trusted_root = _profile_trusted_root(source_path)
    if not working_directory.is_relative_to(trusted_root):
        raise ProfileError(
            "working_directory must stay inside the profile's trusted project "
            f"root: {trusted_root}"
        )
    return FactoryProfile(
        source_path=source_path,
        profile_version=raw["profile_version"],
        profile_id=profile_id,
        inputs=inputs,
        boundary=boundary,
        budget=budget,
        effectiveness=effectiveness,
        selection=selection,
        execution=execution,
        commands=commands,
        working_directory=working_directory,
    )


def audit_training_boundary(
    train_path: str | Path,
    benchmark_path: str | Path,
    trusted_train_path: str | Path,
    policy: BoundaryPolicy,
) -> dict:
    """Fail closed on direct benchmark leakage and unverifiable synthesis."""
    train_rows = _read_jsonl(Path(train_path))
    benchmark_rows = _read_jsonl(Path(benchmark_path))
    trusted_rows = _read_jsonl(Path(trusted_train_path))
    violations: list[dict] = []
    if not train_rows:
        violations.append({"code": "empty_training_data"})
    if not benchmark_rows:
        violations.append({"code": "empty_benchmark"})

    trusted_root_rows = {
        str(_field(row, policy.record_id_field)): _content_hash(row)
        for row in trusted_rows
        if _field(row, policy.provenance_kind_field) in policy.trusted_root_kinds
        and _field(row, policy.record_id_field) not in (None, "")
    }
    trusted_root_ids = set(trusted_root_rows)
    benchmark_record_ids: set[str] = set()
    benchmark_content_hashes: set[str] = set()
    for index, row in enumerate(benchmark_rows, start=1):
        record_id = _field(row, policy.record_id_field)
        if record_id not in (None, ""):
            stable_id = _stable_value(record_id)
            if stable_id in benchmark_record_ids:
                violations.append(
                    {
                        "code": "duplicate_benchmark_record_id",
                        "record": index,
                        "value": record_id,
                    }
                )
            benchmark_record_ids.add(stable_id)
        for field in policy.content_fields:
            value = _field(row, field)
            if value not in (None, ""):
                content_hash = _content_hash(value)
                if content_hash in benchmark_content_hashes:
                    violations.append(
                        {
                            "code": "duplicate_benchmark_content",
                            "record": index,
                            "field": field,
                        }
                    )
                benchmark_content_hashes.add(content_hash)

    for field in policy.identity_fields:
        test_values = {
            _stable_value(_field(row, field))
            for row in benchmark_rows
            if _field(row, field) not in (None, "")
        }
        for index, row in enumerate(train_rows, start=1):
            value = _field(row, field)
            if value in (None, ""):
                violations.append(
                    {
                        "code": "missing_identity_field",
                        "record": index,
                        "field": field,
                    }
                )
            elif _stable_value(value) in test_values:
                violations.append(
                    {
                        "code": "identity_overlap",
                        "record": index,
                        "field": field,
                        "value": value,
                    }
                )

    benchmark_surfaces = [
        surface
        for row in benchmark_rows
        for surface in _record_text_surfaces(row, policy)
    ]
    benchmark_surface_hashes = {
        _content_hash(text) for _field_name, text in benchmark_surfaces
    }
    benchmark_context_ids = {
        str(chunk_id)
        for row in benchmark_rows
        for chunk_id in _context_chunk_ids(row)
    }
    benchmark_context_ids.update(
        str(value)
        for row in benchmark_rows
        for field in policy.identity_fields
        if field.rsplit(".", 1)[-1] == "chunk_id"
        if (value := _field(row, field)) not in (None, "")
    )
    for index, row in enumerate(train_rows, start=1):
        for field in policy.content_fields:
            if _field(row, field) in (None, ""):
                violations.append(
                    {
                        "code": "missing_content_field",
                        "record": index,
                        "field": field,
                    }
                )
        context_chunks = row.get("context_chunks")
        if context_chunks is not None and (
            not isinstance(context_chunks, dict)
            or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in context_chunks.items()
            )
        ):
            violations.append(
                {"code": "invalid_context_chunks", "record": index}
            )
        overlapping_context_ids = sorted(
            set(_context_chunk_ids(row)) & benchmark_context_ids
        )
        if overlapping_context_ids:
            violations.append(
                {
                    "code": "context_chunk_identity_overlap",
                    "record": index,
                    "chunk_ids": overlapping_context_ids,
                }
            )
        for field, value in _record_text_surfaces(row, policy):
            if _content_hash(value) in benchmark_surface_hashes:
                violations.append(
                    {
                        "code": "content_overlap",
                        "record": index,
                        "field": field,
                        "sha256": _content_hash(value),
                    }
                )
            else:
                closest = max(
                    (
                        _near_duplicate_similarity(value, test_text)
                        for _test_field, test_text in benchmark_surfaces
                    ),
                    default=0.0,
                )
                if closest >= policy.near_duplicate_threshold:
                    violations.append(
                        {
                            "code": "near_content_overlap",
                            "record": index,
                            "field": field,
                            "similarity": round(closest, 4),
                            "threshold": policy.near_duplicate_threshold,
                        }
                    )

    seen_record_ids: set[str] = set()
    for index, row in enumerate(train_rows, start=1):
        record_id = _field(row, policy.record_id_field)
        if record_id in (None, ""):
            violations.append({"code": "missing_record_id", "record": index})
        elif str(record_id) in seen_record_ids:
            violations.append(
                {
                    "code": "duplicate_record_id",
                    "record": index,
                    "value": record_id,
                }
            )
        else:
            seen_record_ids.add(str(record_id))

        split = _field(row, policy.source_split_field)
        if split != "train":
            violations.append(
                {
                    "code": "invalid_source_split",
                    "record": index,
                    "value": split,
                }
            )

        kind = _field(row, policy.provenance_kind_field)
        if kind not in policy.allowed_provenance_kinds:
            violations.append(
                {
                    "code": "invalid_provenance_kind",
                    "record": index,
                    "value": kind,
                }
            )
        if kind in policy.generated_kinds:
            if str(record_id) in trusted_root_ids:
                violations.append(
                    {
                        "code": "generated_record_reuses_trusted_root_id",
                        "record": index,
                        "value": record_id,
                    }
                )
            source_ids = _field(row, policy.source_record_ids_field)
            if not isinstance(source_ids, list) or not source_ids:
                violations.append(
                    {"code": "missing_generated_lineage", "record": index}
                )
            else:
                if len({str(source_id) for source_id in source_ids}) != len(
                    source_ids
                ):
                    violations.append(
                        {
                            "code": "duplicate_generated_lineage",
                            "record": index,
                        }
                    )
                untrusted = sorted(
                    str(source_id)
                    for source_id in source_ids
                    if str(source_id) not in trusted_root_ids
                )
                if untrusted:
                    violations.append(
                        {
                            "code": "untrusted_lineage",
                            "record": index,
                            "source_record_ids": untrusted,
                        }
                    )
        if kind in policy.trusted_root_kinds and record_id not in (None, ""):
            expected_hash = trusted_root_rows.get(str(record_id))
            if expected_hash is None:
                violations.append(
                    {
                        "code": "new_trusted_root",
                        "record": index,
                        "value": record_id,
                    }
                )
            elif _content_hash(row) != expected_hash:
                violations.append(
                    {
                        "code": "mutated_trusted_root",
                        "record": index,
                        "value": record_id,
                    }
                )

    for index, row in enumerate(benchmark_rows, start=1):
        context_chunks = row.get("context_chunks")
        if context_chunks is not None and (
            not isinstance(context_chunks, dict)
            or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in context_chunks.items()
            )
        ):
            violations.append(
                {"code": "benchmark_invalid_context_chunks", "record": index}
            )
        for field in policy.identity_fields:
            if _field(row, field) in (None, ""):
                violations.append(
                    {
                        "code": "benchmark_missing_identity_field",
                        "record": index,
                        "field": field,
                    }
                )
        for field in policy.content_fields:
            if _field(row, field) in (None, ""):
                violations.append(
                    {
                        "code": "benchmark_missing_content_field",
                        "record": index,
                        "field": field,
                    }
                )
        if _field(row, policy.source_split_field) != "test":
            violations.append(
                {
                    "code": "invalid_benchmark_source_split",
                    "record": index,
                    "value": _field(row, policy.source_split_field),
                }
            )

    return {
        "passed": not violations,
        "train_records": len(train_rows),
        "benchmark_records": len(benchmark_rows),
        "trusted_root_records": len(trusted_root_ids),
        "identity_fields": list(policy.identity_fields),
        "content_fields": list(policy.content_fields),
        "train_sha256": _sha256_file(Path(train_path)),
        "benchmark_sha256": _sha256_file(Path(benchmark_path)),
        "violations": violations,
    }


def validate_factory_profile(
    profile: FactoryProfile,
    *,
    adapter_digests: dict[str, dict[str, str]] | None = None,
) -> dict:
    """Validate the immutable inputs and initial train/test boundary."""
    boundary_report = audit_training_boundary(
        profile.inputs.seed_train,
        profile.inputs.benchmark_test,
        profile.inputs.seed_train,
        profile.boundary,
    )
    hashes = _input_hashes(profile.inputs)
    seed_contract = audit_structured_records(
        profile.inputs.seed_train,
        payload_field="target",
        schema_path=profile.inputs.extraction_schema,
        ontology_path=profile.inputs.ontology_version,
    )
    benchmark_contract = audit_structured_records(
        profile.inputs.benchmark_test,
        payload_field="target",
        schema_path=profile.inputs.extraction_schema,
        ontology_path=profile.inputs.ontology_version,
    )
    system_effectiveness = audit_effectiveness_benchmark(
        profile.inputs.benchmark_test,
        profile.effectiveness,
    )
    return {
        "profile_id": profile.profile_id,
        "profile_version": profile.profile_version,
        "input_hashes": hashes,
        "evaluation_profile_sha256": _evaluation_profile_hash(
            profile,
            hashes,
            adapter_digests or {},
        ),
        "boundary": boundary_report,
        "structured_contract": {
            "seed_train": seed_contract,
            "benchmark_test": benchmark_contract,
        },
        "system_effectiveness": system_effectiveness,
        "valid": (
            boundary_report["passed"]
            and seed_contract["passed"]
            and benchmark_contract["passed"]
            and system_effectiveness["passed"]
        ),
    }


def _empty_totals() -> dict:
    return {
        "cost_usd": 0.0,
        "tokens": 0,
        "human_review_records": 0,
        "usage_complete": True,
        "wall_clock_seconds": 0.0,
    }


def _load_resumable_run(
    profile: FactoryProfile,
    run_path: Path,
    hashes: dict[str, str],
    evaluation_hash: str,
    adapter_digests: dict[str, dict[str, str]],
    pass_environment: tuple[str, ...],
) -> tuple[datetime, dict, list[dict], Path, Path | None, int]:
    if not run_path.is_dir():
        raise FactoryError(f"Resume directory does not exist: {run_path}")
    snapshot = run_path / "benchmark_profile.yaml"
    manifest_path = run_path / "benchmark_manifest.json"
    state_path = run_path / "run_state.json"
    if not snapshot.is_file() or not manifest_path.is_file() or not state_path.is_file():
        raise FactoryError("Resume directory is missing frozen run metadata.")
    manifest = _read_json(manifest_path)
    state = _read_json(state_path)
    if (
        manifest.get("profile_id") != profile.profile_id
        or manifest.get("source_profile_sha256")
        != _sha256_file(profile.source_path)
        or manifest.get("evaluation_profile_sha256") != evaluation_hash
        or manifest.get("adapter_digests") != adapter_digests
        or manifest.get("input_hashes") != hashes
        or manifest.get("passed_environment_names")
        != sorted(set(pass_environment))
    ):
        raise FactoryError("Current frozen inputs do not match the interrupted run.")

    try:
        started_at = datetime.fromisoformat(str(manifest["started_at"]))
    except (KeyError, ValueError) as exc:
        raise FactoryError("benchmark_manifest.json has no valid started_at.") from exc

    totals = _empty_totals()
    attempts: list[dict] = []
    previous_train = profile.inputs.seed_train
    previous_error: Path | None = None
    attempt_dirs = sorted(run_path.glob("attempt_[0-9][0-9][0-9]"))
    for attempt_dir in attempt_dirs:
        attempt_manifest = attempt_dir / "attempt_manifest.json"
        if attempt_manifest.is_file():
            summary = _read_json(attempt_manifest)
            if summary.get("status") == "completed":
                _revalidate_completed_attempt(
                    profile,
                    attempt_dir,
                    summary,
                    hashes,
                    evaluation_hash,
                )
            else:
                _revalidate_noncompleted_attempt(
                    attempt_dir,
                    summary,
                )
        else:
            attempt_number = int(attempt_dir.name.rsplit("_", 1)[1])
            active_step = state.get("step")
            expected_nonce = state.get("usage_nonce")
            expected_nonces = state.get("usage_nonces")
            attempt_started_at = state.get("attempt_started_at")
            if (
                state.get("status") != "running"
                or state.get("attempt_number") != attempt_number
                or active_step
                not in {
                    "generate",
                    "train_lora",
                    "evaluate",
                    "verify",
                    "analyze",
                }
                or state.get("step_status")
                not in {"running", "completed", "failed"}
                or not isinstance(expected_nonce, str)
                or not isinstance(expected_nonces, dict)
                or not isinstance(attempt_started_at, str)
            ):
                raise FactoryError(
                    f"{attempt_dir.name} has no reconcilable active-step state; "
                    "spend is unknown and the run cannot safely resume."
                )
            step_order = [
                "generate",
                "train_lora",
                "evaluate",
                "verify",
                "analyze",
            ]
            active_index = step_order.index(active_step)
            usage_paths = {
                path.stem: path
                for path in (attempt_dir / "usage").glob("*.json")
            }
            expected_steps = step_order[: active_index + 1]
            if (
                set(expected_nonces) != set(expected_steps)
                or expected_nonces.get(active_step) != expected_nonce
                or any(
                    not isinstance(expected_nonces.get(step), str)
                    or not expected_nonces[step]
                    for step in expected_steps
                )
            ):
                raise FactoryError(
                    f"{attempt_dir.name} has no complete nonce ledger through "
                    f"active step {active_step}."
                )
            if set(usage_paths) != set(expected_steps):
                raise FactoryError(
                    f"{attempt_dir.name} does not have an exact usage ledger "
                    f"through active step {active_step}; spend is unknown."
                )
            usage = [
                {
                    "step": step,
                    "usage_complete": True,
                    **_load_step_usage(
                        usage_paths[step],
                        expected_nonce=expected_nonces[step],
                    ),
                }
                for step in expected_steps
            ]
            try:
                interrupted_started = datetime.fromisoformat(
                    attempt_started_at
                )
                now = datetime.now(UTC)
                if interrupted_started > now:
                    raise ValueError("attempt_started_at is in the future")
                interrupted_wall_seconds = max(
                    0.0,
                    (now - interrupted_started).total_seconds(),
                )
            except (TypeError, ValueError) as exc:
                raise FactoryError(
                    f"{attempt_dir.name} has no valid attempt start time; "
                    "wall-clock spend is unknown."
                ) from exc
            cost = _attempt_cost(usage, time.monotonic())
            cost["wall_clock_seconds"] = round(
                interrupted_wall_seconds,
                3,
            )
            _write_json(attempt_dir / "cost.json", cost)
            summary = {
                "attempt_id": attempt_dir.name,
                "attempt_number": attempt_number,
                "status": "interrupted",
                "eligible": False,
                "rejection_reasons": [
                    "Interrupted attempt was preserved and not reused."
                ],
                "cost": cost,
                "cost_sha256": _sha256_file(attempt_dir / "cost.json"),
                "usage_sha256": {
                    step: _sha256_file(usage_paths[step])
                    for step in expected_steps
                },
                "usage_nonces": {
                    step: expected_nonces[step]
                    for step in expected_steps
                },
            }
            _write_json(attempt_manifest, summary)
            _append_jsonl(run_path / "trajectory.jsonl", summary)
        cost = summary.get("cost")
        if not isinstance(cost, dict) and (attempt_dir / "cost.json").is_file():
            cost = _read_json(attempt_dir / "cost.json")
        if not isinstance(cost, dict) or not cost.get("usage_complete"):
            raise FactoryError(
                f"{attempt_dir.name} has incomplete usage; the run cannot resume."
            )
        _apply_usage(totals, cost)
        totals["wall_clock_seconds"] += float(cost.get("wall_clock_seconds") or 0.0)
        attempts.append(summary)
        if summary.get("status") == "completed":
            previous_train = attempt_dir / "train_records.jsonl"
            previous_error = attempt_dir / "error_analysis.json"

    first_attempt = (
        max((int(path.name.rsplit("_", 1)[1]) for path in attempt_dirs), default=0)
        + 1
    )
    return (
        started_at,
        totals,
        attempts,
        previous_train,
        previous_error,
        first_attempt,
    )


def _revalidate_completed_attempt(
    profile: FactoryProfile,
    attempt_dir: Path,
    summary: dict,
    input_hashes: dict[str, str],
    evaluation_hash: str,
) -> None:
    paths = _attempt_paths(attempt_dir)
    artifact_hashes = summary.get("artifacts_sha256")
    if not isinstance(artifact_hashes, dict):
        raise FactoryError(
            f"{attempt_dir.name} has no complete artifact digest ledger."
        )
    observed_artifacts = _completed_artifact_hashes(paths)
    if observed_artifacts != artifact_hashes:
        raise FactoryError(
            f"{attempt_dir.name} audit artifacts changed after completion."
        )

    usage_hashes = summary.get("usage_sha256")
    usage_nonces = summary.get("usage_nonces")
    step_order = ("generate", "train_lora", "evaluate", "verify", "analyze")
    if (
        not isinstance(usage_hashes, dict)
        or not isinstance(usage_nonces, dict)
        or set(usage_hashes) != set(step_order)
        or set(usage_nonces) != set(step_order)
    ):
        raise FactoryError(
            f"{attempt_dir.name} has no complete usage digest ledger."
        )
    usage = []
    for step in step_order:
        path = attempt_dir / "usage" / f"{step}.json"
        if not path.is_file() or _sha256_file(path) != usage_hashes[step]:
            raise FactoryError(
                f"{attempt_dir.name} usage ledger changed for {step}."
            )
        usage.append(
            {
                "step": step,
                "usage_complete": True,
                **_load_step_usage(
                    path,
                    expected_nonce=usage_nonces[step],
                ),
            }
        )
    persisted_cost = _read_json(paths["cost"])
    recomputed = {
        "usage_complete": True,
        "cost_usd": round(sum(entry["cost_usd"] for entry in usage), 6),
        "tokens": sum(entry["tokens"] for entry in usage),
        "human_review_records": sum(
            entry["human_review_records"] for entry in usage
        ),
        "training_seconds": round(
            sum(entry["training_seconds"] for entry in usage),
            3,
        ),
        "steps": usage,
    }
    for field, value in recomputed.items():
        if persisted_cost.get(field) != value:
            raise FactoryError(
                f"{attempt_dir.name} cost ledger does not reconcile: {field}."
            )
    if summary.get("cost") != persisted_cost:
        raise FactoryError(
            f"{attempt_dir.name} manifest cost does not match cost.json."
        )

    train_hash = summary.get("train_records_sha256")
    if not isinstance(train_hash, str):
        raise FactoryError(
            f"{attempt_dir.name} has no training-data digest."
        )
    _assert_frozen_inputs(
        profile,
        paths,
        input_hashes,
        train_hash,
    )
    require_structured_records(
        paths["train_records"],
        payload_field="target",
        schema_path=paths["extraction_schema"],
        ontology_path=paths["ontology_version"],
    )
    boundary = audit_training_boundary(
        paths["train_records"],
        profile.inputs.benchmark_test,
        profile.inputs.seed_train,
        profile.boundary,
    )
    if not boundary["passed"] or boundary["train_sha256"] != train_hash:
        raise FactoryError(
            f"{attempt_dir.name} no longer passes the training-data boundary."
        )
    if _read_json(paths["data_lineage"]) != _lineage_summary(
        paths["train_records"],
        profile.boundary,
        profile.inputs.seed_train,
    ):
        raise FactoryError(
            f"{attempt_dir.name} data lineage no longer matches training records."
        )

    checkpoint_hash = summary.get("checkpoint_sha256")
    if not isinstance(checkpoint_hash, str):
        raise FactoryError(
            f"{attempt_dir.name} has no checkpoint digest."
        )
    _assert_checkpoint(paths["checkpoint_dir"], checkpoint_hash)
    predictions_hash = _sha256_file(paths["predictions"])
    verification_hash = _sha256_file(paths["verification_records"])
    metrics_hash = _sha256_file(paths["metrics"])
    if (
        summary.get("predictions_sha256") != predictions_hash
        or summary.get("verification_records_sha256") != verification_hash
        or summary.get("metrics_sha256") != metrics_hash
        or summary.get("evaluation_profile_sha256") != evaluation_hash
    ):
        raise FactoryError(
            f"{attempt_dir.name} manifest digests do not match its artifacts."
        )
    require_structured_records(
        paths["predictions"],
        payload_field="prediction",
        schema_path=paths["extraction_schema"],
        ontology_path=paths["ontology_version"],
    )
    _validate_prediction_coverage(
        paths["predictions"],
        profile.inputs.benchmark_test,
        profile.boundary.record_id_field,
    )
    _validate_verification_records(
        paths["verification_records"],
        profile.inputs.benchmark_test,
        profile.boundary.record_id_field,
    )
    system_effectiveness = evaluate_system_effectiveness(
        profile.inputs.benchmark_test,
        paths["predictions"],
        paths["verification_records"],
        profile.effectiveness,
    )
    if _read_json(paths["system_effectiveness"]) != system_effectiveness:
        raise FactoryError(
            f"{attempt_dir.name} system effectiveness report does not reconcile."
        )
    if (
        summary.get("system_effectiveness_sha256")
        != _sha256_file(paths["system_effectiveness"])
    ):
        raise FactoryError(
            f"{attempt_dir.name} system effectiveness digest does not match."
        )
    _validate_error_analysis(
        paths["error_analysis"],
        paths["verification_records"],
    )
    metrics = _read_json(paths["metrics"])
    if (
        metrics.get("evaluation_profile_sha256") != evaluation_hash
        or metrics.get("checkpoint_sha256") != checkpoint_hash
        or metrics.get("predictions_sha256") != predictions_hash
        or metrics.get("verification_records_sha256") != verification_hash
    ):
        raise FactoryError(
            f"{attempt_dir.name} verifier inputs are not cryptographically linked."
        )
    verifier = _read_json(paths["verifier"])
    if (
        verifier.get("eligible") != summary.get("eligible")
        or verifier.get("primary_metric") != summary.get("primary_metric")
        or verifier.get("tie_breaker_metrics")
        != summary.get("tie_breaker_metrics")
        or verifier.get("system_effectiveness_sha256")
        != _sha256_file(paths["system_effectiveness"])
    ):
        raise FactoryError(
            f"{attempt_dir.name} selection summary does not match verifier.json."
        )


def _revalidate_noncompleted_attempt(
    attempt_dir: Path,
    summary: dict,
) -> None:
    if (
        summary.get("status") not in {"failed", "interrupted"}
        or summary.get("eligible") is not False
    ):
        raise FactoryError(
            f"{attempt_dir.name} has an invalid non-completed status."
        )
    cost_path = attempt_dir / "cost.json"
    usage_dir = attempt_dir / "usage"
    usage_hashes = summary.get("usage_sha256")
    usage_nonces = summary.get("usage_nonces")
    if (
        not cost_path.is_file()
        or not isinstance(usage_hashes, dict)
        or not isinstance(usage_nonces, dict)
        or set(usage_hashes) != set(usage_nonces)
    ):
        raise FactoryError(
            f"{attempt_dir.name} has no auditable failure usage ledger."
        )
    observed_usage_paths = {
        path.stem: path for path in usage_dir.glob("*.json")
    }
    if set(observed_usage_paths) != set(usage_hashes):
        raise FactoryError(
            f"{attempt_dir.name} failure usage ledger changed."
        )
    usage = []
    for step in ("generate", "train_lora", "evaluate", "verify", "analyze"):
        if step not in usage_hashes:
            continue
        path = observed_usage_paths[step]
        if _sha256_file(path) != usage_hashes[step]:
            raise FactoryError(
                f"{attempt_dir.name} usage ledger changed for {step}."
            )
        usage.append(
            {
                "step": step,
                "usage_complete": True,
                **_load_step_usage(
                    path,
                    expected_nonce=usage_nonces[step],
                ),
            }
        )
    persisted_cost = _read_json(cost_path)
    if (
        summary.get("cost_sha256") != _sha256_file(cost_path)
        or summary.get("cost") != persisted_cost
        or persisted_cost.get("steps") != usage
        or persisted_cost.get("cost_usd")
        != round(sum(entry["cost_usd"] for entry in usage), 6)
        or persisted_cost.get("tokens")
        != sum(entry["tokens"] for entry in usage)
        or persisted_cost.get("human_review_records")
        != sum(entry["human_review_records"] for entry in usage)
        or persisted_cost.get("training_seconds")
        != round(sum(entry["training_seconds"] for entry in usage), 3)
    ):
        raise FactoryError(
            f"{attempt_dir.name} failure cost ledger does not reconcile."
        )


def _validate_finished_run(
    profile: FactoryProfile,
    run_path: Path,
    report: dict,
    state: dict,
    started_at: datetime,
    totals: dict,
    attempts: list[dict],
    evaluation_hash: str,
    adapter_digests: dict[str, dict[str, str]],
    pass_environment: tuple[str, ...],
) -> None:
    selected = _select_best(attempts, profile.selection)
    stable_fields = {
        "profile_id": profile.profile_id,
        "profile_version": profile.profile_version,
        "started_at": started_at.isoformat(),
        "evaluation_profile_sha256": evaluation_hash,
        "adapter_digests": adapter_digests,
        "budget": asdict(profile.budget),
        "passed_environment_names": sorted(set(pass_environment)),
        "selected": selected,
        "attempts": attempts,
    }
    if any(report.get(name) != value for name, value in stable_fields.items()):
        raise FactoryError("Finished run manifest does not reconcile.")

    recomputed_cost = {
        name: totals[name]
        for name in (
            "cost_usd",
            "tokens",
            "human_review_records",
            "usage_complete",
        )
    }
    report_totals = report.get("totals")
    if (
        not isinstance(report_totals, dict)
        or any(
            report_totals.get(name) != value
            for name, value in recomputed_cost.items()
        )
    ):
        raise FactoryError("Finished run totals do not reconcile.")
    if (
        state.get("termination_reason") != report.get("termination_reason")
        or state.get("totals") != report_totals
        or state.get("selected") != selected
    ):
        raise FactoryError("Finished run state does not match run_manifest.json.")

    selection_path = run_path / "selection.json"
    expected_selection = {
        "evaluation_profile_sha256": evaluation_hash,
        "adapter_digests": adapter_digests,
        "policy": _selection_dict(profile.selection),
        "selected": selected,
        "candidates": attempts,
    }
    if (
        not selection_path.is_file()
        or _read_json(selection_path) != expected_selection
    ):
        raise FactoryError("Finished run selection report does not reconcile.")


def run_extractor_data_factory(
    profile: FactoryProfile,
    run_dir: str | Path,
    *,
    executor: StepExecutor | None = None,
    resume: bool = False,
    pass_environment: tuple[str, ...] = (),
) -> dict:
    """Run attempts until a fixed attempt, time, token, or cost budget ends."""
    invoked_monotonic = time.monotonic()
    _validate_pass_environment(pass_environment)
    run_path = Path(run_dir).resolve()
    hashes = _input_hashes(profile.inputs)
    if executor is None:
        executor = SubprocessStepExecutor(
            profile.working_directory,
            profile.execution,
            profile.commands,
            pass_environment,
        )
        adapter_digests = executor.adapter_digests
    else:
        adapter_digests = {
            "execution_mode": {
                "origin": "in-process test executor",
                "sha256": "not-applicable",
            }
        }
    evaluation_hash = _evaluation_profile_hash(
        profile,
        hashes,
        adapter_digests,
    )
    validation = validate_factory_profile(
        profile,
        adapter_digests=adapter_digests,
    )
    if not validation["valid"]:
        raise FactoryError(
            "Frozen seed/benchmark inputs failed boundary or structured-contract "
            "validation."
        )

    if resume:
        (
            started_at,
            totals,
            attempts,
            previous_train,
            previous_error,
            first_attempt_number,
        ) = _load_resumable_run(
            profile,
            run_path,
            hashes,
            evaluation_hash,
            adapter_digests,
            pass_environment,
        )
        benchmark_inputs_path = run_path / "benchmark_inputs.jsonl"
        if (
            not benchmark_inputs_path.is_file()
            or _sha256_file(benchmark_inputs_path)
            != _read_json(run_path / "benchmark_manifest.json").get(
                "benchmark_inputs_sha256"
            )
        ):
            raise FactoryError("Frozen benchmark inference inputs changed.")
        run_state = _read_json(run_path / "run_state.json")
        run_manifest_path = run_path / "run_manifest.json"
        if run_state.get("status") == "finished":
            if not run_manifest_path.is_file():
                raise FactoryError("Finished run is missing run_manifest.json.")
            finished = _read_json(run_manifest_path)
            _validate_finished_run(
                profile,
                run_path,
                finished,
                run_state,
                started_at,
                totals,
                attempts,
                evaluation_hash,
                adapter_digests,
                pass_environment,
            )
            return finished
    else:
        run_path.mkdir(parents=True, exist_ok=False)
        _write_profile_snapshot(
            profile.source_path,
            run_path / "benchmark_profile.yaml",
        )
        _write_json(
            run_path / "initial_boundary_report.json",
            validation["boundary"],
        )
        _write_json(
            run_path / "initial_contract_report.json",
            validation["structured_contract"],
        )
        _write_json(
            run_path / "initial_system_effectiveness.json",
            validation["system_effectiveness"],
        )
        started_at = datetime.now(UTC)
        totals = _empty_totals()
        attempts = []
        previous_train = profile.inputs.seed_train
        previous_error = None
        first_attempt_number = 1
        benchmark_inputs_path = run_path / "benchmark_inputs.jsonl"
        _write_jsonl(
            benchmark_inputs_path,
            [
                _benchmark_inference_row(row)
                for row in _read_jsonl(profile.inputs.benchmark_test)
            ],
        )
        _write_json(
            run_path / "benchmark_manifest.json",
            {
                "profile_id": profile.profile_id,
                "source_profile_sha256": _sha256_file(profile.source_path),
                "started_at": started_at.isoformat(),
                "evaluation_profile_sha256": evaluation_hash,
                "adapter_digests": adapter_digests,
                "benchmark_test_sha256": hashes["benchmark_test"],
                "benchmark_inputs_sha256": _sha256_file(
                    benchmark_inputs_path
                ),
                "extraction_schema_sha256": hashes["extraction_schema"],
                "ontology_version_sha256": hashes["ontology_version"],
                "input_hashes": hashes,
                "passed_environment_names": sorted(set(pass_environment)),
                "selection": _selection_dict(profile.selection),
                "effectiveness": asdict(profile.effectiveness),
            },
        )

    started_monotonic = (
        time.monotonic() - totals["wall_clock_seconds"]
        if resume
        else invoked_monotonic
    )
    termination_reason = "attempt_budget_exhausted"
    run_state_path = run_path / "run_state.json"

    for attempt_number in range(
        first_attempt_number,
        profile.budget.max_attempts + 1,
    ):
        reason = _budget_stop_reason(profile.budget, totals, started_monotonic)
        if reason:
            termination_reason = reason
            break
        attempt_id = f"attempt_{attempt_number:03d}"
        attempt_dir = run_path / attempt_id
        attempt_dir.mkdir()
        attempt_started = time.monotonic()
        attempt_started_at = datetime.now(UTC).isoformat()
        attempt_usage: list[dict] = []
        paths = _prepare_attempt(profile.inputs, attempt_dir)
        remaining = _remaining_budget(profile.budget, totals, started_monotonic)
        base_context = {
            "attempt_dir": str(attempt_dir),
            "attempt_number": str(attempt_number),
            "attempt_started_at": attempt_started_at,
            "train_records": str(paths["train_records"]),
            "seed_train": str(profile.inputs.seed_train),
            "previous_train_records": str(previous_train),
            "previous_error_analysis": str(previous_error) if previous_error else "",
            "checkpoint_dir": str(paths["checkpoint_dir"]),
            "checkpoint_sha256": "",
            "benchmark_test": str(profile.inputs.benchmark_test),
            "benchmark_inputs": str(benchmark_inputs_path),
            "predictions": str(paths["predictions"]),
            "predictions_sha256": "",
            "verification_records": str(paths["verification_records"]),
            "verification_records_sha256": "",
            "metrics": str(paths["metrics"]),
            "error_analysis": str(paths["error_analysis"]),
            "extraction_schema": str(paths["extraction_schema"]),
            "ontology_version": str(paths["ontology_version"]),
            "prompt_version": str(paths["prompt_version"]),
            "model_config": str(paths["model_config"]),
            "cost": str(paths["cost"]),
            "evaluation_profile_sha256": evaluation_hash,
            **remaining,
        }
        summary = {
            "attempt_id": attempt_id,
            "attempt_number": attempt_number,
            "status": "running",
            "eligible": False,
            "rejection_reasons": [],
        }
        hard_stop = False
        hard_stop_reason = "attempt_failed"
        try:
            _execute_accounted_step(
                executor,
                "generate",
                profile.commands.generate,
                base_context,
                profile,
                totals,
                attempt_usage,
                run_state_path,
                started_monotonic,
            )
            _require_file(paths["train_records"], "generate")
            require_structured_records(
                paths["train_records"],
                payload_field="target",
                schema_path=paths["extraction_schema"],
                ontology_path=paths["ontology_version"],
            )
            boundary_report = audit_training_boundary(
                paths["train_records"],
                profile.inputs.benchmark_test,
                profile.inputs.seed_train,
                profile.boundary,
            )
            if boundary_report["train_records"] > profile.budget.max_training_records:
                boundary_report["passed"] = False
                boundary_report["violations"].append(
                    {
                        "code": "training_record_budget_exceeded",
                        "observed": boundary_report["train_records"],
                        "limit": profile.budget.max_training_records,
                    }
                )
            _write_json(paths["boundary_report"], boundary_report)
            _write_json(
                paths["data_lineage"],
                _lineage_summary(
                    paths["train_records"],
                    profile.boundary,
                    profile.inputs.seed_train,
                ),
            )
            if not boundary_report["passed"]:
                raise FactoryError("Generated training data failed boundary checks.")
            _assert_frozen_inputs(
                profile,
                paths,
                hashes,
                boundary_report["train_sha256"],
            )

            _execute_accounted_step(
                executor,
                "train_lora",
                profile.commands.train_lora,
                base_context,
                profile,
                totals,
                attempt_usage,
                run_state_path,
                started_monotonic,
            )
            if not paths["checkpoint_dir"].is_dir() or not any(
                paths["checkpoint_dir"].iterdir()
            ):
                raise FactoryError("train_lora did not produce a checkpoint.")
            checkpoint_manifest = _checkpoint_manifest(paths["checkpoint_dir"])
            _write_json(paths["checkpoint_manifest"], checkpoint_manifest)
            checkpoint_hash = checkpoint_manifest["checkpoint_sha256"]
            base_context["checkpoint_sha256"] = checkpoint_hash
            _assert_frozen_inputs(
                profile,
                paths,
                hashes,
                boundary_report["train_sha256"],
            )

            _execute_accounted_step(
                executor,
                "evaluate",
                profile.commands.evaluate,
                base_context,
                profile,
                totals,
                attempt_usage,
                run_state_path,
                started_monotonic,
            )
            _require_file(paths["predictions"], "evaluate")
            require_structured_records(
                paths["predictions"],
                payload_field="prediction",
                schema_path=paths["extraction_schema"],
                ontology_path=paths["ontology_version"],
            )
            _assert_checkpoint(paths["checkpoint_dir"], checkpoint_hash)
            _assert_frozen_inputs(
                profile,
                paths,
                hashes,
                boundary_report["train_sha256"],
            )
            _validate_prediction_coverage(
                paths["predictions"],
                profile.inputs.benchmark_test,
                profile.boundary.record_id_field,
            )
            predictions_hash = _sha256_file(paths["predictions"])
            base_context["predictions_sha256"] = predictions_hash

            _execute_accounted_step(
                executor,
                "verify",
                profile.commands.verify,
                base_context,
                profile,
                totals,
                attempt_usage,
                run_state_path,
                started_monotonic,
            )
            _require_file(paths["metrics"], "verify")
            _require_file(paths["verification_records"], "verify")
            _validate_verification_records(
                paths["verification_records"],
                profile.inputs.benchmark_test,
                profile.boundary.record_id_field,
            )
            verification_records_hash = _sha256_file(
                paths["verification_records"]
            )
            base_context["verification_records_sha256"] = (
                verification_records_hash
            )
            system_effectiveness = evaluate_system_effectiveness(
                profile.inputs.benchmark_test,
                paths["predictions"],
                paths["verification_records"],
                profile.effectiveness,
            )
            _write_json(
                paths["system_effectiveness"],
                system_effectiveness,
            )
            metrics_hash = _sha256_file(paths["metrics"])
            _assert_checkpoint(paths["checkpoint_dir"], checkpoint_hash)
            _assert_frozen_inputs(
                profile,
                paths,
                hashes,
                boundary_report["train_sha256"],
            )

            _execute_accounted_step(
                executor,
                "analyze",
                profile.commands.analyze,
                base_context,
                profile,
                totals,
                attempt_usage,
                run_state_path,
                started_monotonic,
            )
            _require_file(paths["error_analysis"], "analyze")
            _validate_error_analysis(
                paths["error_analysis"],
                paths["verification_records"],
            )
            if _sha256_file(paths["predictions"]) != predictions_hash:
                raise FactoryError("predictions.jsonl changed after verification.")
            if _sha256_file(paths["metrics"]) != metrics_hash:
                raise FactoryError("metrics.json changed after verification.")
            if (
                _sha256_file(paths["verification_records"])
                != verification_records_hash
            ):
                raise FactoryError(
                    "verification_records.jsonl changed after verification."
                )
            _assert_checkpoint(paths["checkpoint_dir"], checkpoint_hash)
            _assert_frozen_inputs(
                profile,
                paths,
                hashes,
                boundary_report["train_sha256"],
            )

            cost = _attempt_cost(attempt_usage, attempt_started)
            _write_json(paths["cost"], cost)
            system_effectiveness_hash = _sha256_file(
                paths["system_effectiveness"]
            )
            totals["wall_clock_seconds"] = round(
                time.monotonic() - started_monotonic, 3
            )
            metrics = _read_json(paths["metrics"])
            verifier = _verify_attempt(
                profile,
                metrics,
                boundary_report,
                evaluation_hash,
                totals,
                checkpoint_hash,
                predictions_hash,
                verification_records_hash,
                cost,
                system_effectiveness,
                system_effectiveness_hash,
            )
            _write_json(paths["verifier"], verifier)
            artifacts_sha256 = _completed_artifact_hashes(paths)
            usage_sha256 = {
                entry["step"]: _sha256_file(
                    attempt_dir / "usage" / f"{entry['step']}.json"
                )
                for entry in attempt_usage
            }
            summary.update(
                {
                    "status": "completed",
                    "eligible": verifier["eligible"],
                    "rejection_reasons": verifier["rejection_reasons"],
                    "primary_metric": verifier["primary_metric"],
                    "tie_breaker_metrics": verifier["tie_breaker_metrics"],
                    "checkpoint": str(
                        paths["checkpoint_dir"].relative_to(run_path)
                    ),
                    "checkpoint_sha256": checkpoint_hash,
                    "cost": cost,
                    "metrics_sha256": _sha256_file(paths["metrics"]),
                    "predictions_sha256": predictions_hash,
                    "verification_records_sha256": verification_records_hash,
                    "system_effectiveness_sha256": system_effectiveness_hash,
                    "train_records_sha256": _sha256_file(paths["train_records"]),
                    "evaluation_profile_sha256": evaluation_hash,
                    "artifacts_sha256": artifacts_sha256,
                    "usage_sha256": usage_sha256,
                    "usage_nonces": {
                        entry["step"]: entry["usage_nonce"]
                        for entry in attempt_usage
                    },
                }
            )
        except (FactoryError, OSError, ValueError, json.JSONDecodeError) as exc:
            hard_stop = True
            if isinstance(exc, BudgetExhausted):
                hard_stop_reason = exc.reason
            summary.update(
                {
                    "status": "failed",
                    "error": str(exc),
                    "rejection_reasons": [str(exc)],
                }
            )
            if not paths["boundary_report"].exists():
                _write_json(
                    paths["boundary_report"],
                    {"passed": False, "violations": [{"code": "step_failure"}]},
                )
            if not paths["data_lineage"].exists():
                _write_json(
                    paths["data_lineage"],
                    {"status": "not_available", "reason": str(exc)},
                )
            if not paths["error_analysis"].exists():
                _write_json(
                    paths["error_analysis"],
                    {"status": "not_run", "reason": str(exc)},
                )
            if not paths["cost"].exists():
                _write_json(
                    paths["cost"],
                    _attempt_cost(attempt_usage, attempt_started),
                )
            if not paths["verifier"].exists():
                _write_json(
                    paths["verifier"],
                    {
                        "eligible": False,
                        "rejection_reasons": [str(exc)],
                    },
                )

        if paths["cost"].exists():
            summary.setdefault("cost", _read_json(paths["cost"]))
        if summary["status"] != "completed":
            summary["cost_sha256"] = _sha256_file(paths["cost"])
            summary["usage_sha256"] = {
                entry["step"]: _sha256_file(
                    attempt_dir / "usage" / f"{entry['step']}.json"
                )
                for entry in attempt_usage
                if entry.get("usage_complete")
            }
            summary["usage_nonces"] = {
                entry["step"]: entry["usage_nonce"]
                for entry in attempt_usage
                if entry.get("usage_complete")
                and isinstance(entry.get("usage_nonce"), str)
            }
        totals["wall_clock_seconds"] = round(
            time.monotonic() - started_monotonic, 3
        )
        _write_json(paths["attempt_manifest"], summary)
        _write_json(
            run_state_path,
            {
                "status": "running",
                "attempt_number": attempt_number,
                "attempt_status": summary["status"],
                "totals": totals,
            },
        )
        attempts.append(summary)
        _append_jsonl(run_path / "trajectory.jsonl", summary)
        if summary["status"] == "completed":
            previous_train = paths["train_records"]
            previous_error = paths["error_analysis"]
        if hard_stop:
            termination_reason = hard_stop_reason
            break

    for attempt in attempts:
        if attempt.get("status") == "completed":
            _revalidate_completed_attempt(
                profile,
                run_path / str(attempt["attempt_id"]),
                attempt,
                hashes,
                evaluation_hash,
            )
    selected = _select_best(attempts, profile.selection)
    selection_report = {
        "evaluation_profile_sha256": evaluation_hash,
        "adapter_digests": adapter_digests,
        "policy": _selection_dict(profile.selection),
        "selected": selected,
        "candidates": attempts,
    }
    _write_json(run_path / "selection.json", selection_report)
    totals["wall_clock_seconds"] = round(
        time.monotonic() - started_monotonic, 3
    )
    report = {
        "profile_id": profile.profile_id,
        "profile_version": profile.profile_version,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "evaluation_profile_sha256": evaluation_hash,
        "adapter_digests": adapter_digests,
        "termination_reason": termination_reason,
        "budget": asdict(profile.budget),
        "passed_environment_names": sorted(set(pass_environment)),
        "totals": totals,
        "selected": selected,
        "attempts": attempts,
    }
    _write_json(run_path / "run_manifest.json", report)
    _write_json(
        run_state_path,
        {
            "status": "finished",
            "termination_reason": termination_reason,
            "totals": totals,
            "selected": selected,
        },
    )
    return report


def _run_step(
    executor: StepExecutor,
    step: str,
    command: tuple[str, ...],
    base_context: dict[str, str],
    remaining: dict[str, str],
) -> None:
    allowed = _ALLOWED_PLACEHOLDERS[step]
    context = {
        key: value
        for key, value in {**base_context, **remaining}.items()
        if key in allowed or key in {"attempt_dir", "attempt_number"}
    }
    rendered = [argument.format_map(context) for argument in command]
    timeout = float(context["remaining_wall_clock_seconds"])
    if timeout <= 0:
        raise FactoryError("wall-clock budget exhausted before the next step")
    executor.run(step, rendered, context, timeout)


def _execute_accounted_step(
    executor: StepExecutor,
    step: str,
    command: tuple[str, ...],
    base_context: dict[str, str],
    profile: FactoryProfile,
    totals: dict,
    attempt_usage: list[dict],
    run_state_path: Path,
    started_monotonic: float,
) -> None:
    reason = _budget_stop_reason(profile.budget, totals, started_monotonic)
    if reason:
        raise BudgetExhausted(reason)
    usage_dir = Path(base_context["attempt_dir"]) / "usage"
    usage_dir.mkdir(exist_ok=True)
    usage_path = usage_dir / f"{step}.json"
    if usage_path.exists():
        raise StepExecutionError(
            f"Refusing pre-existing usage record for {step}: {usage_path}"
        )
    usage_nonce = secrets.token_hex(16)
    context = {
        **base_context,
        "step_usage": str(usage_path),
        "usage_nonce": usage_nonce,
    }
    usage_nonces = {
        entry["step"]: entry["usage_nonce"]
        for entry in attempt_usage
        if isinstance(entry.get("usage_nonce"), str)
    }
    usage_nonces[step] = usage_nonce
    remaining = _remaining_budget(profile.budget, totals, started_monotonic)
    _write_json(
        run_state_path,
        {
            "status": "running",
            "attempt_number": int(base_context["attempt_number"]),
            "attempt_started_at": base_context["attempt_started_at"],
            "step": step,
            "step_status": "running",
            "usage_nonce": usage_nonce,
            "usage_nonces": usage_nonces,
            "totals": totals,
        },
    )

    step_error: Exception | None = None
    try:
        _run_step(executor, step, command, context, remaining)
    except Exception as exc:
        step_error = exc

    usage_error: Exception | None = None
    if usage_path.is_file():
        try:
            usage = _load_step_usage(
                usage_path,
                expected_nonce=usage_nonce,
            )
        except Exception as exc:
            usage_error = exc
        else:
            entry = {"step": step, "usage_complete": True, **usage}
            _apply_usage(totals, usage)
    if not usage_path.is_file() or usage_error is not None:
        totals["usage_complete"] = False
        entry = {
            "step": step,
            "usage_complete": False,
            "cost_usd": None,
            "tokens": None,
            "human_review_records": None,
            "training_seconds": None,
        }
    attempt_usage.append(entry)
    attempt_cost = _attempt_cost(attempt_usage, started_monotonic)
    _write_json(Path(base_context["cost"]), attempt_cost)
    _write_json(
        run_state_path,
        {
            "status": "running",
            "attempt_number": int(base_context["attempt_number"]),
            "attempt_started_at": base_context["attempt_started_at"],
            "step": step,
            "step_status": (
                "failed"
                if step_error is not None or usage_error is not None
                else "completed"
            ),
            "usage_nonce": usage_nonce,
            "usage_nonces": usage_nonces,
            "totals": totals,
        },
    )
    if usage_error is not None:
        raise StepExecutionError(
            f"{step} reported invalid usage; spend is unknown"
        ) from usage_error
    if step_error is not None:
        if not entry["usage_complete"]:
            raise StepExecutionError(
                f"{step} failed and did not report usage; spend is unknown"
            ) from step_error
        raise step_error
    if not entry["usage_complete"]:
        raise StepExecutionError(
            f"{step} completed without its required atomic usage record"
        )


def _attempt_paths(attempt_dir: Path) -> dict[str, Path]:
    return {
        "train_records": attempt_dir / "train_records.jsonl",
        "checkpoint_dir": attempt_dir / "checkpoint",
        "extraction_schema": attempt_dir / "extraction_schema.json",
        "ontology_version": attempt_dir / "ontology_version.json",
        "prompt_version": attempt_dir / "prompt_version.txt",
        "model_config": attempt_dir / "model_config.json",
        "predictions": attempt_dir / "predictions.jsonl",
        "verification_records": attempt_dir / "verification_records.jsonl",
        "error_analysis": attempt_dir / "error_analysis.json",
        "metrics": attempt_dir / "metrics.json",
        "system_effectiveness": attempt_dir / "system_effectiveness.json",
        "cost": attempt_dir / "cost.json",
        "checkpoint_manifest": attempt_dir / "checkpoint_manifest.json",
        "boundary_report": attempt_dir / "boundary_report.json",
        "data_lineage": attempt_dir / "data_lineage.json",
        "verifier": attempt_dir / "verifier.json",
        "attempt_manifest": attempt_dir / "attempt_manifest.json",
    }


def _prepare_attempt(inputs: FactoryInputs, attempt_dir: Path) -> dict[str, Path]:
    paths = _attempt_paths(attempt_dir)
    shutil.copy2(inputs.extraction_schema, paths["extraction_schema"])
    shutil.copy2(inputs.ontology_version, paths["ontology_version"])
    shutil.copy2(inputs.prompt_version, paths["prompt_version"])
    shutil.copy2(inputs.model_config, paths["model_config"])
    return paths


def _completed_artifact_hashes(paths: dict[str, Path]) -> dict[str, str]:
    names = (
        "train_records",
        "extraction_schema",
        "ontology_version",
        "prompt_version",
        "model_config",
        "predictions",
        "verification_records",
        "error_analysis",
        "metrics",
        "system_effectiveness",
        "cost",
        "checkpoint_manifest",
        "boundary_report",
        "data_lineage",
        "verifier",
    )
    missing = [name for name in names if not paths[name].is_file()]
    if missing:
        raise FactoryError(
            f"Completed attempt is missing audit artifacts: {sorted(missing)}"
        )
    return {name: _sha256_file(paths[name]) for name in names}


def _verify_attempt(
    profile: FactoryProfile,
    metrics: dict,
    boundary_report: dict,
    evaluation_hash: str,
    totals: dict,
    checkpoint_hash: str,
    predictions_hash: str,
    verification_records_hash: str,
    cost: dict,
    system_effectiveness: dict,
    system_effectiveness_hash: str,
) -> dict:
    reasons = []
    if metrics.get("evaluation_profile_sha256") != evaluation_hash:
        reasons.append("evaluation_profile_sha256 mismatch")
    if metrics.get("checkpoint_sha256") != checkpoint_hash:
        reasons.append("checkpoint_sha256 mismatch")
    if metrics.get("predictions_sha256") != predictions_hash:
        reasons.append("predictions_sha256 mismatch")
    if (
        metrics.get("verification_records_sha256")
        != verification_records_hash
    ):
        reasons.append("verification_records_sha256 mismatch")
    if not cost["usage_complete"] or not totals["usage_complete"]:
        reasons.append("step usage is incomplete")
    if not boundary_report["passed"]:
        reasons.append("training data boundary failed")
    if not system_effectiveness.get("passed"):
        reasons.append("system effectiveness validation failed")
    if totals["cost_usd"] > profile.budget.max_cost_usd:
        reasons.append("cumulative cost budget exceeded")
    if totals["tokens"] > profile.budget.max_tokens:
        reasons.append("cumulative token budget exceeded")
    if (
        totals["human_review_records"]
        > profile.budget.max_human_review_records
    ):
        reasons.append("cumulative human-review budget exceeded")
    if (
        totals["wall_clock_seconds"]
        > profile.budget.max_wall_clock_seconds
    ):
        reasons.append("cumulative wall-clock budget exceeded")

    selection_metrics = dict(metrics)
    selection_metrics["system"] = system_effectiveness.get("metrics", {})
    gate_results = []
    for gate in profile.selection.gates:
        observed = _numeric_metric(selection_metrics, gate.metric)
        passed = _compare(observed, gate.operator, gate.value)
        gate_results.append(
            {
                "metric": gate.metric,
                "operator": gate.operator,
                "threshold": gate.value,
                "observed": observed,
                "passed": passed,
            }
        )
        if not passed:
            reasons.append(f"{gate.metric} {gate.operator} {gate.value}")

    primary = _numeric_metric(
        selection_metrics,
        profile.selection.primary_metric,
    )
    tie_values = {
        tie.metric: _numeric_metric(selection_metrics, tie.metric)
        for tie in profile.selection.tie_breakers
    }
    return {
        "eligible": not reasons,
        "evaluation_profile_sha256": evaluation_hash,
        "checkpoint_sha256": checkpoint_hash,
        "predictions_sha256": predictions_hash,
        "verification_records_sha256": verification_records_hash,
        "system_effectiveness_sha256": system_effectiveness_hash,
        "primary_metric": primary,
        "tie_breaker_metrics": tie_values,
        "gates": gate_results,
        "rejection_reasons": reasons,
    }


def _select_best(attempts: list[dict], policy: SelectionPolicy) -> dict | None:
    eligible = [
        attempt
        for attempt in attempts
        if attempt.get("status") == "completed"
        and attempt.get("eligible") is True
    ]
    if not eligible:
        return None

    def rank(attempt: dict) -> tuple:
        primary = float(attempt["primary_metric"])
        values = [primary if policy.direction == "maximize" else -primary]
        for tie in policy.tie_breakers:
            value = float(attempt["tie_breaker_metrics"][tie.metric])
            values.append(value if tie.direction == "maximize" else -value)
        values.append(-int(attempt["attempt_number"]))
        return tuple(values)

    best = max(eligible, key=rank)
    return {
        "attempt_id": best["attempt_id"],
        "checkpoint": best["checkpoint"],
        "checkpoint_sha256": best["checkpoint_sha256"],
        "evaluation_profile_sha256": best[
            "evaluation_profile_sha256"
        ],
        "primary_metric_name": policy.primary_metric,
        "primary_metric": best["primary_metric"],
        "tie_breaker_metrics": best["tie_breaker_metrics"],
        "metrics_sha256": best["metrics_sha256"],
        "predictions_sha256": best["predictions_sha256"],
        "verification_records_sha256": best[
            "verification_records_sha256"
        ],
        "system_effectiveness_sha256": best[
            "system_effectiveness_sha256"
        ],
        "train_records_sha256": best["train_records_sha256"],
    }


def _checkpoint_manifest(checkpoint_dir: Path) -> dict:
    files = []
    for path in sorted(checkpoint_dir.rglob("*")):
        if path.is_symlink():
            raise FactoryError("Checkpoint must not contain symbolic links.")
        if path.is_file():
            files.append(
                {
                    "path": path.relative_to(checkpoint_dir).as_posix(),
                    "size": path.stat().st_size,
                    "sha256": _sha256_file(path),
                }
            )
    if not files:
        raise FactoryError("Checkpoint contains no files.")
    digest = hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "manifest_version": "pas.checkpoint-manifest.v1",
        "checkpoint_sha256": digest,
        "files": files,
    }


def _assert_checkpoint(checkpoint_dir: Path, expected_hash: str) -> None:
    observed = _checkpoint_manifest(checkpoint_dir)["checkpoint_sha256"]
    if observed != expected_hash:
        raise FactoryError("Checkpoint changed after training.")


def _validate_prediction_coverage(
    predictions_path: Path,
    benchmark_path: Path,
    record_id_field: str,
) -> None:
    benchmark = _read_jsonl(benchmark_path)
    predictions = _read_jsonl(predictions_path)
    expected = [str(_field(row, record_id_field)) for row in benchmark]
    observed = [str(_field(row, record_id_field)) for row in predictions]
    if len(observed) != len(set(observed)):
        raise FactoryError("predictions.jsonl contains duplicate record IDs.")
    if set(observed) != set(expected):
        raise FactoryError(
            "predictions.jsonl must cover every benchmark record exactly once."
        )
    if any(not isinstance(row.get("prediction"), dict) for row in predictions):
        raise FactoryError(
            "Every prediction row must contain a structured prediction object."
        )


def _validate_verification_records(
    verification_path: Path,
    benchmark_path: Path,
    record_id_field: str,
) -> None:
    benchmark = _read_jsonl(benchmark_path)
    rows = _read_jsonl(verification_path)
    expected = {str(_field(row, record_id_field)) for row in benchmark}
    observed = [str(_field(row, record_id_field)) for row in rows]
    if len(observed) != len(set(observed)) or set(observed) != expected:
        raise FactoryError(
            "verification_records.jsonl must cover every benchmark record once."
        )
    for row in rows:
        if not isinstance(row.get("is_correct"), bool):
            raise FactoryError(
                "Every verification record must contain boolean is_correct."
            )
        if not isinstance(row.get("error_types"), list) or any(
            not isinstance(value, str) for value in row["error_types"]
        ):
            raise FactoryError(
                "Every verification record must contain string-list error_types."
            )
        if not isinstance(row.get("field_errors"), dict):
            raise FactoryError(
                "Every verification record must contain object field_errors."
            )


def _validate_error_analysis(
    analysis_path: Path,
    verification_path: Path,
) -> None:
    analysis = _read_json(analysis_path)
    verification = _read_jsonl(verification_path)
    expected_errors: Counter[str] = Counter(
        error
        for row in verification
        for error in row["error_types"]
    )
    expected_failed = sum(not row["is_correct"] for row in verification)
    if analysis.get("analysis_version") != "structured-extractor-errors.v1":
        raise FactoryError("error_analysis.json has an unsupported analysis_version.")
    total = analysis.get("total_predictions")
    failed = analysis.get("failed_predictions")
    if (
        isinstance(total, bool)
        or not isinstance(total, int)
        or total != len(verification)
        or isinstance(failed, bool)
        or not isinstance(failed, int)
        or failed != expected_failed
    ):
        raise FactoryError("error_analysis.json has invalid prediction counts.")
    if not isinstance(analysis.get("error_type_counts"), dict) or not isinstance(
        analysis.get("targeting_priorities"), list
    ):
        raise FactoryError("error_analysis.json is missing error category details.")
    if analysis["error_type_counts"] != dict(expected_errors):
        raise FactoryError(
            "error_analysis.json does not match per-record verifier errors."
        )
    if failed and not analysis["targeting_priorities"]:
        raise FactoryError(
            "Failed predictions require at least one targeting priority."
        )


def _lineage_summary(
    path: Path,
    policy: BoundaryPolicy,
    trusted_train_path: Path,
) -> dict:
    rows = _read_jsonl(path)
    trusted_rows = _read_jsonl(trusted_train_path)
    trusted_hashes = {
        str(_field(row, policy.record_id_field)): _content_hash(row)
        for row in trusted_rows
        if _field(row, policy.record_id_field) not in (None, "")
        and _field(row, policy.provenance_kind_field)
        in policy.trusted_root_kinds
    }
    kinds: Counter[str] = Counter()
    source_splits: Counter[str] = Counter()
    generated_sources: Counter[str] = Counter()
    lineage_records = []
    for row in rows:
        record_id = str(_field(row, policy.record_id_field))
        kind = str(_field(row, policy.provenance_kind_field))
        kinds[kind] += 1
        source_splits[str(_field(row, policy.source_split_field))] += 1
        source_ids = []
        if kind in policy.generated_kinds:
            source_ids = _field(row, policy.source_record_ids_field) or []
            if isinstance(source_ids, list):
                generated_sources.update(str(source_id) for source_id in source_ids)
        lineage_records.append(
            {
                "record_id": record_id,
                "record_sha256": _content_hash(row),
                "provenance_kind": kind,
                "source_records": [
                    {
                        "record_id": str(source_id),
                        "trusted_record_sha256": trusted_hashes.get(
                            str(source_id)
                        ),
                    }
                    for source_id in source_ids
                ]
                if isinstance(source_ids, list)
                else [],
            }
        )
    return {
        "lineage_version": "pas.extractor-data-lineage.v1",
        "records": len(rows),
        "provenance_kind_counts": dict(kinds),
        "source_split_counts": dict(source_splits),
        "generated_source_record_counts": dict(generated_sources),
        "train_records_sha256": _sha256_file(path),
        "trusted_train_sha256": _sha256_file(trusted_train_path),
        "record_lineage": lineage_records,
    }


def _load_step_usage(path: Path, *, expected_nonce: str | None = None) -> dict:
    raw = _read_json(path)
    usage_nonce = raw.get("usage_nonce")
    if (
        not isinstance(usage_nonce, str)
        or not usage_nonce
        or (expected_nonce is not None and usage_nonce != expected_nonce)
    ):
        raise FactoryError(f"{path.name} has an invalid usage_nonce.")
    numeric = ("cost_usd", "training_seconds")
    integers = ("tokens", "human_review_records")
    if any(
        isinstance(raw.get(name), bool)
        or not isinstance(raw.get(name), (int, float))
        or not math.isfinite(float(raw[name]))
        or raw[name] < 0
        for name in numeric
    ) or any(
        isinstance(raw.get(name), bool)
        or not isinstance(raw.get(name), int)
        or raw[name] < 0
        for name in integers
    ):
        raise FactoryError(
            f"{path.name} must contain non-negative cost_usd, integer tokens, "
            "integer human_review_records, and training_seconds."
        )
    return {
        "usage_nonce": usage_nonce,
        "cost_usd": float(raw["cost_usd"]),
        "tokens": int(raw["tokens"]),
        "human_review_records": int(raw["human_review_records"]),
        "training_seconds": float(raw["training_seconds"]),
    }


def _apply_usage(totals: dict, usage: dict) -> None:
    totals["cost_usd"] = round(totals["cost_usd"] + usage["cost_usd"], 6)
    totals["tokens"] += usage["tokens"]
    totals["human_review_records"] += usage["human_review_records"]


def _attempt_cost(usage: list[dict], started_monotonic: float) -> dict:
    complete = all(entry["usage_complete"] for entry in usage)
    return {
        "usage_complete": complete,
        "cost_usd": round(
            sum(entry["cost_usd"] or 0.0 for entry in usage),
            6,
        ),
        "tokens": sum(entry["tokens"] or 0 for entry in usage),
        "human_review_records": sum(
            entry["human_review_records"] or 0 for entry in usage
        ),
        "training_seconds": round(
            sum(entry["training_seconds"] or 0.0 for entry in usage),
            3,
        ),
        "wall_clock_seconds": round(time.monotonic() - started_monotonic, 3),
        "steps": usage,
    }


def _budget_stop_reason(
    budget: FactoryBudget, totals: dict, started_monotonic: float
) -> str | None:
    if totals["cost_usd"] >= budget.max_cost_usd:
        return "cost_budget_exhausted"
    if totals["tokens"] >= budget.max_tokens:
        return "token_budget_exhausted"
    if totals["human_review_records"] >= budget.max_human_review_records:
        return "human_review_budget_exhausted"
    if time.monotonic() - started_monotonic >= budget.max_wall_clock_seconds:
        return "wall_clock_budget_exhausted"
    return None


def _remaining_budget(
    budget: FactoryBudget, totals: dict, started_monotonic: float
) -> dict[str, str]:
    return {
        "remaining_cost_usd": str(
            round(max(0.0, budget.max_cost_usd - totals["cost_usd"]), 6)
        ),
        "remaining_tokens": str(max(0, budget.max_tokens - totals["tokens"])),
        "remaining_human_review_records": str(
            max(
                0,
                budget.max_human_review_records
                - totals["human_review_records"],
            )
        ),
        "remaining_wall_clock_seconds": str(
            round(
                max(
                    0.0,
                    budget.max_wall_clock_seconds
                    - (time.monotonic() - started_monotonic),
                ),
                3,
            )
        ),
    }


def _evaluation_profile_hash(
    profile: FactoryProfile,
    hashes: dict[str, str],
    adapter_digests: dict[str, dict[str, str]],
) -> str:
    payload = {
        "profile_version": profile.profile_version,
        "profile_id": profile.profile_id,
        "benchmark_test_sha256": hashes["benchmark_test"],
        "extraction_schema_sha256": hashes["extraction_schema"],
        "ontology_version_sha256": hashes["ontology_version"],
        "selection": _selection_dict(profile.selection),
        "effectiveness": asdict(profile.effectiveness),
        "evaluate_command": list(profile.commands.evaluate),
        "verify_command": list(profile.commands.verify),
        "adapter_digests": {
            module: digest
            for module, digest in adapter_digests.items()
            if module in {
                profile.commands.evaluate[2],
                profile.commands.verify[2],
                "execution_mode",
                "python_interpreter",
            }
        },
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _resolve_adapter_digests(
    commands: FactoryCommands,
) -> dict[str, dict[str, str]]:
    modules = sorted(
        {
            getattr(commands, step)[2]
            for step in (
                "generate",
                "train_lora",
                "evaluate",
                "verify",
                "analyze",
            )
        }
    )
    return {
        "python_interpreter": {
            "origin": str(Path(sys.executable).resolve()),
            "sha256": _sha256_file(Path(sys.executable).resolve()),
        },
        **{module: _resolve_python_module(module) for module in modules},
    }


def _resolve_python_module(module: str) -> dict[str, str]:
    resolver = (
        "import importlib.util, json, pathlib, sys; "
        "spec=importlib.util.find_spec(sys.argv[1]); "
        "origin=getattr(spec, 'origin', None) if spec else None; "
        "print(json.dumps({'origin': str(pathlib.Path(origin).resolve()) "
        "if origin and origin not in {'built-in','frozen'} else origin}))"
    )
    completed = subprocess.run(
        [sys.executable, "-I", "-c", resolver, module],
        env={
            "PATH": str(Path(sys.executable).parent),
            **{
                name: value
                for name in ("TMPDIR", "LANG", "LC_ALL")
                if (value := os.environ.get(name)) is not None
            },
        },
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ProfileError(
            f"Could not resolve reviewed adapter '{module}': "
            f"{completed.stderr.strip()}"
        )
    try:
        origin = json.loads(completed.stdout)["origin"]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ProfileError(
            f"Could not resolve reviewed adapter '{module}'."
        ) from exc
    if not isinstance(origin, str):
        raise ProfileError(
            f"Reviewed adapter '{module}' is not installed as a source artifact."
        )
    path = Path(origin)
    if not path.is_file():
        raise ProfileError(
            f"Reviewed adapter '{module}' has no hashable source file: {path}"
        )
    return {"origin": str(path), "sha256": _sha256_file(path)}


def _selection_dict(selection: SelectionPolicy) -> dict:
    return {
        "primary_metric": selection.primary_metric,
        "direction": selection.direction,
        "gates": [asdict(gate) for gate in selection.gates],
        "tie_breakers": [asdict(tie) for tie in selection.tie_breakers],
    }


def _validate_release_effectiveness_gates(
    effectiveness: EffectivenessPolicy,
    selection: SelectionPolicy,
) -> None:
    if effectiveness.benchmark_tier != "release":
        return
    by_metric = {gate.metric: gate for gate in selection.gates}
    invalid = []
    for metric, (limit_type, limit) in _RELEASE_GATE_LIMITS.items():
        gate = by_metric.get(metric)
        if gate is None:
            invalid.append(metric)
            continue
        if limit_type == "minimum":
            valid = gate.operator in {">", ">="} and gate.value >= limit
        else:
            valid = gate.operator in {"<", "<="} and gate.value <= limit
        if not valid or not 0 <= gate.value <= 1:
            invalid.append(metric)
    if invalid:
        raise ProfileError(
            "Release effectiveness requires selection gates at least as strict "
            f"as the release floors for: {sorted(invalid)}."
        )


def _validate_pass_environment(names: tuple[str, ...]) -> None:
    invalid = sorted(
        {
            str(name)
            for name in names
            if (
                not isinstance(name, str)
                or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None
                or name in _BLOCKED_ENVIRONMENT_NAMES
                or name.startswith(("PYTHON", "DYLD_", "LD_"))
            )
        }
    )
    if invalid:
        raise ProfileError(
            "Environment variables that control Python or dynamic loading "
            f"cannot be passed to adapters: {invalid}."
        )


def _benchmark_inference_row(row: dict) -> dict:
    allowed_roots = _SAFE_IDENTITY_FIELDS | _SAFE_CONTENT_FIELDS
    return {
        key: value
        for key, value in row.items()
        if key in allowed_roots
    }


def _input_hashes(inputs: FactoryInputs) -> dict[str, str]:
    return {
        name: _sha256_file(getattr(inputs, name))
        for name in (
            "seed_train",
            "benchmark_test",
            "extraction_schema",
            "ontology_version",
            "prompt_version",
            "model_config",
        )
    }


def _assert_frozen_inputs(
    profile: FactoryProfile,
    attempt_paths: dict[str, Path],
    expected_hashes: dict[str, str],
    expected_train_hash: str,
) -> None:
    current = _input_hashes(profile.inputs)
    for name, expected in expected_hashes.items():
        if current[name] != expected:
            raise FactoryError(f"Frozen input changed during the run: {name}.")
    for name in (
        "extraction_schema",
        "ontology_version",
        "prompt_version",
        "model_config",
    ):
        if _sha256_file(attempt_paths[name]) != expected_hashes[name]:
            raise FactoryError(
                f"Frozen attempt snapshot changed during the run: {name}."
            )
    if _sha256_file(attempt_paths["train_records"]) != expected_train_hash:
        raise FactoryError("train_records.jsonl changed after its boundary audit.")


def _validate_placeholders(step: str, command: tuple[str, ...]) -> None:
    allowed = _ALLOWED_PLACEHOLDERS[step]
    for argument in command:
        for _literal, field, _format, _conversion in string.Formatter().parse(
            argument
        ):
            if field and field not in allowed:
                raise ProfileError(
                    f"{step} command cannot use placeholder {{{field}}}; "
                    f"allowed: {sorted(allowed)}"
                )


def _validate_command_policy(
    step: str,
    command: tuple[str, ...],
    policy: ExecutionPolicy,
) -> None:
    executable = Path(command[0]).name
    if executable not in policy.allowed_executables:
        raise ProfileError(
            f"{step} executable '{executable}' is not in execution.allowed_executables."
        )
    if executable not in _SYSTEM_EXECUTABLE_ALLOWLIST:
        raise ProfileError(
            f"{step} executable '{executable}' is not allowed by the factory runtime."
        )
    if executable.startswith("python"):
        if len(command) < 3 or command[1] != "-m":
            raise ProfileError(
                f"{step} Python command must call one reviewed module with -m."
            )
        module = command[2]
        if not any(
            module.startswith(prefix)
            for prefix in policy.allowed_python_module_prefixes
        ):
            raise ProfileError(
                f"{step} module '{module}' is outside the allowed module prefixes."
            )
        if not module.startswith(_SYSTEM_PYTHON_MODULE_PREFIXES):
            raise ProfileError(
                f"{step} module '{module}' is not a reviewed factory adapter."
            )
        expected_tail = _COMMAND_TAIL_SCHEMAS[step]
        if tuple(command[3:]) != expected_tail:
            raise ProfileError(
                f"{step} command arguments must exactly match the reviewed "
                f"step contract: {list(expected_tail)}."
            )


def _command(
    mapping: dict, key: str, *, required: bool = True
) -> tuple[str, ...] | None:
    value = mapping.get(key)
    if value is None and not required:
        return None
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item for item in value)
    ):
        raise ProfileError(f"commands.{key} must be a non-empty argv list.")
    return tuple(value)


def _required_mapping(mapping: dict, key: str) -> dict:
    value = mapping.get(key)
    if not isinstance(value, dict):
        raise ProfileError(f"{key} must be an object.")
    return value


def _required_string(mapping: dict, key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ProfileError(f"{key} must be a non-empty string.")
    return value.strip()


def _required_string_tuple(mapping: dict, key: str) -> tuple[str, ...]:
    value = mapping.get(key)
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item for item in value)
    ):
        raise ProfileError(f"{key} must be a non-empty string list.")
    return tuple(value)


def _mapping_list(value, name: str) -> list[dict]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ProfileError(f"{name} must be a list of objects.")
    return value


def _positive_int(mapping: dict, key: str) -> int:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ProfileError(f"{key} must be a positive integer.")
    return value


def _positive_number(mapping: dict, key: str) -> float:
    value = mapping.get(key)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value <= 0
    ):
        raise ProfileError(f"{key} must be a positive number.")
    return float(value)


def _finite_number(value, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ProfileError(f"{name} must be a finite number.")
    return float(value)


def _unit_interval(value, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0 < value <= 1
    ):
        raise ProfileError(f"{name} must be in (0, 1].")
    return float(value)


def _direction(value, name: str) -> str:
    if value not in {"maximize", "minimize"}:
        raise ProfileError(f"{name} must be maximize or minimize.")
    return str(value)


def _operator(value) -> str:
    if value not in {"<", "<=", "==", ">=", ">"}:
        raise ProfileError("Metric gate operator must be one of <, <=, ==, >=, >.")
    return str(value)


def _existing_path(base: Path, value: str, name: str) -> Path:
    path = (base / value).resolve()
    if not path.is_file():
        raise ProfileError(f"inputs.{name} does not exist: {path}")
    return path


def _validate_input_roles(inputs: FactoryInputs) -> None:
    paths = asdict(inputs)
    names = list(paths)
    for index, left_name in enumerate(names):
        for right_name in names[index + 1 :]:
            left = Path(paths[left_name])
            right = Path(paths[right_name])
            if left.samefile(right):
                raise ProfileError(
                    f"inputs.{left_name} and inputs.{right_name} must be "
                    "distinct files."
                )
    benchmark_hash = _sha256_file(inputs.benchmark_test)
    for name in names:
        if name == "benchmark_test":
            continue
        if _sha256_file(Path(paths[name])) == benchmark_hash:
            raise ProfileError(
                f"inputs.{name} must not duplicate benchmark_test content."
            )
    prompt_text = inputs.prompt_version.read_text(encoding="utf-8")
    if not prompt_text.strip():
        raise ProfileError("inputs.prompt_version must be non-empty UTF-8 text.")
    try:
        model_config = json.loads(inputs.model_config.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProfileError("inputs.model_config must be valid JSON.") from exc
    if not isinstance(model_config, dict):
        raise ProfileError("inputs.model_config must contain a JSON object.")
    control_text = _normalized_text(
        f"{prompt_text}\n{_stable_value(model_config)}"
    )
    for row in _read_jsonl(inputs.benchmark_test):
        protected_values = []
        for field in _SAFE_CONTENT_FIELDS:
            value = row.get(field)
            if isinstance(value, str):
                protected_values.append(value)
            elif isinstance(value, dict):
                protected_values.extend(
                    child for child in value.values() if isinstance(child, str)
                )
        for value in protected_values:
            normalized = _normalized_text(value)
            if len(normalized) >= 20 and normalized in control_text:
                raise ProfileError(
                    "prompt_version or model_config contains held-out benchmark "
                    "input content."
                )
        target = row.get("target")
        normalized_target = (
            _normalized_text(_stable_value(target))
            if isinstance(target, dict)
            else ""
        )
        if (
            len(normalized_target) >= 20
            and normalized_target in control_text
        ):
            raise ProfileError(
                "prompt_version or model_config contains a held-out gold target."
            )


def _profile_trusted_root(profile_path: Path) -> Path:
    for parent in profile_path.parents:
        if (parent / "backend").is_dir() and (parent / "experiments").is_dir():
            return parent.resolve()
    return profile_path.parent.resolve()


def _field(row: dict, dotted_path: str):
    value = row
    for part in dotted_path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _numeric_metric(metrics: dict, path: str) -> float:
    value = _field(metrics, path)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise FactoryError(
            f"metrics.json is missing finite numeric metric '{path}'."
        )
    return float(value)


def _compare(observed: float, operator: str, threshold: float) -> bool:
    return {
        "<": observed < threshold,
        "<=": observed <= threshold,
        "==": observed == threshold,
        ">=": observed >= threshold,
        ">": observed > threshold,
    }[operator]


def _stable_value(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _content_hash(value) -> str:
    if isinstance(value, str):
        normalized = _normalized_text(value)
    else:
        normalized = _stable_value(value)
    return hashlib.sha256(normalized.encode()).hexdigest()


def _record_text_surfaces(
    row: dict,
    policy: BoundaryPolicy,
) -> list[tuple[str, str]]:
    surfaces: list[tuple[str, str]] = []
    included_roots: set[str] = set()
    for field in policy.content_fields:
        value = _field(row, field)
        included_roots.add(field.split(".", 1)[0])
        if isinstance(value, str):
            surfaces.append((field, value))
        elif isinstance(value, dict):
            surfaces.extend(
                (f"{field}.{key}", text)
                for key, text in value.items()
                if isinstance(key, str) and isinstance(text, str)
            )
    if "context_chunks" not in included_roots:
        context_chunks = row.get("context_chunks")
        if isinstance(context_chunks, dict):
            surfaces.extend(
                (f"context_chunks.{key}", text)
                for key, text in context_chunks.items()
                if isinstance(key, str) and isinstance(text, str)
            )
    return surfaces


def _context_chunk_ids(row: dict) -> set[str]:
    context_chunks = row.get("context_chunks")
    if not isinstance(context_chunks, dict):
        return set()
    return {
        str(key)
        for key, value in context_chunks.items()
        if isinstance(key, str) and isinstance(value, str)
    }


def _near_duplicate_similarity(left: str, right: str) -> float:
    left_normalized = _normalized_text(left)
    right_normalized = _normalized_text(right)
    sequence = SequenceMatcher(
        None,
        left_normalized,
        right_normalized,
    ).ratio()
    left_tokens = left_normalized.split()
    right_tokens = right_normalized.split()
    if not left_tokens or not right_tokens:
        return sequence
    left_counts = Counter(left_tokens)
    right_counts = Counter(right_tokens)
    shared = sum((left_counts & right_counts).values())
    containment = shared / min(len(left_tokens), len(right_tokens))
    return max(sequence, containment)


def _normalized_text(value: str) -> str:
    return " ".join(value.lower().split())


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FactoryError(f"Expected a JSON object in {path}.")
    return value


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise FactoryError(f"{path}:{line_number} must be a JSON object.")
        rows.append(value)
    return rows


def _require_file(path: Path, step: str) -> None:
    if not path.is_file():
        raise FactoryError(f"{step} did not produce {path.name}.")


def _write_json(path: Path, payload: dict) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _append_jsonl(path: Path, payload: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _write_profile_snapshot(source: Path, destination: Path) -> None:
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ProfileError("Factory profile must be a YAML object.")
    inputs = raw.get("inputs")
    if isinstance(inputs, dict) and "benchmark_test" in inputs:
        inputs["benchmark_test"] = "[HELD_OUT_PATH_REDACTED]"
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.write_text(
        yaml.safe_dump(raw, sort_keys=False),
        encoding="utf-8",
    )
    os.replace(temporary, destination)


def _redact(value: str, secrets: list[str]) -> str:
    redacted = value
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted
