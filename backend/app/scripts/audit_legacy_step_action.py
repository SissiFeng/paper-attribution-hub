"""Quantify the legacy whole-sentence step-action contamination."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any, Callable


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _rate(passed: int, total: int) -> float | None:
    return round(passed / total, 6) if total else None


def _result_metrics(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    numeric = [
        item
        for item in rows
        if item.get("numeric_replacement_passed") is not None
    ]
    deletion_passed = sum(
        item.get("evidence_deletion_passed") is True for item in rows
    )
    numeric_passed = sum(
        item.get("numeric_replacement_passed") is True for item in numeric
    )
    return {
        "evidence_deletion": {
            "passed": deletion_passed,
            "total": len(rows),
            "rate": _rate(deletion_passed, len(rows)),
        },
        "numeric_replacement": {
            "passed": numeric_passed,
            "total": len(numeric),
            "rate": _rate(numeric_passed, len(numeric)),
        },
    }


def _slot_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = sum(item["status"] == "accepted" for item in rows)
    failed = sum(item.get("reasons") == ["perturbation_failed"] for item in rows)
    not_verified = sum(
        item.get("reasons") == ["perturbation_not_verified"] for item in rows
    )
    evaluated = accepted + failed + not_verified
    return {
        "accepted": accepted,
        "perturbation_failed": failed,
        "perturbation_not_verified": not_verified,
        "evaluated_slot_count": evaluated,
        "failure_share_of_evaluated": _rate(failed, evaluated),
    }


def _write_new(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing audit: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary_path = Path(temporary.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def audit_legacy_step_action(
    legacy_artifact_dir: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    """Recompute counterfactual and consensus slices around legacy action."""
    root = Path(legacy_artifact_dir)
    consensus = root / "consensus"
    cases = _read_jsonl(consensus / "perturbation_cases.jsonl")
    results = _read_jsonl(consensus / "perturbation_results.jsonl")

    decision_fields: dict[str, tuple[str, str]] = {}
    for case in cases:
        decision_id = str(case["decision_id"])
        field = (str(case["entity_type"]), str(case["field_name"]))
        previous = decision_fields.setdefault(decision_id, field)
        if previous != field:
            raise ValueError("One perturbation decision maps to multiple fields")
    unknown_results = [
        item for item in results if item["decision_id"] not in decision_fields
    ]
    if unknown_results:
        raise ValueError("Perturbation results contain decisions without cases")

    decisions: list[dict[str, Any]] = []
    for status, filename in (
        ("accepted", "accepted_silver.jsonl"),
        ("disputed", "disputed_claims.jsonl"),
    ):
        for item in _read_jsonl(consensus / filename):
            decisions.append({**item, "status": status})

    predicates: dict[str, Callable[[str, str], bool]] = {
        "action": lambda entity, field: entity == "steps" and field == "action",
        "non_action": lambda entity, field: not (
            entity == "steps" and field == "action"
        ),
        "non_steps": lambda entity, _field: entity != "steps",
        "legacy_step_non_action": lambda entity, field: (
            entity == "steps" and field != "action"
        ),
    }
    result_slices: dict[str, dict[str, Any]] = {}
    slot_slices: dict[str, dict[str, Any]] = {}
    for name, predicate in predicates.items():
        sliced_results = [
            item
            for item in results
            if predicate(*decision_fields[str(item["decision_id"])])
        ]
        result_slices[name] = _result_metrics(sliced_results)
        sliced_decisions = [
            item
            for item in decisions
            if predicate(str(item["entity_type"]), str(item["field_name"]))
            and (
                item["status"] == "accepted"
                or item.get("reasons")
                in (["perturbation_failed"], ["perturbation_not_verified"])
            )
        ]
        slot_slices[name] = _slot_metrics(sliced_decisions)

    report = {
        "schema_version": "legacy-step-action-contamination-audit-v0.1",
        "legacy_artifact_dir": str(root),
        "counterfactual_results": result_slices,
        "consensus_slots": slot_slices,
        "claims_boundary": (
            "Legacy whole-sentence steps.action results are contaminated by a "
            "field-granularity bug and must not support scientific claims. "
            "Non-action and non-step slices are descriptive re-analyses, not gold accuracy."
        ),
    }
    _write_new(Path(output_path), report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit whole-sentence legacy action contamination."
    )
    parser.add_argument("--legacy-artifact-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = audit_legacy_step_action(args.legacy_artifact_dir, args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
