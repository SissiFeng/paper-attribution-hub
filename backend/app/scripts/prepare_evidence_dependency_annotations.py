"""Create a non-overwriting field-level evidence-dependency review queue."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from app.domain_adaptation.evidence_dependency import (
    EvidenceDependencyAnnotation,
    build_evidence_dependency_annotations,
    summarize_evidence_dependency_annotations,
)
from app.domain_adaptation.gold import CandidateClaim, GoldProtocolAnnotation
from app.domain_adaptation.models import ProtocolUnit


ModelType = TypeVar("ModelType", bound=BaseModel)


def _read_jsonl(path: Path, model_type: type[ModelType]) -> list[ModelType]:
    rows: list[ModelType] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if model_type is ProtocolUnit:
            payload.pop("schema_version", None)
        rows.append(model_type.model_validate(payload))
    return rows


def _json_bytes(value: dict) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _jsonl_bytes(rows: list[dict]) -> bytes:
    return "".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
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


def prepare_evidence_dependency_annotations(
    package_dir: str | Path,
) -> dict[str, int]:
    package = Path(package_dir)
    protocols = _read_jsonl(
        package / "knowledge/protocols.jsonl", ProtocolUnit
    )
    candidate_claims = _read_jsonl(
        package / "gold/candidate_claims.jsonl", CandidateClaim
    )
    gold_protocols = _read_jsonl(
        package / "gold/gold_protocols.jsonl", GoldProtocolAnnotation
    )
    annotations = build_evidence_dependency_annotations(
        protocols, candidate_claims
    )
    summary = summarize_evidence_dependency_annotations(
        annotations=annotations,
        gold_protocols=gold_protocols,
        candidate_claims=candidate_claims,
    )
    outputs = {
        package / "gold/evidence_dependencies.jsonl": _jsonl_bytes(
            [item.model_dump(mode="json") for item in annotations]
        ),
        package
        / "gold/schemas/evidence_dependencies.schema.json": _json_bytes(
            EvidenceDependencyAnnotation.model_json_schema()
        ),
        package / "reports/evidence_dependency_summary.json": _json_bytes(
            summary
        ),
    }
    existing = [str(path) for path in outputs if path.exists()]
    if existing:
        raise FileExistsError(
            "Refusing to overwrite existing evidence-dependency files: "
            + ", ".join(existing)
        )
    for path, content in outputs.items():
        _write_new(path, content)
    return {
        "annotation_count": summary["annotation_count"],
        "pending_count": summary["pending_count"],
        "reviewed_count": summary["reviewed_count"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create field-level evidence-dependency annotations."
    )
    parser.add_argument("--package", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = prepare_evidence_dependency_annotations(args.package)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
