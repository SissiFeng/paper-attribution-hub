"""Compile experiment-run JSON into a deterministic evidence package."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from app.domain_adaptation.experimental_feedback import (
    ExperimentalEvidenceCompilationSpec,
    compile_experimental_evidence,
)


def _json_bytes(value: dict) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _write_if_changed(path: Path, content: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == content:
        return False
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
    return True


def compile_experimental_feedback_file(
    input_path: str | Path,
    output_path: str | Path,
) -> dict[str, object]:
    spec = ExperimentalEvidenceCompilationSpec.model_validate_json(
        Path(input_path).read_text(encoding="utf-8")
    )
    bundle = compile_experimental_evidence(
        spec.runs,
        package_id=spec.package_id,
        package_version=spec.package_version,
    )
    destination = Path(output_path)
    changed = _write_if_changed(
        destination,
        _json_bytes(bundle.model_dump(mode="json")),
    )
    return {
        "output_path": str(destination),
        "changed": changed,
        "package": bundle.package.coordinate,
        "run_count": len(bundle.source_runs),
        "evidence_record_count": len(bundle.records),
        "content_sha256": bundle.content_sha256,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compile content-addressed experimental feedback evidence."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = compile_experimental_feedback_file(args.input, args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
