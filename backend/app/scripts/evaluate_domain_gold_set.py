"""Score reviewed domain-adapter annotations against candidate claims."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from app.domain_adaptation.gold import (
    CandidateClaim,
    GoldEntityAnnotation,
    GoldProtocolAnnotation,
    GoldScoreReport,
    score_gold_entities,
)
from app.domain_adaptation.evidence_dependency import (
    EvidenceDependencyAnnotation,
    summarize_evidence_dependency_annotations,
)


ModelType = TypeVar("ModelType", bound=BaseModel)


def _read_jsonl(path: Path, model_type: type[ModelType]) -> list[ModelType]:
    return [
        model_type.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_report(path: Path, report: GoldScoreReport) -> None:
    content = (
        json.dumps(
            report.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
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


def _write_json_report(path: Path, value: dict) -> None:
    content = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
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


def evaluate_gold_set(package_dir: str | Path) -> GoldScoreReport:
    package_path = Path(package_dir)
    gold_protocols = _read_jsonl(
        package_path / "gold/gold_protocols.jsonl",
        GoldProtocolAnnotation,
    )
    candidate_claims = _read_jsonl(
        package_path / "gold/candidate_claims.jsonl",
        CandidateClaim,
    )
    dependency_summary = summarize_evidence_dependency_annotations(
        annotations=_read_jsonl(
            package_path / "gold/evidence_dependencies.jsonl",
            EvidenceDependencyAnnotation,
        ),
        gold_protocols=gold_protocols,
        candidate_claims=candidate_claims,
    )
    report = score_gold_entities(
        gold_protocols=gold_protocols,
        gold_entities=_read_jsonl(
            package_path / "gold/gold_entities.jsonl",
            GoldEntityAnnotation,
        ),
        candidate_claims=candidate_claims,
    )
    _write_report(package_path / "reports/gold_score.json", report)
    _write_json_report(
        package_path / "reports/evidence_dependency_summary.json",
        dependency_summary,
    )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score completed human gold annotations."
    )
    parser.add_argument("--package", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = evaluate_gold_set(args.package)
    print(
        json.dumps(
            report.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
