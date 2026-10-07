"""Compile classification-neutral, evidence-linked scientific paper knowledge."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models import Paper, PaperChunk, ScientificKnowledgeRecord
from app.services.entity_extractor import load_sdl_entities
from app.services.text_utils import find_term_hits


SCIENTIFIC_KNOWLEDGE_SCHEMA = "pas-scientific-knowledge-v0.1"
SCIENTIFIC_KNOWLEDGE_COMPILER = "deterministic-v0.1"
SCIENTIFIC_ENTITY_TYPES = ("method", "material", "instrument", "software")
_EXCLUDED_SECTIONS = frozenset({"acknowledgements", "references"})
_SECTION_PRIORITY = {
    "methods": 100,
    "experimental": 100,
    "results": 90,
    "supplementary": 85,
    "figure_caption": 80,
    "abstract": 70,
    "discussion": 60,
    "conclusion": 60,
    "unknown": 50,
    "introduction": 40,
    "title": 30,
}
_SENTENCE_START = re.compile(r"(?<=[.!?])\s+")


class ScientificKnowledgeNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class ScientificKnowledgeCompileResult:
    record: ScientificKnowledgeRecord
    changed: bool


@dataclass(frozen=True)
class ScientificKnowledgeBatchResult:
    selected: int
    changed: int
    unchanged: int
    failed: int
    errors: tuple[dict[str, str], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "selected": self.selected,
            "changed": self.changed,
            "unchanged": self.unchanged,
            "failed": self.failed,
            "errors": list(self.errors),
        }


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _scientific_vocabulary() -> dict[str, dict[str, str]]:
    loaded = load_sdl_entities()
    return {
        entity_type: loaded.get(entity_type, {})
        for entity_type in SCIENTIFIC_ENTITY_TYPES
    }


def _source_projection(
    paper: Paper,
    chunks: list[PaperChunk],
    vocabulary: dict[str, dict[str, str]],
) -> dict[str, Any]:
    return {
        "paper_id": paper.id,
        "title": paper.title,
        "abstract": paper.abstract,
        "year": paper.year,
        "vocabulary_sha256": _canonical_hash(vocabulary),
        "chunks": [
            {
                "id": chunk.id,
                "section_type": chunk.section_type,
                "text": chunk.chunk_text,
            }
            for chunk in sorted(chunks, key=lambda item: (item.section_type, item.id))
            if chunk.section_type not in _EXCLUDED_SECTIONS
        ],
    }


def scientific_source_snapshot_hash(
    paper: Paper,
    chunks: list[PaperChunk],
) -> str:
    """Hash every input that can change deterministic entity compilation."""
    return _canonical_hash(_source_projection(paper, chunks, _scientific_vocabulary()))


def _evidence_excerpt(text: str, start: int, end: int) -> str:
    cursor = 0
    for sentence in _SENTENCE_START.split(text):
        sentence_start = text.find(sentence, cursor)
        if sentence_start < 0:
            sentence_start = cursor
        sentence_end = sentence_start + len(sentence)
        if sentence_start <= start and end <= sentence_end:
            return " ".join(sentence.split())[:500]
        cursor = sentence_end
    return " ".join(text.split())[:500]


def _source_rows(paper: Paper, chunks: list[PaperChunk]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if paper.title:
        rows.append(
            {
                "text": paper.title,
                "section_type": "title",
                "chunk_id": None,
                "priority": _SECTION_PRIORITY["title"],
                "confidence": 0.6,
            }
        )
    if paper.abstract:
        rows.append(
            {
                "text": paper.abstract,
                "section_type": "abstract",
                "chunk_id": None,
                "priority": _SECTION_PRIORITY["abstract"],
                "confidence": 0.7,
            }
        )
    for chunk in chunks:
        if chunk.section_type in _EXCLUDED_SECTIONS:
            continue
        rows.append(
            {
                "text": chunk.chunk_text,
                "section_type": chunk.section_type,
                "chunk_id": chunk.id,
                "priority": _SECTION_PRIORITY.get(chunk.section_type, 50),
                "confidence": 0.9,
            }
        )
    return rows


def _compile_entities(
    paper: Paper,
    chunks: list[PaperChunk],
    vocabulary: dict[str, dict[str, str]],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for source in _source_rows(paper, chunks):
        text = str(source["text"])
        for entity_type in SCIENTIFIC_ENTITY_TYPES:
            for surface, canonical in vocabulary.get(entity_type, {}).items():
                hits = find_term_hits(text, surface)
                if not hits:
                    continue
                hit = hits[0]
                candidate = {
                    "name": canonical,
                    "surface_form": text[hit.start : hit.end],
                    "confidence": source["confidence"],
                    "section_type": source["section_type"],
                    "chunk_id": source["chunk_id"],
                    "evidence_text": _evidence_excerpt(text, hit.start, hit.end),
                    "rank": (
                        source["chunk_id"] is not None,
                        source["priority"],
                        source["confidence"],
                    ),
                }
                key = (entity_type, canonical)
                if key not in best or candidate["rank"] > best[key]["rank"]:
                    best[key] = candidate

    entities: dict[str, list[dict[str, Any]]] = {
        entity_type: [] for entity_type in SCIENTIFIC_ENTITY_TYPES
    }
    assertions: list[dict[str, Any]] = []
    for (entity_type, _canonical), candidate in sorted(best.items()):
        entity = {key: value for key, value in candidate.items() if key != "rank"}
        entities[entity_type].append(entity)
        assertions.append(
            {
                "subject_type": "paper",
                "subject_id": paper.id,
                "predicate": "reports_scientific_entity",
                "object_type": entity_type,
                "object_value": entity["name"],
                "confidence": entity["confidence"],
                "evidence": {
                    "paper_id": paper.id,
                    "section_type": entity["section_type"],
                    "chunk_id": entity["chunk_id"],
                    "text": entity["evidence_text"],
                },
            }
        )
    return entities, assertions


def get_scientific_knowledge(
    session: Session,
    paper_id: str,
) -> ScientificKnowledgeRecord:
    record = session.get(ScientificKnowledgeRecord, paper_id)
    if record is None:
        raise ScientificKnowledgeNotFoundError(
            f"Scientific knowledge for paper {paper_id!r} was not found"
        )
    return record


def compile_scientific_knowledge(
    session: Session,
    paper_id: str,
) -> ScientificKnowledgeCompileResult:
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise ScientificKnowledgeNotFoundError(f"Paper {paper_id!r} was not found")
    chunks = list(
        session.execute(
            select(PaperChunk)
            .where(PaperChunk.paper_id == paper_id)
            .order_by(PaperChunk.section_type, PaperChunk.id)
        ).scalars()
    )
    vocabulary = _scientific_vocabulary()
    vocabulary_hash = _canonical_hash(vocabulary)
    source_projection = _source_projection(paper, chunks, vocabulary)
    source_snapshot_hash = _canonical_hash(source_projection)
    existing = session.get(ScientificKnowledgeRecord, paper_id)
    if (
        existing is not None
        and existing.schema_version == SCIENTIFIC_KNOWLEDGE_SCHEMA
        and existing.compiler_version == SCIENTIFIC_KNOWLEDGE_COMPILER
        and existing.source_snapshot_hash == source_snapshot_hash
    ):
        return ScientificKnowledgeCompileResult(record=existing, changed=False)

    entities, assertions = _compile_entities(paper, chunks, vocabulary)
    source_metadata = {
        "paper_id": paper.id,
        "chunk_count": len(source_projection["chunks"]),
        "entity_counts": {
            entity_type: len(values) for entity_type, values in entities.items()
        },
        "classification_neutral": True,
        "vocabulary_sha256": vocabulary_hash,
    }
    content_hash = _canonical_hash(
        {
            "entities": entities,
            "assertions": assertions,
            "source_metadata": source_metadata,
        }
    )
    generated_at = datetime.now(UTC)
    if existing is None:
        existing = ScientificKnowledgeRecord(paper_id=paper_id)
        session.add(existing)
    existing.schema_version = SCIENTIFIC_KNOWLEDGE_SCHEMA
    existing.compiler_version = SCIENTIFIC_KNOWLEDGE_COMPILER
    existing.source_snapshot_hash = source_snapshot_hash
    existing.content_hash = content_hash
    existing.entities = entities
    existing.assertions = assertions
    existing.source_metadata = source_metadata
    existing.generated_at = generated_at
    session.flush()
    return ScientificKnowledgeCompileResult(record=existing, changed=True)


def compile_scientific_knowledge_batch(
    session: Session,
    *,
    paper_ids: list[str] | None = None,
    limit: int | None = None,
) -> ScientificKnowledgeBatchResult:
    """Compile eligible full-text papers without reading attribution state."""
    statement = (
        select(Paper.id)
        .where(
            Paper.full_text_available.is_(True),
            exists().where(PaperChunk.paper_id == Paper.id),
        )
        .order_by(Paper.id)
    )
    if paper_ids is not None:
        statement = statement.where(Paper.id.in_(paper_ids))
    if limit is not None:
        statement = statement.limit(limit)
    selected_ids = list(session.execute(statement).scalars())

    changed = 0
    unchanged = 0
    errors: list[dict[str, str]] = []
    for paper_id in selected_ids:
        try:
            with session.begin_nested():
                result = compile_scientific_knowledge(session, paper_id)
            if result.changed:
                changed += 1
            else:
                unchanged += 1
        except Exception as exc:  # pragma: no cover - defensive batch isolation
            errors.append(
                {
                    "paper_id": paper_id,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return ScientificKnowledgeBatchResult(
        selected=len(selected_ids),
        changed=changed,
        unchanged=unchanged,
        failed=len(errors),
        errors=tuple(errors),
    )
