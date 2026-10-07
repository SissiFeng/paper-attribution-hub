"""Build a versioned Domain Adaptation Package from selected source papers."""

from __future__ import annotations

import hashlib
import json
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from app.domain_adaptation.chunking import (
    SCIENTIFIC_CHUNK_SCHEMA,
    ScientificChunkingPolicy,
    build_scientific_chunks,
    validate_scientific_chunk,
)
from app.domain_adaptation.extractors import (
    ProtocolExtractor,
    is_high_information_chunk,
    scientific_content,
)
from app.domain_adaptation.models import (
    DomainPackageConfig,
    KnowledgeRelation,
    PackageBuildResult,
    ProtocolUnit,
    ScientificChunk,
    SourceChunk,
    SourcePaper,
)
from app.domain_adaptation.package_graph import PackageDescriptor
from app.domain_adaptation.validation import validate_protocol_unit


CORPUS_SCHEMA = "domain-adapter-corpus-v0.2"
KNOWLEDGE_SCHEMA = "domain-adapter-knowledge-v0.1"
TASK_SCHEMA = "domain-adapter-task-v0.3"


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_text(content: str) -> str:
    return _sha256_bytes(content.encode("utf-8"))


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _jsonl_bytes(rows: Iterable[dict]) -> bytes:
    return "".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
        for row in rows
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


def _excluded_chunk(chunk: SourceChunk) -> bool:
    section = f"{chunk.section_type} {chunk.section_title or ''}".casefold()
    if "reference" in section or "acknowledg" in section:
        return True
    stripped = chunk.text.lstrip().casefold()
    return stripped.startswith(
        (
            "author contributions",
            "competing interests",
            "publisher's note",
            "publisher’s note",
            "reprints and permissions",
        )
    )


def _eligible_chunks(paper: SourcePaper) -> list[SourceChunk]:
    return [
        chunk
        for chunk in paper.chunks
        if not _excluded_chunk(chunk) and is_high_information_chunk(chunk)
    ]


def _attach_structural_relations(protocol: ProtocolUnit) -> ProtocolUnit:
    relations: list[KnowledgeRelation] = []

    def add(object_id: str, predicate: str, evidence_ids: list[str]) -> None:
        relation_id = "rel_" + _sha256_text(
            f"{protocol.protocol_id}\0{predicate}\0{object_id}"
        )[:16]
        relations.append(
            KnowledgeRelation(
                relation_id=relation_id,
                subject_id=protocol.protocol_id,
                predicate=predicate,
                object_id=object_id,
                evidence_ids=evidence_ids,
            )
        )

    for material in protocol.materials:
        add(material.entity_id, "uses_material", material.evidence_ids)
    for instrument in protocol.instruments:
        add(instrument.entity_id, "uses_instrument", instrument.evidence_ids)
    for software in protocol.software:
        add(software.entity_id, "uses_software", software.evidence_ids)
    for step in protocol.steps:
        add(step.step_id, "has_step", step.evidence_ids)
    for technique in protocol.characterization:
        add(technique.entity_id, "uses_characterization", technique.evidence_ids)
    for result in protocol.results:
        add(result.result_id, "reports_result", result.evidence_ids)
    for caveat in protocol.caveats:
        add(caveat.caveat_id, "has_caveat", caveat.evidence_ids)
    return protocol.model_copy(update={"relations": relations})


def _attach_scientific_chunk_links(
    protocol: ProtocolUnit,
    scientific_chunk_ids_by_source: dict[tuple[str, str], list[str]],
) -> ProtocolUnit:
    scientific_chunk_ids = list(
        dict.fromkeys(
            scientific_chunk_id
            for source_chunk_id in protocol.source_chunk_ids
            for scientific_chunk_id in scientific_chunk_ids_by_source.get(
                (protocol.paper_id, source_chunk_id), []
            )
        )
    )
    return protocol.model_copy(
        update={"scientific_chunk_ids": scientific_chunk_ids}
    )


def _corpus_rows(
    papers: list[SourcePaper],
    scientific_chunks: list[ScientificChunk],
) -> tuple[list[dict], int, int]:
    rows: list[dict] = []
    seen: dict[str, dict] = {}
    duplicate_count = 0
    paper_by_id = {paper.paper_id: paper for paper in papers}
    eligible_source_ids = {
        (chunk.paper_id, source_chunk_id)
        for chunk in scientific_chunks
        for source_chunk_id in chunk.source_chunk_ids
    }
    excluded_count = sum(
        (paper.paper_id, chunk.chunk_id) not in eligible_source_ids
        for paper in papers
        for chunk in paper.chunks
    )
    for chunk in scientific_chunks:
        paper = paper_by_id[chunk.paper_id]
        content_hash = chunk.content_sha256
        if content_hash in seen:
            duplicate_count += 1
            seen[content_hash]["duplicate_provenance"].append(
                {
                    "paper_id": paper.paper_id,
                    "scientific_chunk_id": chunk.scientific_chunk_id,
                    "source_chunk_ids": chunk.source_chunk_ids,
                }
            )
            continue
        document_starts = [
            item.document_char_start
            for item in chunk.segments
            if item.document_char_start is not None
        ]
        document_ends = [
            item.document_char_end
            for item in chunk.segments
            if item.document_char_end is not None
        ]
        row = {
            "schema_version": CORPUS_SCHEMA,
            "record_id": _sha256_text(
                f"{paper.paper_id}\0{chunk.scientific_chunk_id}\0{content_hash}"
            ),
            "paper_id": paper.paper_id,
            "title": paper.title,
            "year": paper.year,
            "chunk_id": chunk.scientific_chunk_id,
            "scientific_chunk_id": chunk.scientific_chunk_id,
            "parent_section_id": chunk.parent_section_id,
            "semantic_roles": chunk.semantic_roles,
            "source_chunk_ids": chunk.source_chunk_ids,
            "source_segments": [
                item.model_dump(mode="json") for item in chunk.segments
            ],
            "section_type_original": chunk.section_type,
            "section_title_original": chunk.section_title,
            "section_path": chunk.section_path,
            "document_char_start": (
                min(document_starts) if document_starts else None
            ),
            "document_char_end": max(document_ends) if document_ends else None,
            "source_markdown_key": paper.source_markdown_key,
            "text": chunk.text,
            "content_sha256": content_hash,
            "duplicate_provenance": [],
        }
        rows.append(row)
        seen[content_hash] = row
    return rows, duplicate_count, excluded_count


def _paper_records(
    papers: list[SourcePaper], scientific_chunks: list[ScientificChunk]
) -> list[dict]:
    records: list[dict] = []
    chunks_by_paper: dict[str, list[ScientificChunk]] = {}
    for chunk in scientific_chunks:
        chunks_by_paper.setdefault(chunk.paper_id, []).append(chunk)
    for paper in sorted(papers, key=lambda item: item.paper_id):
        chunks = _eligible_chunks(paper)
        snapshot = "\0".join(
            f"{chunk.chunk_id}:{_sha256_text(scientific_content(chunk.text))}"
            for chunk in sorted(chunks, key=lambda item: item.chunk_id)
        )
        semantic_chunks = chunks_by_paper.get(paper.paper_id, [])
        semantic_snapshot = "\0".join(
            f"{chunk.scientific_chunk_id}:{chunk.content_sha256}"
            for chunk in semantic_chunks
        )
        records.append(
            {
                "schema_version": KNOWLEDGE_SCHEMA,
                "paper_id": paper.paper_id,
                "title": paper.title,
                "year": paper.year,
                "doi": paper.doi,
                "selection_tier": paper.selection_tier,
                "selection_reasons": paper.selection_reasons,
                "task_split": paper.task_split,
                "source_bucket": paper.source_bucket,
                "source_prefix": paper.source_prefix,
                "source_manifest_key": paper.source_manifest_key,
                "source_markdown_key": paper.source_markdown_key,
                "source_markdown_sha256": paper.source_markdown_sha256,
                "eligible_chunk_ids": [chunk.chunk_id for chunk in chunks],
                "scientific_chunk_ids": [
                    chunk.scientific_chunk_id for chunk in semantic_chunks
                ],
                "source_snapshot_sha256": _sha256_text(snapshot),
                "scientific_chunk_snapshot_sha256": _sha256_text(
                    semantic_snapshot
                ),
            }
        )
    return records


def _schema_placeholder(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _schema_placeholder(item)
            for key, item in sorted(value.items())
        }
    if isinstance(value, list):
        if not value:
            return []
        merged = _schema_placeholder(value[0])
        for item in value[1:]:
            merged = _merge_schema_placeholders(
                merged, _schema_placeholder(item)
            )
        return [merged]
    if value is None:
        return "<null>"
    if isinstance(value, bool):
        return "<boolean>"
    if isinstance(value, int):
        return "<integer>"
    if isinstance(value, float):
        return "<number>"
    return "<string>"


def _merge_schema_placeholders(left: Any, right: Any) -> Any:
    if isinstance(left, dict) and isinstance(right, dict):
        return {
            key: (
                _merge_schema_placeholders(left[key], right[key])
                if key in left and key in right
                else left.get(key, right.get(key))
            )
            for key in sorted(set(left) | set(right))
        }
    if isinstance(left, list) and isinstance(right, list):
        if not left:
            return right
        if not right:
            return left
        return [_merge_schema_placeholders(left[0], right[0])]
    if left == right:
        return left
    if isinstance(left, str) and isinstance(right, str):
        types = {
            item
            for value in (left, right)
            for item in value.removeprefix("<").removesuffix(">").split("|")
        }
        order = ["string", "integer", "number", "boolean", "null"]
        return "<" + "|".join(item for item in order if item in types) + ">"
    return "<value>"


def _protocol_tasks(protocols: list[ProtocolUnit]) -> list[dict]:
    tasks: list[dict] = []

    def append_task(
        protocol: ProtocolUnit,
        task_type: str,
        instruction: str,
        response: Any,
        evidence_ids: list[str],
    ) -> None:
        task_evidence_ids = sorted(set(evidence_ids))
        task_evidence_set = set(task_evidence_ids)
        source_context = [
            {
                "evidence_id": evidence.evidence_id,
                "paper_id": evidence.paper_id,
                "chunk_id": evidence.chunk_id,
                "quote": evidence.quote,
                "char_start": evidence.char_start,
                "char_end": evidence.char_end,
                "document_char_start": evidence.document_char_start,
                "document_char_end": evidence.document_char_end,
                "source_sha256": evidence.source_sha256,
            }
            for evidence in sorted(
                protocol.evidence,
                key=lambda item: (item.chunk_id, item.char_start),
            )
            if evidence.evidence_id in task_evidence_set
        ]
        task_id = _sha256_text(
            f"{protocol.protocol_id}\0{task_type}\0{instruction}"
        )
        tasks.append(
            {
                "schema_version": TASK_SCHEMA,
                "task_id": task_id,
                "task_type": task_type,
                "paper_id": protocol.paper_id,
                "protocol_id": protocol.protocol_id,
                "instruction": instruction,
                "source_context": source_context,
                "response_schema": _schema_placeholder(response),
                "response": response,
                "evidence_ids": task_evidence_ids,
                "generation_policy": "extractive_only",
            }
        )

    for protocol in sorted(protocols, key=lambda item: item.protocol_id):
        if protocol.evidence_scope != "primary_report":
            continue
        if protocol.materials:
            append_task(
                protocol,
                "materials_extraction",
                "Extract the explicitly reported materials and quantities for this protocol.",
                [
                    {
                        "name": item.name,
                        "amount": item.amount,
                        "role": item.role,
                    }
                    for item in protocol.materials
                ],
                [eid for item in protocol.materials for eid in item.evidence_ids],
            )
        if protocol.instruments or protocol.software:
            append_task(
                protocol,
                "instrument_software_grounding",
                "Identify the explicitly reported instruments and software for this protocol.",
                {
                    "instruments": [
                        {
                            "name": item.name,
                            "model": item.model,
                            "manufacturer": item.manufacturer,
                            "settings": item.settings,
                        }
                        for item in protocol.instruments
                    ],
                    "software": [
                        {
                            "name": item.name,
                            "version": item.version,
                            "settings": item.settings,
                        }
                        for item in protocol.software
                    ],
                },
                [
                    eid
                    for item in protocol.instruments + protocol.software
                    for eid in item.evidence_ids
                ],
            )
        structured_steps = [
            item for item in protocol.steps if item.verb is not None and item.targets
        ]
        if structured_steps:
            append_task(
                protocol,
                "protocol_reconstruction",
                "Reconstruct only the explicitly supported ordered protocol steps.",
                [
                    {
                        "order": item.order,
                        "verb": item.verb,
                        "targets": item.targets,
                        "params": item.params,
                    }
                    for item in structured_steps
                ],
                [eid for item in structured_steps for eid in item.evidence_ids],
            )
        if protocol.characterization:
            append_task(
                protocol,
                "characterization_grounding",
                "Extract the reported characterization or measurement techniques and settings.",
                [
                    {"technique": item.technique, "settings": item.settings}
                    for item in protocol.characterization
                ],
                [
                    eid
                    for item in protocol.characterization
                    for eid in item.evidence_ids
                ],
            )
        if protocol.results:
            append_task(
                protocol,
                "reported_result_grounding",
                "Extract only the explicitly reported result values and their context.",
                [
                    {
                        "metric": item.metric,
                        "raw_value": item.raw_value,
                        "context": item.context,
                    }
                    for item in protocol.results
                ],
                [eid for item in protocol.results for eid in item.evidence_ids],
            )
        if protocol.caveats:
            append_task(
                protocol,
                "failure_mode_grounding",
                "Extract only explicitly stated limitations, failure modes, or cautions.",
                [item.text for item in protocol.caveats],
                [eid for item in protocol.caveats for eid in item.evidence_ids],
            )
    return tasks


def build_domain_adapter_package(
    *,
    papers: list[SourcePaper],
    output_dir: str | Path,
    extractor: ProtocolExtractor,
    config: DomainPackageConfig,
    chunking_policy: ScientificChunkingPolicy | None = None,
) -> PackageBuildResult:
    """Build Corpus, Structured Knowledge, and Task Suite artifacts."""
    if not papers:
        raise ValueError("At least one source paper is required")
    paper_ids = [paper.paper_id for paper in papers]
    if len(set(paper_ids)) != len(paper_ids):
        raise ValueError("Source paper IDs must be unique")

    active_chunking_policy = chunking_policy or ScientificChunkingPolicy()
    scientific_chunks = [
        chunk
        for paper in sorted(papers, key=lambda item: item.paper_id)
        for chunk in build_scientific_chunks(
            paper, policy=active_chunking_policy
        )
    ]
    paper_by_id = {paper.paper_id: paper for paper in papers}
    chunking_violations = [
        {
            "paper_id": chunk.paper_id,
            "scientific_chunk_id": chunk.scientific_chunk_id,
            "violations": violations,
        }
        for chunk in scientific_chunks
        for violations in [
            validate_scientific_chunk(chunk, paper_by_id[chunk.paper_id])
        ]
        if violations
    ]
    if chunking_violations:
        raise ValueError(
            "Scientific chunks failed source reconstruction: "
            + json.dumps(chunking_violations, ensure_ascii=False)
        )
    scientific_chunk_ids_by_source: dict[tuple[str, str], list[str]] = {}
    for chunk in scientific_chunks:
        for source_chunk_id in chunk.source_chunk_ids:
            scientific_chunk_ids_by_source.setdefault(
                (chunk.paper_id, source_chunk_id), []
            ).append(chunk.scientific_chunk_id)

    protocols: list[ProtocolUnit] = []
    validation_rejections: list[dict] = []
    teacher_counter_names = (
        "unsupported_claim_count",
        "proposed_field_count",
        "accepted_field_count",
        "rejected_field_count",
        "repair_attempted_count",
        "repair_succeeded_count",
        "input_token_count",
        "output_token_count",
        "latency_ms_total",
        "invocation_count",
        "response_schema_failure_count",
        "salvaged_response_count",
    )
    teacher_counters_before = {
        name: int(getattr(extractor, name, 0)) for name in teacher_counter_names
    }
    teacher_audit_records_before = len(
        getattr(extractor, "field_audit_records", [])
    )
    teacher_paper_diagnostics_before = len(
        getattr(extractor, "paper_diagnostics", [])
    )
    for paper in sorted(papers, key=lambda item: item.paper_id):
        for protocol in extractor.extract(paper):
            protocol = _attach_scientific_chunk_links(
                protocol, scientific_chunk_ids_by_source
            )
            protocol = _attach_structural_relations(protocol)
            violations = validate_protocol_unit(protocol, paper)
            if not protocol.scientific_chunk_ids:
                violations.insert(
                    0, "Protocol has no linked scientific semantic chunks"
                )
            if violations:
                validation_rejections.append(
                    {
                        "paper_id": paper.paper_id,
                        "protocol_id": protocol.protocol_id,
                        "violations": violations,
                    }
                )
                continue
            protocols.append(protocol)
    protocols.sort(key=lambda item: (item.paper_id, item.protocol_id))
    teacher_counters = {
        name: max(
            0,
            int(getattr(extractor, name, 0)) - teacher_counters_before[name],
        )
        for name in teacher_counter_names
    }
    unsupported_teacher_claims = teacher_counters[
        "unsupported_claim_count"
    ]
    all_teacher_audit_records = getattr(extractor, "field_audit_records", [])
    teacher_audit_records = list(
        all_teacher_audit_records[teacher_audit_records_before:]
    )
    all_teacher_paper_diagnostics = getattr(extractor, "paper_diagnostics", [])
    teacher_paper_diagnostics = list(
        all_teacher_paper_diagnostics[teacher_paper_diagnostics_before:]
    )

    corpus_rows, duplicate_count, excluded_count = _corpus_rows(
        papers, scientific_chunks
    )
    paper_records = _paper_records(papers, scientific_chunks)
    tasks = _protocol_tasks(protocols)
    split_by_paper = {paper.paper_id: paper.task_split for paper in papers}
    train_tasks = [
        task for task in tasks if split_by_paper[task["paper_id"]] == "train"
    ]
    eval_tasks = [
        task
        for task in tasks
        if split_by_paper[task["paper_id"]] == "evaluation"
    ]
    train_task_paper_ids = {task["paper_id"] for task in train_tasks}
    evaluation_task_paper_ids = {task["paper_id"] for task in eval_tasks}

    protocols_by_paper = Counter(protocol.paper_id for protocol in protocols)
    tier_by_paper = {paper.paper_id: paper.selection_tier for paper in papers}
    papers_by_tier = Counter(paper.selection_tier for paper in papers)
    covered_papers_by_tier = Counter(
        tier_by_paper[paper_id] for paper_id in protocols_by_paper
    )
    protocols_by_tier = Counter(
        tier_by_paper[protocol.paper_id] for protocol in protocols
    )
    protocols_by_evidence_scope = Counter(
        protocol.evidence_scope for protocol in protocols
    )
    entity_counts = {
        "materials": sum(len(protocol.materials) for protocol in protocols),
        "instruments": sum(len(protocol.instruments) for protocol in protocols),
        "software": sum(len(protocol.software) for protocol in protocols),
        "steps": sum(len(protocol.steps) for protocol in protocols),
        "characterization": sum(
            len(protocol.characterization) for protocol in protocols
        ),
        "results": sum(len(protocol.results) for protocol in protocols),
        "caveats": sum(len(protocol.caveats) for protocol in protocols),
        "relations": sum(len(protocol.relations) for protocol in protocols),
    }
    rejected_audit_records = [
        record
        for record in teacher_audit_records
        if str(record.outcome) == "rejected"
    ]
    repaired_audit_records = [
        record
        for record in teacher_audit_records
        if str(record.outcome) == "repaired"
    ]
    response_audit_records = [
        record
        for record in teacher_audit_records
        if record.entity_type == "teacher_response"
    ]
    rejected_audit_records = [
        record
        for record in rejected_audit_records
        if record.entity_type != "teacher_response"
    ]
    proposed_field_count = teacher_counters["proposed_field_count"]
    quality_report = {
        "schema_version": "domain-adapter-quality-report-v0.3",
        "paper_count": len(papers),
        "source_chunk_count": sum(len(paper.chunks) for paper in papers),
        "scientific_chunk_count": len(scientific_chunks),
        "scientific_chunks_by_semantic_role": dict(
            sorted(
                Counter(
                    role
                    for chunk in scientific_chunks
                    for role in chunk.semantic_roles
                ).items()
            )
        ),
        "multi_segment_scientific_chunk_count": sum(
            len(chunk.segments) > 1 for chunk in scientific_chunks
        ),
        "max_scientific_chunk_chars": max(
            (len(chunk.text) for chunk in scientific_chunks), default=0
        ),
        "chunking": active_chunking_policy.manifest(),
        "eligible_corpus_chunk_count": len(corpus_rows),
        "excluded_or_low_information_chunk_count": excluded_count,
        "exact_duplicate_count": duplicate_count,
        "protocol_count": len(protocols),
        "papers_with_protocols": len(protocols_by_paper),
        "papers_without_protocols": sorted(
            paper.paper_id
            for paper in papers
            if paper.paper_id not in protocols_by_paper
        ),
        "paper_coverage_by_selection_tier": {
            tier: {
                "paper_count": count,
                "papers_with_protocols": covered_papers_by_tier[tier],
                "coverage_rate": round(
                    covered_papers_by_tier[tier] / count, 6
                ),
            }
            for tier, count in sorted(papers_by_tier.items())
        },
        "protocols_per_paper": dict(sorted(protocols_by_paper.items())),
        "protocols_by_selection_tier": dict(sorted(protocols_by_tier.items())),
        "protocols_by_evidence_scope": dict(
            sorted(protocols_by_evidence_scope.items())
        ),
        "entity_counts": entity_counts,
        "evidence_span_count": sum(len(protocol.evidence) for protocol in protocols),
        "unsupported_evidence_count": unsupported_teacher_claims
        + sum(len(item["violations"]) for item in validation_rejections),
        "unsupported_teacher_claim_count": unsupported_teacher_claims,
        "teacher_field_audit": {
            "proposed_field_count": proposed_field_count,
            "accepted_field_count": teacher_counters[
                "accepted_field_count"
            ],
            "rejected_field_count": teacher_counters[
                "rejected_field_count"
            ],
            "field_acceptance_rate": (
                round(
                    teacher_counters["accepted_field_count"]
                    / proposed_field_count,
                    6,
                )
                if proposed_field_count
                else None
            ),
            "repair_attempted_count": teacher_counters[
                "repair_attempted_count"
            ],
            "repair_succeeded_count": teacher_counters[
                "repair_succeeded_count"
            ],
            "rejection_reason_counts": dict(
                sorted(
                    Counter(
                        str(record.rejection_reason)
                        for record in rejected_audit_records
                    ).items()
                )
            ),
            "rejected_entity_type_counts": dict(
                sorted(
                    Counter(
                        record.entity_type
                        for record in rejected_audit_records
                    ).items()
                )
            ),
            "repair_reason_counts": dict(
                sorted(
                    Counter(
                        str(record.rejection_reason)
                        for record in repaired_audit_records
                    ).items()
                )
            ),
        },
        "teacher_runtime": {
            "invocation_count": teacher_counters["invocation_count"],
            "input_token_count": teacher_counters["input_token_count"],
            "output_token_count": teacher_counters["output_token_count"],
            "latency_ms_total": teacher_counters["latency_ms_total"],
            "response_schema_failure_count": teacher_counters[
                "response_schema_failure_count"
            ],
            "salvaged_response_count": teacher_counters[
                "salvaged_response_count"
            ],
            "response_failure_diagnostics": [
                {
                    "paper_id": record.paper_id,
                    "diagnostic": record.diagnostic,
                }
                for record in response_audit_records
            ],
        },
        "teacher_paper_outcome_counts": dict(
            sorted(
                Counter(
                    str(item.outcome) for item in teacher_paper_diagnostics
                ).items()
            )
        ),
        "teacher_paper_diagnostics": [
            item.model_dump(mode="json") for item in teacher_paper_diagnostics
        ],
        "rejected_protocols": validation_rejections,
        "task_count": len(tasks),
        "task_type_counts": dict(
            sorted(Counter(task["task_type"] for task in tasks).items())
        ),
        "train_task_count": len(train_tasks),
        "evaluation_task_count": len(eval_tasks),
        "train_paper_count": sum(
            paper.task_split == "train" for paper in papers
        ),
        "evaluation_paper_count": sum(
            paper.task_split == "evaluation" for paper in papers
        ),
        "train_task_paper_count": len(train_task_paper_ids),
        "evaluation_task_paper_count": len(evaluation_task_paper_ids),
        "claims_boundary": (
            "Heuristic output is a baseline unless extraction.mode is teacher. "
            "Tasks are extractive and do not advise future experiments."
        ),
    }
    selection_manifest = {
        "schema_version": "domain-adapter-selection-v0.2",
        "selection_method": "curated_full_text_scientific_evidence",
        "classification_tables_used": False,
        "papers": [
            {
                "paper_id": paper.paper_id,
                "title": paper.title,
                "year": paper.year,
                "doi": paper.doi,
                "selection_tier": paper.selection_tier,
                "evidence_scope": paper.evidence_scope,
                "selection_reasons": paper.selection_reasons,
                "task_split": paper.task_split,
                "source_manifest_key": paper.source_manifest_key,
                "source_markdown_key": paper.source_markdown_key,
                "source_markdown_sha256": paper.source_markdown_sha256,
            }
            for paper in sorted(papers, key=lambda item: item.paper_id)
        ],
    }

    protocol_rows = [
        {"schema_version": KNOWLEDGE_SCHEMA, **protocol.model_dump(mode="json")}
        for protocol in protocols
    ]
    scientific_chunk_rows = [
        {
            "schema_version": SCIENTIFIC_CHUNK_SCHEMA,
            **chunk.model_dump(mode="json"),
        }
        for chunk in scientific_chunks
    ]
    contents = {
        "corpus/continued_pretraining.jsonl": _jsonl_bytes(corpus_rows),
        "knowledge/paper_records.jsonl": _jsonl_bytes(paper_records),
        "knowledge/protocols.jsonl": _jsonl_bytes(protocol_rows),
        "knowledge/scientific_chunks.jsonl": _jsonl_bytes(
            scientific_chunk_rows
        ),
        "reports/quality_report.json": _json_bytes(quality_report),
        "reports/teacher_field_audit.jsonl": _jsonl_bytes(
            record.model_dump(mode="json") for record in teacher_audit_records
        ),
        "source/selection_manifest.json": _json_bytes(selection_manifest),
        "tasks/sft/train.jsonl": _jsonl_bytes(train_tasks),
        "tasks/evaluation/eval.jsonl": _jsonl_bytes(eval_tasks),
    }
    artifact_hashes = {
        relative_path: _sha256_bytes(content)
        for relative_path, content in sorted(contents.items())
    }
    manifest = {
        "schema_version": config.schema_version,
        "package_id": config.package_id,
        "package_version": config.package_version,
        "domain": config.domain,
        "package_descriptor": PackageDescriptor(
            package_id=config.package_id,
            package_version=config.package_version,
            package_kind=config.package_kind,
            domain=config.domain,
            facets=config.facets,
            dependencies=config.dependencies,
        ).model_dump(mode="json"),
        "classification_neutral": True,
        "institution_entities_included": False,
        "source_access": config.source_access,
        "layers": [
            "cleaned_corpus",
            "scientific_chunks",
            "structured_knowledge",
            "task_suite",
        ],
        "chunking": active_chunking_policy.manifest(),
        "extraction": {
            "extractor": extractor.name,
            "mode": extractor.mode,
            "model": extractor.model,
            "prompt_version": extractor.prompt_version,
            "candidate_domain_terms": list(
                getattr(extractor, "domain_terms", ())
            ),
            "minimum_chunk_score": getattr(
                extractor, "minimum_chunk_score", None
            ),
            "scope_aware": getattr(extractor, "scope_aware", False),
            "region": getattr(extractor, "region", None),
            "inference_config": (
                {
                    "temperature": 0.0,
                    "max_output_tokens": getattr(
                        extractor, "max_output_tokens", None
                    ),
                }
                if extractor.mode == "teacher"
                else None
            ),
            "usage": quality_report["teacher_runtime"],
        },
        "counts": {
            "paper_count": len(papers),
            "corpus_record_count": len(corpus_rows),
            "scientific_chunk_count": len(scientific_chunks),
            "protocol_count": len(protocols),
            "task_count": len(tasks),
        },
        "validation": {
            "unsupported_evidence_count": quality_report[
                "unsupported_evidence_count"
            ],
            "rejected_protocol_count": len(validation_rejections),
            "rejected_teacher_field_count": teacher_counters[
                "rejected_field_count"
            ],
        },
        "artifact_sha256": artifact_hashes,
    }
    contents["manifest.json"] = _json_bytes(manifest)

    destination = Path(output_dir)
    changed_files = 0
    write_order = sorted(path for path in contents if path != "manifest.json")
    write_order.append("manifest.json")
    for relative_path in write_order:
        content = contents[relative_path]
        changed_files += int(_write_if_changed(destination / relative_path, content))
    return PackageBuildResult(
        output_dir=str(destination),
        manifest=manifest,
        changed_files=changed_files,
    )
