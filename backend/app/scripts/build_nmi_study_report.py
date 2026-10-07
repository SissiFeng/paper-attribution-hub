"""Build a deterministic, fail-closed NMI evidence-readiness report."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from app.domain_adaptation.nmi_study import (
    NmiStudyInput,
    evaluate_nmi_readiness,
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


def build_nmi_study_report(
    input_path: str | Path,
    output_path: str | Path,
) -> dict[str, object]:
    spec = NmiStudyInput.model_validate_json(
        Path(input_path).read_text(encoding="utf-8")
    )
    report = evaluate_nmi_readiness(
        spec.domains,
        spec.policy,
        transfer_comparisons=spec.transfer_comparisons,
    )
    destination = Path(output_path)
    changed = _write_if_changed(
        destination,
        _json_bytes(report.model_dump(mode="json")),
    )
    return {
        "output_path": str(destination),
        "changed": changed,
        "meets_evidence_policy": report.meets_evidence_policy,
        "failed_global_gates": report.failed_global_gates,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a fail-closed cross-domain NMI readiness report."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = build_nmi_study_report(args.input, args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
