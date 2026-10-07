"""Run bounded, fail-closed counterfactual checks against Bedrock teachers."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.domain_adaptation.consensus import (
    ClaimPerturbationCase,
    ModelClaimPerturbationResult,
)
from app.domain_adaptation.model_benchmark import (
    TeacherModelCandidate,
    load_benchmark_spec,
)
from app.domain_adaptation.perturbation import (
    PerturbationBatchRecord,
    PerturbationEvaluationRun,
    PerturbationObservation,
    evaluate_perturbation_cases,
)
from app.scripts.benchmark_domain_teachers import DEFAULT_SPEC


def _json_bytes(value: dict) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _jsonl_bytes(rows: Sequence[BaseModel]) -> bytes:
    return "".join(
        json.dumps(
            row.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
        for row in rows
    ).encode("utf-8")


def _write_new(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _select_cases(
    cases: list[ClaimPerturbationCase],
    *,
    max_decisions: int | None,
) -> list[ClaimPerturbationCase]:
    if max_decisions is None:
        return sorted(cases, key=lambda item: (item.decision_id, item.case_id))
    if max_decisions < 1:
        raise ValueError("max_decisions must be positive")
    selected_decisions = set(
        sorted({item.decision_id for item in cases})[:max_decisions]
    )
    return sorted(
        (item for item in cases if item.decision_id in selected_decisions),
        key=lambda item: (item.decision_id, item.case_id),
    )


def run_teacher_perturbation_artifacts(
    *,
    cases: list[ClaimPerturbationCase],
    models: list[TeacherModelCandidate],
    output_dir: str | Path,
    client_factory: Callable[[TeacherModelCandidate], Any],
    max_decisions: int | None = None,
    batch_size: int = 20,
) -> dict:
    """Evaluate a deterministic decision subset and write new artifacts."""
    output = Path(output_dir)
    if output.exists() and any(output.rglob("*")):
        raise FileExistsError(
            f"Refusing to overwrite existing perturbation output: {output}"
        )
    selected_cases = _select_cases(cases, max_decisions=max_decisions)
    run = evaluate_perturbation_cases(
        cases=selected_cases,
        models=models,
        client_factory=client_factory,
        batch_size=batch_size,
    )
    return write_teacher_perturbation_artifacts(
        cases=selected_cases,
        models=models,
        run=run,
        output_dir=output_dir,
    )


def write_teacher_perturbation_artifacts(
    *,
    cases: list[ClaimPerturbationCase],
    models: list[TeacherModelCandidate],
    run: PerturbationEvaluationRun,
    output_dir: str | Path,
) -> dict:
    """Persist a completed live or replayed perturbation run."""
    output = Path(output_dir)
    paths = {
        "cases": output / "cases.jsonl",
        "batches": output / "batches.jsonl",
        "observations": output / "observations.jsonl",
        "results": output / "model_results.jsonl",
        "report": output / "report.json",
        "observation_schema": output / "schemas/observations.schema.json",
        "batch_schema": output / "schemas/batches.schema.json",
        "result_schema": output / "schemas/model_results.schema.json",
    }
    existing = [str(path) for path in paths.values() if path.exists()]
    if existing:
        raise FileExistsError(
            "Refusing to overwrite existing perturbation files: "
            + ", ".join(existing)
        )
    report = run.report.model_dump(mode="json")
    report["model_aliases"] = sorted(item.alias for item in models)
    report["selected_decision_count"] = len(
        {item.decision_id for item in cases}
    )
    outputs = {
        paths["cases"]: _jsonl_bytes(cases),
        paths["batches"]: _jsonl_bytes(run.batches),
        paths["observations"]: _jsonl_bytes(run.observations),
        paths["results"]: _jsonl_bytes(run.results),
        paths["report"]: _json_bytes(report),
        paths["observation_schema"]: _json_bytes(
            PerturbationObservation.model_json_schema()
        ),
        paths["batch_schema"]: _json_bytes(
            PerturbationBatchRecord.model_json_schema()
        ),
        paths["result_schema"]: _json_bytes(
            ModelClaimPerturbationResult.model_json_schema()
        ),
    }
    for path, content in outputs.items():
        _write_new(path, content)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run claim-level counterfactual checks with Bedrock models."
    )
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        help="Benchmark model alias; repeat to run a subset.",
    )
    parser.add_argument("--max-decisions", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument(
        "--aws-profile", default=os.getenv("AWS_PROFILE", "pas-sdl0-dev")
    )
    parser.add_argument("--read-timeout", type=int, default=120)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    spec = load_benchmark_spec(args.spec)
    requested_aliases = set(args.model)
    models = [
        item
        for item in spec.models
        if not requested_aliases or item.alias in requested_aliases
    ]
    missing_aliases = sorted(
        requested_aliases - {item.alias for item in models}
    )
    if missing_aliases:
        raise ValueError(
            "Unknown benchmark model aliases: " + ", ".join(missing_aliases)
        )
    cases = [
        ClaimPerturbationCase.model_validate_json(line)
        for line in args.cases.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    import boto3  # type: ignore[import-untyped]
    from botocore.config import Config  # type: ignore[import-untyped]

    session = boto3.Session(profile_name=args.aws_profile)
    clients: dict[str, Any] = {}

    def client_factory(model: TeacherModelCandidate):
        if model.region not in clients:
            clients[model.region] = session.client(
                "bedrock-runtime",
                region_name=model.region,
                config=Config(
                    connect_timeout=10,
                    read_timeout=args.read_timeout,
                    retries={"total_max_attempts": 2, "mode": "standard"},
                ),
            )
        return clients[model.region]

    report = run_teacher_perturbation_artifacts(
        cases=cases,
        models=models,
        output_dir=args.output,
        client_factory=client_factory,
        max_decisions=args.max_decisions,
        batch_size=args.batch_size,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
