"""Create non-overwriting RAG review queues from a domain package."""

from __future__ import annotations

import argparse
import json
import tempfile
from collections import Counter
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from app.domain_adaptation.models import ProtocolUnit, ScientificChunk
from app.domain_adaptation.rag import (
    RagGoldQuestion,
    RagPrediction,
    RagQuestionCandidate,
    StructuredRagBaseline,
    build_rag_review_queue,
)


ModelType = TypeVar("ModelType", bound=BaseModel)


def _read_jsonl(path: Path, model_type: type[ModelType]) -> list[ModelType]:
    rows: list[ModelType] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if model_type in {ProtocolUnit, ScientificChunk}:
            payload.pop("schema_version", None)
        rows.append(model_type.model_validate(payload))
    return rows


def _jsonl_bytes(rows: list[dict]) -> bytes:
    return "".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
        for row in rows
    ).encode("utf-8")


def _json_bytes(value: dict) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
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


def prepare_rag_evaluation(
    package_dir: str | Path, *, limit: int = 50
) -> dict[str, int]:
    package = Path(package_dir)
    protocols = _read_jsonl(
        package / "knowledge/protocols.jsonl", ProtocolUnit
    )
    scientific_chunks = _read_jsonl(
        package / "knowledge/scientific_chunks.jsonl", ScientificChunk
    )
    candidates, gold_questions = build_rag_review_queue(
        protocols, scientific_chunks, limit=limit
    )
    baseline = StructuredRagBaseline(scientific_chunks, protocols)
    predictions = [
        baseline.answer(candidate.question, top_k=5)
        for candidate in candidates
    ]
    readiness = {
        "schema_version": "domain-adapter-rag-readiness-v0.2",
        "candidate_question_count": len(candidates),
        "human_reviewed_question_count": 0,
        "pending_gold_question_count": len(gold_questions),
        "question_type_counts": dict(
            sorted(
                Counter(
                    item.question.question_type for item in candidates
                ).items()
            )
        ),
        "evidence_scope_counts": dict(
            sorted(
                Counter(
                    evidence_scope
                    for item in candidates
                    for evidence_scope in item.question.evidence_scope_filters
                ).items()
            )
        ),
        "protocol_count": len(
            {
                protocol_id
                for item in candidates
                for protocol_id in item.source_protocol_ids
            }
        ),
        "paper_count": len(
            {
                paper_id
                for item in candidates
                for paper_id in item.question.paper_ids
            }
        ),
        "baseline_system_id": baseline.system_id,
        "baseline_prediction_count": len(predictions),
        "scientific_accuracy_metrics": None,
        "claims_boundary": (
            "Candidate answers and baseline predictions are review aids. "
            "Scientific metrics remain null until source-first human gold is "
            "reviewed and annotation-complete."
        ),
    }
    outputs = {
        package / "rag/candidate_questions.jsonl": _jsonl_bytes(
            [item.model_dump(mode="json") for item in candidates]
        ),
        package / "gold/rag_questions.jsonl": _jsonl_bytes(
            [item.model_dump(mode="json") for item in gold_questions]
        ),
        package / "rag/baseline_predictions.jsonl": _jsonl_bytes(
            [item.model_dump(mode="json") for item in predictions]
        ),
        package / "rag/schemas/candidate_questions.schema.json": _json_bytes(
            RagQuestionCandidate.model_json_schema()
        ),
        package / "gold/schemas/rag_questions.schema.json": _json_bytes(
            RagGoldQuestion.model_json_schema()
        ),
        package / "rag/schemas/predictions.schema.json": _json_bytes(
            RagPrediction.model_json_schema()
        ),
        package / "reports/rag_readiness.json": _json_bytes(readiness),
    }
    existing = [str(path) for path in outputs if path.exists()]
    if existing:
        raise FileExistsError(
            "Refusing to overwrite existing RAG review files: "
            + ", ".join(existing)
        )
    for path, content in outputs.items():
        _write_new(path, content)
    return {
        "baseline_prediction_count": len(predictions),
        "candidate_question_count": len(candidates),
        "pending_gold_question_count": len(gold_questions),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create pending source-first RAG review artifacts."
    )
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=50)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = prepare_rag_evaluation(args.package, limit=args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
