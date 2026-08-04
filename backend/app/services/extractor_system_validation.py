"""Deterministic system-effectiveness checks for structured extraction."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

SYSTEM_EFFECTIVENESS_VERSION = "pas.extractor-system-effectiveness.v1"
RELEASE_MIN_RECORDS_PER_CASE = 20
SUPPORTED_CASE_TYPES = frozenset(
    {
        "standard",
        "hard_negative",
        "counterfactual",
        "cross_domain_transfer",
    }
)


@dataclass(frozen=True)
class EffectivenessPolicy:
    benchmark_tier: str
    required_case_types: tuple[str, ...]
    min_records_per_case: int
    min_domains: int


def audit_effectiveness_benchmark(
    benchmark_path: Path,
    policy: EffectivenessPolicy,
) -> dict:
    """Verify that the gold benchmark contains useful adversarial slices."""
    rows = _read_jsonl(benchmark_path)
    violations: list[dict] = []
    case_counts: Counter[str] = Counter()
    domain_counts: Counter[str] = Counter()
    seen_ids: set[str] = set()
    counterfactual_groups: dict[str, list[dict]] = defaultdict(list)

    if policy.benchmark_tier == "release":
        missing_case_types = sorted(
            SUPPORTED_CASE_TYPES - set(policy.required_case_types)
        )
        if missing_case_types:
            violations.append(
                {
                    "code": "release_policy_missing_case_types",
                    "case_types": missing_case_types,
                }
            )
        if policy.min_domains < 2:
            violations.append(
                {
                    "code": "release_policy_requires_multiple_domains",
                    "minimum": 2,
                }
            )
        if policy.min_records_per_case < RELEASE_MIN_RECORDS_PER_CASE:
            violations.append(
                {
                    "code": "release_policy_sample_floor_too_low",
                    "observed": policy.min_records_per_case,
                    "minimum": RELEASE_MIN_RECORDS_PER_CASE,
                }
            )

    for line_number, row in enumerate(rows, start=1):
        record_id = row.get("record_id")
        if not isinstance(record_id, str) or not record_id:
            violations.append(
                {"code": "missing_record_id", "line": line_number}
            )
        elif record_id in seen_ids:
            violations.append(
                {
                    "code": "duplicate_record_id",
                    "line": line_number,
                    "record_id": record_id,
                }
            )
        else:
            seen_ids.add(record_id)

        provenance = row.get("provenance")
        allowed_gold_kinds = (
            {"synthetic_smoke"}
            if policy.benchmark_tier == "smoke"
            else {"human_gold", "curated_real"}
        )
        if (
            not isinstance(provenance, dict)
            or provenance.get("source_split") != "test"
            or provenance.get("kind") not in allowed_gold_kinds
        ):
            violations.append(
                {
                    "code": "benchmark_not_independent_gold",
                    "line": line_number,
                }
            )

        case = row.get("evaluation_case")
        if not isinstance(case, dict):
            violations.append(
                {"code": "missing_evaluation_case", "line": line_number}
            )
            continue
        case_type = case.get("case_type")
        domain = case.get("domain")
        if case_type not in SUPPORTED_CASE_TYPES:
            violations.append(
                {
                    "code": "unsupported_case_type",
                    "line": line_number,
                    "value": case_type,
                }
            )
            continue
        if not isinstance(domain, str) or not domain.strip():
            violations.append(
                {"code": "missing_case_domain", "line": line_number}
            )
            continue

        case_counts[case_type] += 1
        domain_counts[domain.strip()] += 1
        target = row.get("target")
        if not isinstance(target, dict):
            violations.append(
                {"code": "missing_gold_target", "line": line_number}
            )
            continue

        if case_type == "hard_negative" and _has_asserted_claim(target):
            violations.append(
                {
                    "code": "hard_negative_has_positive_target",
                    "line": line_number,
                }
            )
        elif case_type == "counterfactual":
            pair_id = case.get("pair_id")
            if not isinstance(pair_id, str) or not pair_id:
                violations.append(
                    {
                        "code": "counterfactual_missing_pair_id",
                        "line": line_number,
                    }
                )
            else:
                counterfactual_groups[pair_id].append(row)
        elif case_type == "cross_domain_transfer":
            source_domain = case.get("source_domain")
            target_domain = case.get("target_domain")
            if (
                not isinstance(source_domain, str)
                or not source_domain
                or not isinstance(target_domain, str)
                or not target_domain
                or source_domain == target_domain
            ):
                violations.append(
                    {
                        "code": "invalid_cross_domain_pair",
                        "line": line_number,
                    }
                )
            if not _has_asserted_claim(target.get("transferable_pattern")):
                violations.append(
                    {
                        "code": "cross_domain_target_has_no_transfer_claim",
                        "line": line_number,
                    }
                )

    for case_type in policy.required_case_types:
        minimum = max(
            policy.min_records_per_case,
            2 if case_type == "counterfactual" else 1,
        )
        if case_counts[case_type] < minimum:
            violations.append(
                {
                    "code": "insufficient_case_records",
                    "case_type": case_type,
                    "observed": case_counts[case_type],
                    "minimum": minimum,
                }
            )
    if len(domain_counts) < policy.min_domains:
        violations.append(
            {
                "code": "insufficient_domains",
                "observed": len(domain_counts),
                "minimum": policy.min_domains,
            }
        )

    for pair_id, pair_rows in counterfactual_groups.items():
        if len(pair_rows) < 2:
            violations.append(
                {
                    "code": "incomplete_counterfactual_pair",
                    "pair_id": pair_id,
                }
            )
            continue
        target_hashes = {
            _content_hash(row.get("target")) for row in pair_rows
        }
        input_hashes = {
            _content_hash(row.get("input_text")) for row in pair_rows
        }
        if len(target_hashes) < 2 or len(input_hashes) < 2:
            violations.append(
                {
                    "code": "degenerate_counterfactual_pair",
                    "pair_id": pair_id,
                }
            )

    return {
        "validation_version": SYSTEM_EFFECTIVENESS_VERSION,
        "benchmark_tier": policy.benchmark_tier,
        "passed": not violations,
        "records": len(rows),
        "case_counts": dict(sorted(case_counts.items())),
        "domain_counts": dict(sorted(domain_counts.items())),
        "policy": {
            "benchmark_tier": policy.benchmark_tier,
            "required_case_types": list(policy.required_case_types),
            "min_records_per_case": policy.min_records_per_case,
            "min_domains": policy.min_domains,
        },
        "violations": violations,
    }


def evaluate_system_effectiveness(
    benchmark_path: Path,
    predictions_path: Path,
    verification_path: Path,
    policy: EffectivenessPolicy,
) -> dict:
    """Recompute adversarial and domain-slice metrics from record-level outputs."""
    audit = audit_effectiveness_benchmark(benchmark_path, policy)
    benchmark = _read_jsonl(benchmark_path)
    predictions = _index_unique(_read_jsonl(predictions_path), "predictions")
    verification = _index_unique(
        _read_jsonl(verification_path),
        "verification records",
    )
    expected_ids = {str(row.get("record_id")) for row in benchmark}
    coverage_passed = (
        set(predictions) == expected_ids
        and set(verification) == expected_ids
    )
    if not coverage_passed:
        return {
            "validation_version": SYSTEM_EFFECTIVENESS_VERSION,
            "passed": False,
            "benchmark": audit,
            "metrics": {},
            "violations": [
                {
                    "code": "system_evaluation_coverage_mismatch",
                    "expected": sorted(expected_ids),
                    "predictions": sorted(predictions),
                    "verification": sorted(verification),
                }
            ],
        }

    case_results: dict[str, list[bool]] = defaultdict(list)
    domain_results: dict[str, list[bool]] = defaultdict(list)
    counterfactual_results: dict[str, list[bool]] = defaultdict(list)
    counterfactual_predictions: dict[str, set[str]] = defaultdict(set)
    hard_negative_claim_false_positives = 0
    hard_negative_false_positives = 0
    verifier_agreement: list[bool] = []
    verifier_positive: list[bool] = []

    for row in benchmark:
        record_id = str(row["record_id"])
        case = row["evaluation_case"]
        case_type = str(case["case_type"])
        domain = str(case["domain"])
        prediction = predictions[record_id].get("prediction")
        is_correct = _content_hash(prediction) == _content_hash(row["target"])
        verifier_correct = verification[record_id].get("is_correct") is True
        verifier_agreement.append(verifier_correct == is_correct)
        verifier_positive.append(verifier_correct)
        case_results[case_type].append(is_correct)
        domain_results[domain].append(is_correct)

        if case_type == "hard_negative":
            if _has_asserted_claim(prediction):
                hard_negative_claim_false_positives += 1
            if _has_asserted_claim(
                prediction.get("transferable_pattern")
                if isinstance(prediction, dict)
                else None
            ):
                hard_negative_false_positives += 1
        elif case_type == "counterfactual":
            pair_id = str(case["pair_id"])
            counterfactual_results[pair_id].append(is_correct)
            counterfactual_predictions[pair_id].add(
                _content_hash(prediction)
            )

    case_accuracy = {
        case_type: _accuracy(values)
        for case_type, values in sorted(case_results.items())
    }
    domain_accuracy = {
        domain: _accuracy(values)
        for domain, values in sorted(domain_results.items())
    }
    counterfactual_pair_accuracy = _accuracy(
        [all(values) for values in counterfactual_results.values()]
    )
    counterfactual_sensitivity = _accuracy(
        [
            len(counterfactual_predictions[pair_id]) > 1
            for pair_id in counterfactual_results
        ]
    )
    hard_negative_count = len(case_results.get("hard_negative", []))
    hard_negative_claim_false_positive_rate = (
        round(hard_negative_claim_false_positives / hard_negative_count, 6)
        if hard_negative_count
        else None
    )
    hard_negative_false_positive_rate = (
        round(hard_negative_false_positives / hard_negative_count, 6)
        if hard_negative_count
        else None
    )
    all_results = [
        value for values in case_results.values() for value in values
    ]
    metrics = {
        "overall_accuracy": _accuracy(all_results),
        "gold_exact_match_accuracy": _accuracy(all_results),
        "verifier_gold_exact_agreement": _accuracy(verifier_agreement),
        "verifier_positive_rate": _accuracy(verifier_positive),
        "standard_accuracy": case_accuracy.get("standard"),
        "hard_negative_accuracy": case_accuracy.get("hard_negative"),
        "hard_negative_claim_false_positive_rate": (
            hard_negative_claim_false_positive_rate
        ),
        "hard_negative_transfer_false_positive_rate": (
            hard_negative_false_positive_rate
        ),
        "counterfactual_pair_accuracy": counterfactual_pair_accuracy,
        "counterfactual_sensitivity": counterfactual_sensitivity,
        "cross_domain_transfer_accuracy": case_accuracy.get(
            "cross_domain_transfer"
        ),
        "worst_domain_accuracy": (
            min(domain_accuracy.values()) if domain_accuracy else None
        ),
        "case_accuracy": case_accuracy,
        "domain_accuracy": domain_accuracy,
    }
    return {
        "validation_version": SYSTEM_EFFECTIVENESS_VERSION,
        "passed": audit["passed"] and coverage_passed,
        "benchmark": audit,
        "metrics": metrics,
        "violations": [],
    }


def _index_unique(rows: list[dict], label: str) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for row in rows:
        record_id = row.get("record_id")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError(f"{label} contain a missing record_id")
        if record_id in indexed:
            raise ValueError(f"{label} contain duplicate record_id {record_id!r}")
        indexed[record_id] = row
    return indexed


def _has_asserted_claim(value) -> bool:
    if isinstance(value, dict):
        claim_fields = {"value", "canonical_concept", "surface_form"}
        if claim_fields & value.keys():
            return any(value.get(field) is not None for field in claim_fields)
        return any(
            _has_asserted_claim(child)
            for name, child in value.items()
            if name not in {"evidence_spans", "assumptions"}
        )
    if isinstance(value, list):
        return any(_has_asserted_claim(child) for child in value)
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None


def _accuracy(values: list[bool]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 6)


def _content_hash(value) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number} must contain a JSON object")
        rows.append(value)
    return rows
