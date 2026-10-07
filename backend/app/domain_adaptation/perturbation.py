"""Fail-closed, claim-level counterfactual checks for teacher consensus."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from typing import Any, Literal

from pydantic import Field

from app.domain_adaptation.consensus import (
    ClaimPerturbationCase,
    ModelClaimPerturbationResult,
    normalize_consensus_value,
)
from app.domain_adaptation.model_benchmark import TeacherModelCandidate
from app.domain_adaptation.models import DomainModel


PerturbationOutcome = Literal[
    "passed",
    "failed",
    "missing_result",
    "invalid_result",
    "invocation_error",
]
PerturbationBatchParseStatus = Literal[
    "valid",
    "salvaged",
    "invalid",
    "invocation_error",
]


_SYSTEM_PROMPT = """You audit evidence dependence in scientific extraction.
For every case, extract all verbatim source strings that answer the requested
entity type and field. Use only source_text. Return one JSON object with this
shape: {"results":[{"case_id":"...","values":["..."]}]}. Return an empty
values list when the requested field is absent. Do not infer, normalize, use
outside knowledge, or return markdown."""


class PerturbationObservation(DomainModel):
    schema_version: str = "domain-teacher-perturbation-observation-v0.1"
    case_id: str
    decision_id: str
    model_alias: str
    model_id: str
    perturbation_type: str
    outcome: PerturbationOutcome
    observed_values: list[str] = Field(default_factory=list)
    diagnostic: str | None = None


class PerturbationBatchRecord(DomainModel):
    schema_version: str = "domain-teacher-perturbation-batch-v0.1"
    batch_id: str
    model_alias: str
    model_id: str
    case_ids: list[str]
    parse_status: PerturbationBatchParseStatus
    response_text: str | None = None
    response_sha256: str | None = None
    stop_reason: str | None = None
    input_token_count: int = Field(default=0, ge=0)
    output_token_count: int = Field(default=0, ge=0)
    diagnostic: str | None = None


class PerturbationEvaluationReport(DomainModel):
    schema_version: str = "domain-teacher-perturbation-evaluation-report-v0.1"
    case_count: int = Field(ge=0)
    targeted_model_case_count: int = Field(ge=0)
    observation_count: int = Field(ge=0)
    passed_observation_count: int = Field(ge=0)
    failed_observation_count: int = Field(ge=0)
    invalid_observation_count: int = Field(ge=0)
    model_claim_count: int = Field(ge=0)
    passed_model_claim_count: int = Field(ge=0)
    failed_model_claim_count: int = Field(ge=0)
    invocation_count: int = Field(ge=0)
    input_token_count: int = Field(ge=0)
    output_token_count: int = Field(ge=0)
    claims_boundary: str = (
        "Counterfactual checks measure claim-level evidence dependence, not "
        "scientific precision or recall."
    )


class PerturbationEvaluationRun(DomainModel):
    batches: list[PerturbationBatchRecord]
    observations: list[PerturbationObservation]
    results: list[ModelClaimPerturbationResult]
    report: PerturbationEvaluationReport


def _chunks[T](items: Sequence[T], size: int) -> list[Sequence[T]]:
    if size < 1:
        raise ValueError("Perturbation batch size must be positive")
    return [items[index : index + size] for index in range(0, len(items), size)]


def _prompt(cases: Sequence[ClaimPerturbationCase]) -> str:
    payload = {
        "cases": [
            {
                "case_id": item.case_id,
                "entity_type": item.entity_type,
                "field_name": item.field_name,
                "source_text": item.mutated_quote,
            }
            for item in cases
        ]
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _response_text(response: dict[str, Any]) -> str:
    return "".join(
        block.get("text", "")
        for block in response["output"]["message"]["content"]
        if isinstance(block, dict)
    )


def _parse_payload(payload: Any) -> dict[str, list[str]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("Response must contain a results array")
    parsed: dict[str, list[str]] = {}
    for raw_item in payload["results"]:
        if not isinstance(raw_item, dict):
            raise ValueError("Each perturbation result must be an object")
        case_id = raw_item.get("case_id")
        values = raw_item.get("values")
        if not isinstance(case_id, str) or not isinstance(values, list):
            raise ValueError("Each result requires case_id and values")
        if case_id in parsed:
            raise ValueError("Response contains a duplicate case_id")
        if not all(isinstance(value, str) and value.strip() for value in values):
            raise ValueError("Perturbation values must be non-empty strings")
        parsed[case_id] = values
    return parsed


def _parse_results(text: str) -> tuple[dict[str, list[str]], bool]:
    stripped = text.strip()
    try:
        return _parse_payload(json.loads(stripped)), False
    except (json.JSONDecodeError, ValueError) as direct_error:
        decoder = json.JSONDecoder()
        for index, character in enumerate(stripped):
            if character != "{":
                continue
            try:
                payload, _end = decoder.raw_decode(stripped[index:])
                return _parse_payload(payload), True
            except (json.JSONDecodeError, ValueError):
                continue
        raise ValueError(f"Could not parse perturbation JSON: {direct_error}") from direct_error


def _batch_id(model_alias: str, cases: Sequence[ClaimPerturbationCase]) -> str:
    digest = hashlib.sha256(
        "\0".join([model_alias, *(item.case_id for item in cases)]).encode("utf-8")
    ).hexdigest()
    return f"perturb_batch_{digest[:16]}"


def _observed_value_supported(value: str, source_text: str) -> bool:
    return normalize_consensus_value(value) in normalize_consensus_value(source_text)


def _evaluate_observation(
    *,
    case: ClaimPerturbationCase,
    model: TeacherModelCandidate,
    values: list[str] | None,
    fallback_outcome: PerturbationOutcome | None = None,
    diagnostic: str | None = None,
) -> PerturbationObservation:
    if fallback_outcome is not None:
        return PerturbationObservation(
            case_id=case.case_id,
            decision_id=case.decision_id,
            model_alias=model.alias,
            model_id=model.model_id,
            perturbation_type=case.perturbation_type,
            outcome=fallback_outcome,
            diagnostic=diagnostic,
        )
    if values is None:
        return PerturbationObservation(
            case_id=case.case_id,
            decision_id=case.decision_id,
            model_alias=model.alias,
            model_id=model.model_id,
            perturbation_type=case.perturbation_type,
            outcome="missing_result",
            diagnostic="Model response omitted this case",
        )
    if not all(_observed_value_supported(value, case.mutated_quote) for value in values):
        return PerturbationObservation(
            case_id=case.case_id,
            decision_id=case.decision_id,
            model_alias=model.alias,
            model_id=model.model_id,
            perturbation_type=case.perturbation_type,
            outcome="invalid_result",
            observed_values=values,
            diagnostic="At least one observed value is not in the mutated source",
        )
    normalized_values = {normalize_consensus_value(value) for value in values}
    original_absent = (
        normalize_consensus_value(case.original_source_value)
        not in normalized_values
    )
    if case.perturbation_type == "evidence_deletion":
        passed = original_absent
    else:
        expected = case.expected_source_value
        passed = (
            expected is not None
            and normalize_consensus_value(expected) in normalized_values
            and original_absent
        )
    return PerturbationObservation(
        case_id=case.case_id,
        decision_id=case.decision_id,
        model_alias=model.alias,
        model_id=model.model_id,
        perturbation_type=case.perturbation_type,
        outcome="passed" if passed else "failed",
        observed_values=values,
    )


def _aggregate_results(
    observations: list[PerturbationObservation],
) -> list[ModelClaimPerturbationResult]:
    grouped: dict[tuple[str, str], list[PerturbationObservation]] = defaultdict(list)
    for observation in observations:
        grouped[(observation.model_alias, observation.decision_id)].append(observation)
    results: list[ModelClaimPerturbationResult] = []
    for (model_alias, decision_id), items in sorted(grouped.items()):
        by_type: dict[str, PerturbationObservation] = {}
        for item in items:
            if item.perturbation_type in by_type:
                raise ValueError("Duplicate perturbation type for one model claim")
            by_type[item.perturbation_type] = item
        deletion = by_type.get("evidence_deletion")
        numeric = by_type.get("numeric_replacement")
        results.append(
            ModelClaimPerturbationResult(
                model_alias=model_alias,
                decision_id=decision_id,
                evidence_deletion_passed=(
                    deletion is not None and deletion.outcome == "passed"
                ),
                numeric_replacement_passed=(
                    numeric.outcome == "passed" if numeric is not None else None
                ),
            )
        )
    return results


def _finalize_run(
    *,
    cases: list[ClaimPerturbationCase],
    batches: list[PerturbationBatchRecord],
    observations: list[PerturbationObservation],
) -> PerturbationEvaluationRun:
    observations.sort(key=lambda item: (item.decision_id, item.model_alias, item.case_id))
    batches.sort(key=lambda item: (item.model_alias, item.batch_id))
    results = _aggregate_results(observations)
    outcome_counts = Counter(item.outcome for item in observations)
    passed_model_claim_count = sum(
        item.evidence_deletion_passed
        and item.numeric_replacement_passed is not False
        for item in results
    )
    report = PerturbationEvaluationReport(
        case_count=len(cases),
        targeted_model_case_count=len(observations),
        observation_count=len(observations),
        passed_observation_count=outcome_counts["passed"],
        failed_observation_count=outcome_counts["failed"],
        invalid_observation_count=(
            outcome_counts["missing_result"]
            + outcome_counts["invalid_result"]
            + outcome_counts["invocation_error"]
        ),
        model_claim_count=len(results),
        passed_model_claim_count=passed_model_claim_count,
        failed_model_claim_count=len(results) - passed_model_claim_count,
        invocation_count=len(batches),
        input_token_count=sum(item.input_token_count for item in batches),
        output_token_count=sum(item.output_token_count for item in batches),
    )
    return PerturbationEvaluationRun(
        batches=batches,
        observations=observations,
        results=results,
        report=report,
    )


def replay_perturbation_batches(
    *,
    cases: list[ClaimPerturbationCase],
    models: list[TeacherModelCandidate],
    batches: list[PerturbationBatchRecord],
) -> PerturbationEvaluationRun:
    """Re-evaluate persisted raw model responses without new model calls."""
    case_by_id = {item.case_id: item for item in cases}
    model_by_alias = {item.alias: item for item in models}
    if len(case_by_id) != len(cases):
        raise ValueError("Perturbation replay cases contain duplicate IDs")
    if len(model_by_alias) != len(models):
        raise ValueError("Perturbation replay models contain duplicate aliases")
    expected_pairs = {
        (alias, case.case_id)
        for case in cases
        for alias in case.target_model_aliases
        if alias in model_by_alias
    }
    observed_pairs: set[tuple[str, str]] = set()
    replayed_batches: list[PerturbationBatchRecord] = []
    observations: list[PerturbationObservation] = []
    for batch_record in batches:
        if batch_record.model_alias not in model_by_alias:
            raise ValueError(
                f"Replay batch targets unknown model: {batch_record.model_alias}"
            )
        model = model_by_alias[batch_record.model_alias]
        if model.model_id != batch_record.model_id:
            raise ValueError("Replay batch model ID does not match its model alias")
        batch_cases = [
            case_by_id[case_id]
            for case_id in batch_record.case_ids
            if case_id in case_by_id
        ]
        if len(batch_cases) != len(batch_record.case_ids):
            raise ValueError("Replay batch contains unknown case IDs")
        for case in batch_cases:
            pair = (model.alias, case.case_id)
            if pair in observed_pairs:
                raise ValueError("Replay batches contain a duplicate model case")
            observed_pairs.add(pair)
        if batch_record.response_text is None:
            diagnostic = batch_record.diagnostic or "Model response is unavailable"
            replayed_batches.append(batch_record)
            observations.extend(
                _evaluate_observation(
                    case=case,
                    model=model,
                    values=None,
                    fallback_outcome="invocation_error",
                    diagnostic=diagnostic,
                )
                for case in batch_cases
            )
            continue
        try:
            parsed, salvaged = _parse_results(batch_record.response_text)
        except ValueError as error:
            diagnostic = str(error)[:1000]
            replayed_batches.append(
                batch_record.model_copy(
                    update={"parse_status": "invalid", "diagnostic": diagnostic}
                )
            )
            observations.extend(
                _evaluate_observation(
                    case=case,
                    model=model,
                    values=None,
                    fallback_outcome="invalid_result",
                    diagnostic=diagnostic,
                )
                for case in batch_cases
            )
            continue
        expected_case_ids = {item.case_id for item in batch_cases}
        unexpected = sorted(set(parsed) - expected_case_ids)
        unexpected_diagnostic = (
            "Response returned unexpected case IDs: " + ", ".join(unexpected)
            if unexpected
            else None
        )
        replayed_batches.append(
            batch_record.model_copy(
                update={
                    "parse_status": (
                        "salvaged" if salvaged or unexpected else "valid"
                    ),
                    "diagnostic": unexpected_diagnostic,
                }
            )
        )
        observations.extend(
            _evaluate_observation(
                case=case,
                model=model,
                values=parsed.get(case.case_id),
            )
            for case in batch_cases
        )
    if observed_pairs != expected_pairs:
        missing = sorted(expected_pairs - observed_pairs)
        extra = sorted(observed_pairs - expected_pairs)
        raise ValueError(
            f"Replay batch coverage mismatch; missing={missing}, extra={extra}"
        )
    return _finalize_run(
        cases=cases,
        batches=replayed_batches,
        observations=observations,
    )


def evaluate_perturbation_cases(
    *,
    cases: list[ClaimPerturbationCase],
    models: list[TeacherModelCandidate],
    client_factory: Callable[[TeacherModelCandidate], Any],
    batch_size: int = 20,
) -> PerturbationEvaluationRun:
    """Ask each supporting teacher to re-read mutated evidence in batches."""
    aliases = [item.alias for item in models]
    if len(aliases) != len(set(aliases)):
        raise ValueError("Perturbation model aliases must be unique")
    observations: list[PerturbationObservation] = []
    batches: list[PerturbationBatchRecord] = []
    for model in sorted(models, key=lambda item: item.alias):
        model_cases = [
            item for item in cases if model.alias in item.target_model_aliases
        ]
        if not model_cases:
            continue
        client = client_factory(model)
        for batch in _chunks(model_cases, batch_size):
            batch_identifier = _batch_id(model.alias, batch)
            case_ids = [item.case_id for item in batch]
            try:
                response = client.converse(
                    modelId=model.model_id,
                    system=[{"text": _SYSTEM_PROMPT}],
                    messages=[
                        {
                            "role": "user",
                            "content": [{"text": _prompt(batch)}],
                        }
                    ],
                    inferenceConfig={"temperature": 0.0, "maxTokens": 4000},
                )
            except Exception as error:
                outcome: PerturbationOutcome = "invocation_error"
                diagnostic = f"{error.__class__.__name__}: {error}"[:1000]
                batches.append(
                    PerturbationBatchRecord(
                        batch_id=batch_identifier,
                        model_alias=model.alias,
                        model_id=model.model_id,
                        case_ids=case_ids,
                        parse_status="invocation_error",
                        diagnostic=diagnostic,
                    )
                )
                observations.extend(
                    _evaluate_observation(
                        case=case,
                        model=model,
                        values=None,
                        fallback_outcome=outcome,
                        diagnostic=diagnostic,
                    )
                    for case in batch
                )
                continue
            usage = response.get("usage", {})
            batch_input_tokens = int(usage.get("inputTokens", 0))
            batch_output_tokens = int(usage.get("outputTokens", 0))
            response_text = _response_text(response)
            try:
                parsed, salvaged = _parse_results(response_text)
            except ValueError as error:
                diagnostic = str(error)[:1000]
                batches.append(
                    PerturbationBatchRecord(
                        batch_id=batch_identifier,
                        model_alias=model.alias,
                        model_id=model.model_id,
                        case_ids=case_ids,
                        parse_status="invalid",
                        response_text=response_text,
                        response_sha256=hashlib.sha256(
                            response_text.encode("utf-8")
                        ).hexdigest(),
                        stop_reason=response.get("stopReason"),
                        input_token_count=batch_input_tokens,
                        output_token_count=batch_output_tokens,
                        diagnostic=diagnostic,
                    )
                )
                observations.extend(
                    _evaluate_observation(
                        case=case,
                        model=model,
                        values=None,
                        fallback_outcome="invalid_result",
                        diagnostic=diagnostic,
                    )
                    for case in batch
                )
                continue
            expected_case_ids = {item.case_id for item in batch}
            unexpected = sorted(set(parsed) - expected_case_ids)
            unexpected_diagnostic = (
                "Response returned unexpected case IDs: " + ", ".join(unexpected)
                if unexpected
                else None
            )
            batches.append(
                PerturbationBatchRecord(
                    batch_id=batch_identifier,
                    model_alias=model.alias,
                    model_id=model.model_id,
                    case_ids=case_ids,
                    parse_status=(
                        "salvaged" if salvaged or unexpected else "valid"
                    ),
                    response_text=response_text,
                    response_sha256=hashlib.sha256(
                        response_text.encode("utf-8")
                    ).hexdigest(),
                    stop_reason=response.get("stopReason"),
                    input_token_count=batch_input_tokens,
                    output_token_count=batch_output_tokens,
                    diagnostic=unexpected_diagnostic,
                )
            )
            observations.extend(
                _evaluate_observation(
                    case=case,
                    model=model,
                    values=parsed.get(case.case_id),
                )
                for case in batch
            )

    return _finalize_run(
        cases=cases,
        batches=batches,
        observations=observations,
    )
