"""Create non-overwriting human-review queues for a domain adapter package."""

from __future__ import annotations

import argparse
import json
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from app.domain_adaptation.gold import (
    CandidateClaim,
    GoldEntityAnnotation,
    GoldProtocolAnnotation,
    build_candidate_claims,
    build_gold_annotation_queue,
)
from app.domain_adaptation.evidence_dependency import (
    EvidenceDependencyAnnotation,
    build_evidence_dependency_annotations,
    summarize_evidence_dependency_annotations,
)
from app.domain_adaptation.models import ProtocolUnit


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


def _round_robin_by_paper(
    protocols: list[ProtocolUnit], limit: int
) -> list[ProtocolUnit]:
    by_paper: dict[str, list[ProtocolUnit]] = defaultdict(list)
    for protocol in sorted(protocols, key=lambda item: item.protocol_id):
        by_paper[protocol.paper_id].append(protocol)
    selected: list[ProtocolUnit] = []
    while len(selected) < limit and any(by_paper.values()):
        for paper_id in sorted(by_paper):
            if by_paper[paper_id] and len(selected) < limit:
                selected.append(by_paper[paper_id].pop(0))
    return selected


def _review_batch(
    protocols: list[ProtocolUnit],
    candidate_counts: Counter[str],
    limit: int = 20,
) -> list[ProtocolUnit]:
    primary = [
        protocol
        for protocol in protocols
        if protocol.evidence_scope == "primary_report"
    ]
    selected = _round_robin_by_paper(primary, limit)
    selected_ids = {item.protocol_id for item in selected}
    controls = sorted(
        (
            protocol
            for protocol in protocols
            if protocol.protocol_id not in selected_ids
        ),
        key=lambda item: (
            candidate_counts[item.protocol_id],
            item.paper_id,
            item.protocol_id,
        ),
    )
    selected.extend(controls[: max(0, limit - len(selected))])
    return selected


def _review_batch_payload(
    protocols: list[ProtocolUnit], candidates: list[CandidateClaim]
) -> dict:
    candidate_counts = Counter(
        candidate.protocol_id for candidate in candidates
    )
    review_batch = _review_batch(protocols, candidate_counts)
    protocol_ids = [item.protocol_id for item in review_batch]
    return {
        "schema_version": "domain-adapter-gold-review-batch-v0.1",
        "selection_strategy": (
            "primary-report protocols round-robin by paper, then "
            "lowest-claim-count controls"
        ),
        "protocol_ids": protocol_ids,
        "paper_ids": sorted({item.paper_id for item in review_batch}),
        "protocol_count": len(review_batch),
        "candidate_claim_count": sum(
            candidate_counts[protocol_id] for protocol_id in protocol_ids
        ),
    }


def _load_protocols(protocol_path: Path) -> list[ProtocolUnit]:
    protocols: list[ProtocolUnit] = []
    for line in protocol_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        row.pop("schema_version", None)
        protocols.append(ProtocolUnit.model_validate(row))
    return protocols


def prepare_review_batch(package_dir: str | Path) -> dict[str, int]:
    package_path = Path(package_dir)
    protocols = _load_protocols(
        package_path / "knowledge/protocols.jsonl"
    )
    candidates = [
        CandidateClaim.model_validate(json.loads(line))
        for line in (package_path / "gold/candidate_claims.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    payload = _review_batch_payload(protocols, candidates)
    output_path = package_path / "gold/review_batch_001.json"
    if output_path.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing review batch: {output_path}"
        )
    _write_new(output_path, _json_bytes(payload))
    return {
        "review_batch_candidate_claim_count": payload[
            "candidate_claim_count"
        ],
        "review_batch_protocol_count": payload["protocol_count"],
    }


def prepare_gold_set(package_dir: str | Path) -> dict[str, int]:
    package_path = Path(package_dir)
    protocol_path = package_path / "knowledge/protocols.jsonl"
    protocols = _load_protocols(protocol_path)

    candidates = build_candidate_claims(protocols)
    protocol_queue, entity_queue = build_gold_annotation_queue(protocols)
    dependency_queue = build_evidence_dependency_annotations(
        protocols, candidates
    )
    dependency_summary = summarize_evidence_dependency_annotations(
        annotations=dependency_queue,
        gold_protocols=protocol_queue,
        candidate_claims=candidates,
    )
    review_batch_payload = _review_batch_payload(protocols, candidates)
    outputs = {
        package_path / "gold/candidate_claims.jsonl": _jsonl_bytes(
            [item.model_dump(mode="json") for item in candidates]
        ),
        package_path / "gold/gold_protocols.jsonl": _jsonl_bytes(
            [item.model_dump(mode="json") for item in protocol_queue]
        ),
        package_path / "gold/gold_entities.jsonl": _jsonl_bytes(
            [item.model_dump(mode="json") for item in entity_queue]
        ),
        package_path / "gold/evidence_dependencies.jsonl": _jsonl_bytes(
            [item.model_dump(mode="json") for item in dependency_queue]
        ),
        package_path
        / "gold/schemas/candidate_claims.schema.json": _json_bytes(
            CandidateClaim.model_json_schema()
        ),
        package_path
        / "gold/schemas/gold_protocols.schema.json": _json_bytes(
            GoldProtocolAnnotation.model_json_schema()
        ),
        package_path
        / "gold/schemas/gold_entities.schema.json": _json_bytes(
            GoldEntityAnnotation.model_json_schema()
        ),
        package_path
        / "gold/schemas/evidence_dependencies.schema.json": _json_bytes(
            EvidenceDependencyAnnotation.model_json_schema()
        ),
        package_path / "reports/evidence_dependency_summary.json": _json_bytes(
            dependency_summary
        ),
        package_path / "gold/review_batch_001.json": _json_bytes(
            review_batch_payload
        ),
    }
    existing = [str(path) for path in outputs if path.exists()]
    if existing:
        raise FileExistsError(
            "Refusing to overwrite existing gold review files: "
            + ", ".join(existing)
        )
    for path, content in outputs.items():
        _write_new(path, content)
    return {
        "candidate_claim_count": len(candidates),
        "evidence_dependency_annotation_count": len(dependency_queue),
        "gold_entity_queue_count": len(entity_queue),
        "gold_protocol_queue_count": len(protocol_queue),
        "review_batch_candidate_claim_count": review_batch_payload[
            "candidate_claim_count"
        ],
        "review_batch_protocol_count": review_batch_payload["protocol_count"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create pending human-review queues from protocol claims."
    )
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument(
        "--review-batch-only",
        action="store_true",
        help="Add the review-batch manifest to an existing pending queue.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(
        json.dumps(
            (
                prepare_review_batch(args.package)
                if args.review_batch_only
                else prepare_gold_set(args.package)
            ),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
