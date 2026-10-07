"""Build a non-overwriting Experiment A design artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.domain_adaptation.memory_evidence_experiment import (
    ExperimentAAnalysisPlan,
    ExperimentADesignInput,
    ExperimentADesignReport,
    ExperimentAStratumAssignment,
    build_experiment_a_design,
)


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _jsonl_bytes(rows: list[BaseModel]) -> bytes:
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


def build_memory_evidence_experiment(
    input_path: str | Path,
    output_dir: str | Path,
) -> dict[str, object]:
    output = Path(output_dir)
    if output.exists() and any(output.rglob("*")):
        raise FileExistsError(
            f"Refusing to overwrite existing Experiment A output: {output}"
        )
    source = Path(input_path)
    spec = ExperimentADesignInput.model_validate_json(
        source.read_text(encoding="utf-8")
    )
    design = build_experiment_a_design(spec)
    outputs = {
        output / "design/assignments.jsonl": _jsonl_bytes(design.assignments),
        output / "design/analysis_plan.json": _json_bytes(
            design.analysis_plan.model_dump(mode="json")
        ),
        output / "reports/design_report.json": _json_bytes(
            design.report.model_dump(mode="json")
        ),
        output / "schemas/input.schema.json": _json_bytes(
            ExperimentADesignInput.model_json_schema()
        ),
        output / "schemas/assignment.schema.json": _json_bytes(
            ExperimentAStratumAssignment.model_json_schema()
        ),
        output / "schemas/analysis_plan.schema.json": _json_bytes(
            ExperimentAAnalysisPlan.model_json_schema()
        ),
        output / "schemas/design_report.schema.json": _json_bytes(
            ExperimentADesignReport.model_json_schema()
        ),
    }
    for path, content in outputs.items():
        _write_new(path, content)
    manifest = {
        "schema_version": "memory-evidence-experiment-manifest-v0.1",
        "experiment_id": spec.experiment_id,
        "domain": spec.domain,
        "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "files": {
            str(path.relative_to(output)): hashlib.sha256(content).hexdigest()
            for path, content in sorted(outputs.items(), key=lambda item: str(item[0]))
        },
        "claims_boundary": design.analysis_plan.claims_boundary,
    }
    _write_new(output / "manifest.json", _json_bytes(manifest))
    return {
        "output_dir": str(output),
        "ready": design.report.ready,
        "failed_gates": design.report.failed_gates,
        "assignment_count": len(design.assignments),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the stratified memory-versus-evidence Experiment A design."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = build_memory_evidence_experiment(args.input, args.output_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
