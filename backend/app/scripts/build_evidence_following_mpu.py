"""Build a non-overwriting, content-addressed evidence-following MPU artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.domain_adaptation.evidence_following_mpu import (
    MpuAnalysisReport,
    MpuDesign,
    MpuItemScore,
    MpuObservation,
    MpuPrompt,
    MpuStudyInput,
    analyze_mpu,
    build_mpu_design,
    score_mpu_observations,
)


MAX_STUDY_BYTES = 50_000_000
MAX_OBSERVATION_BYTES = 100_000_000


def _read_bounded(path: Path, limit: int) -> bytes:
    with path.open("rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError(f"MPU input must be a regular file: {path}")
        content = handle.read(limit + 1)
    if len(content) > limit:
        raise ValueError(f"MPU input exceeds {limit} bytes: {path}")
    return content


def _json_bytes(value: Any) -> bytes:
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


def _load_observations(path: Path | None) -> tuple[list[MpuObservation], bytes]:
    if path is None:
        return [], b""
    content = _read_bounded(path, MAX_OBSERVATION_BYTES)
    observations = [
        MpuObservation.model_validate_json(line)
        for line in content.decode("utf-8").splitlines()
        if line.strip()
    ]
    return observations, content


def build_evidence_following_mpu(
    *,
    input_path: str | Path,
    output_dir: str | Path,
    observations_path: str | Path | None = None,
) -> dict[str, object]:
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing MPU output: {output}")
    source = Path(input_path)
    source_bytes = _read_bounded(source, MAX_STUDY_BYTES)
    spec = MpuStudyInput.model_validate_json(source_bytes)
    observations_source = Path(observations_path) if observations_path else None
    observations, observations_bytes = _load_observations(observations_source)

    design = build_mpu_design(spec)
    scores = score_mpu_observations(spec, observations, design=design)
    report = analyze_mpu(
        spec,
        observations,
        design=design,
        scores=scores,
    )
    design_report = design.model_dump(mode="json", exclude={"prompts"})
    outputs = {
        Path("inputs/study.json"): source_bytes,
        Path("design/prompts.jsonl"): _jsonl_bytes(design.prompts),
        Path("design/design_report.json"): _json_bytes(design_report),
        Path("analysis/item_scores.jsonl"): _jsonl_bytes(scores),
        Path("reports/mpu_report.json"): _json_bytes(
            report.model_dump(mode="json")
        ),
        Path("schemas/study.schema.json"): _json_bytes(
            MpuStudyInput.model_json_schema()
        ),
        Path("schemas/prompt.schema.json"): _json_bytes(
            MpuPrompt.model_json_schema()
        ),
        Path("schemas/observation.schema.json"): _json_bytes(
            MpuObservation.model_json_schema()
        ),
        Path("schemas/item_score.schema.json"): _json_bytes(
            MpuItemScore.model_json_schema()
        ),
        Path("schemas/design.schema.json"): _json_bytes(
            MpuDesign.model_json_schema()
        ),
        Path("schemas/report.schema.json"): _json_bytes(
            MpuAnalysisReport.model_json_schema()
        ),
    }
    if observations_source is not None:
        outputs[Path("inputs/observations.jsonl")] = observations_bytes

    manifest = {
        "schema_version": "evidence-following-mpu-manifest-v0.1",
        "study_id": spec.study_id,
        "domains": spec.domains,
        "study_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "observations_sha256": (
            hashlib.sha256(observations_bytes).hexdigest()
            if observations_source is not None
            else None
        ),
        "files": {
            str(path): hashlib.sha256(content).hexdigest()
            for path, content in sorted(outputs.items(), key=lambda item: str(item[0]))
        },
        "claims_boundary": report.claims_boundary,
        "future_scope_exclusion": report.future_scope_exclusion,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(dir=output.parent, prefix=f".{output.name}.staging-")
    )
    try:
        for path, content in outputs.items():
            _write_new(staging / path, content)
        _write_new(staging / "manifest.json", _json_bytes(manifest))
        staging.replace(output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        "output_dir": str(output),
        "design_ready": design.ready,
        "analysis_ready": report.analysis_ready,
        "failed_gates": report.failed_gates,
        "prompt_count": len(design.prompts),
        "observation_count": len(observations),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the two-domain evidence-following MPU artifact."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--observations", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = build_evidence_following_mpu(
        input_path=args.input,
        observations_path=args.observations,
        output_dir=args.output_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
