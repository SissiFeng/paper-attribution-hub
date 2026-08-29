"""Score source-first RAG predictions against completed human gold."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from app.domain_adaptation.models import ProtocolUnit
from app.domain_adaptation.rag import (
    RagGoldQuestion,
    RagPrediction,
    RagScoreReport,
    score_rag_predictions,
)


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


def _write_report(path: Path, report: RagScoreReport) -> None:
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


def evaluate_rag_set(
    package_dir: str | Path,
    *,
    predictions_path: str | Path | None = None,
    retrieval_k: int = 5,
) -> RagScoreReport:
    package = Path(package_dir)
    predictions = Path(predictions_path) if predictions_path else (
        package / "rag/baseline_predictions.jsonl"
    )
    report = score_rag_predictions(
        gold_questions=_read_jsonl(
            package / "gold/rag_questions.jsonl", RagGoldQuestion
        ),
        predictions=_read_jsonl(predictions, RagPrediction),
        protocols=_read_jsonl(
            package / "knowledge/protocols.jsonl", ProtocolUnit
        ),
        retrieval_k=retrieval_k,
    )
    _write_report(package / "reports/rag_eval.json", report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score RAG predictions against completed human gold."
    )
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, default=None)
    parser.add_argument("--retrieval-k", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = evaluate_rag_set(
        args.package,
        predictions_path=args.predictions,
        retrieval_k=args.retrieval_k,
    )
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
