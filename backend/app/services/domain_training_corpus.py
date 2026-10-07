"""Export deterministic, classification-neutral scientific training text."""

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Paper, PaperChunk, ScientificKnowledgeRecord
from app.services.scientific_knowledge_service import (
    SCIENTIFIC_KNOWLEDGE_COMPILER,
    SCIENTIFIC_KNOWLEDGE_SCHEMA,
    scientific_source_snapshot_hash,
)

DOMAIN_CORPUS_SCHEMA = "pas-domain-training-corpus-v0.1"
DOMAIN_TEXT_SCHEMA = "pas-domain-training-text-v0.1"
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
}


@dataclass(frozen=True)
class DomainTrainingCorpusExport:
    corpus_path: Path
    manifest_path: Path
    manifest: dict[str, Any]
    changed_files: int


class StaleScientificKnowledgeError(RuntimeError):
    pass


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_if_changed(path: Path, content: bytes) -> bool:
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


def export_domain_training_corpus(
    session: Session,
    output_dir: str | Path,
    *,
    paper_ids: list[str] | None = None,
    limit: int | None = None,
) -> DomainTrainingCorpusExport:
    """Write deduplicated full-text chunks from compiled knowledge records."""
    statement = (
        select(ScientificKnowledgeRecord, Paper)
        .join(Paper, Paper.id == ScientificKnowledgeRecord.paper_id)
        .order_by(Paper.id)
    )
    if paper_ids is not None:
        statement = statement.where(Paper.id.in_(paper_ids))
    if limit is not None:
        statement = statement.limit(limit)
    paper_rows = list(session.execute(statement))
    selected_ids = [paper.id for _record, paper in paper_rows]

    chunks_by_paper: dict[str, list[PaperChunk]] = {
        paper_id: [] for paper_id in selected_ids
    }
    if selected_ids:
        chunks = session.execute(
            select(PaperChunk).where(
                PaperChunk.paper_id.in_(selected_ids),
                PaperChunk.section_type.not_in(_EXCLUDED_SECTIONS),
            )
        ).scalars()
        for chunk in chunks:
            chunks_by_paper[chunk.paper_id].append(chunk)

    stale_paper_ids = [
        paper.id
        for knowledge_record, paper in paper_rows
        if knowledge_record.schema_version != SCIENTIFIC_KNOWLEDGE_SCHEMA
        or knowledge_record.compiler_version != SCIENTIFIC_KNOWLEDGE_COMPILER
        or knowledge_record.source_snapshot_hash
        != scientific_source_snapshot_hash(paper, chunks_by_paper[paper.id])
    ]
    if stale_paper_ids:
        joined = ", ".join(stale_paper_ids[:10])
        suffix = " ..." if len(stale_paper_ids) > 10 else ""
        raise StaleScientificKnowledgeError(
            "Rebuild scientific knowledge before corpus export; stale papers: "
            f"{joined}{suffix}"
        )

    output_rows: list[dict[str, Any]] = []
    seen_content: set[str] = set()
    duplicate_count = 0
    sections: dict[str, int] = {}
    for knowledge_record, paper in paper_rows:
        candidates = sorted(
            chunks_by_paper[paper.id],
            key=lambda chunk: (
                -_SECTION_PRIORITY.get(chunk.section_type, 50),
                chunk.id,
            ),
        )
        for chunk in candidates:
            content_hash = _sha256_bytes(chunk.chunk_text.encode("utf-8"))
            if content_hash in seen_content:
                duplicate_count += 1
                continue
            seen_content.add(content_hash)
            record_id = _sha256_bytes(
                f"{paper.id}\0{chunk.id}\0{content_hash}".encode("utf-8")
            )
            output_rows.append(
                {
                    "schema_version": DOMAIN_TEXT_SCHEMA,
                    "record_id": record_id,
                    "paper_id": paper.id,
                    "title": paper.title,
                    "year": paper.year,
                    "chunk_id": chunk.id,
                    "section_type": chunk.section_type,
                    "text": chunk.chunk_text,
                    "content_sha256": content_hash,
                    "knowledge_record_hash": knowledge_record.content_hash,
                }
            )
            sections[chunk.section_type] = sections.get(chunk.section_type, 0) + 1

    corpus_text = "".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
        for row in output_rows
    )
    corpus_content = corpus_text.encode("utf-8")
    manifest = {
        "schema_version": DOMAIN_CORPUS_SCHEMA,
        "classification_neutral": True,
        "paper_count": len(paper_rows),
        "record_count": len(output_rows),
        "duplicate_count": duplicate_count,
        "sections": dict(sorted(sections.items())),
        "corpus_sha256": _sha256_bytes(corpus_content),
    }
    manifest_content = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    corpus_path = destination / "domain_corpus.jsonl"
    manifest_path = destination / "manifest.json"
    changed_files = int(_write_if_changed(corpus_path, corpus_content))
    changed_files += int(_write_if_changed(manifest_path, manifest_content))
    return DomainTrainingCorpusExport(
        corpus_path=corpus_path,
        manifest_path=manifest_path,
        manifest=manifest,
        changed_files=changed_files,
    )
