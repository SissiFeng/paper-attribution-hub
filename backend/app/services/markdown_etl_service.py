"""Idempotent ETL for Zotero Markdown batches stored in S3."""
from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Paper
from app.services.s3_storage import get_file, put_file


@dataclass
class MarkdownEtlStats:
    run_id: str
    manifest_key: str
    documents: int = 0
    processed: int = 0
    skipped_idempotent: int = 0
    failed: int = 0
    entities: int = 0
    embeddings: int = 0
    classified_new: int = 0
    reclassified_stale: int = 0
    review_queue_updates: int = 0
    postprocessing_run: bool = False
    report_key: str | None = None
    errors: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def process_zotero_markdown_batch(
    session: Session,
    batch_manifest_key: str,
    *,
    s3_client=None,
    run_postprocessing: bool = False,
) -> MarkdownEtlStats:
    batch = _read_json(batch_manifest_key, s3_client=s3_client)
    if batch.get("kind") != "zotero_markdown_batch":
        raise ValueError("manifest is not a Zotero Markdown batch")
    if int(batch.get("schema_version") or 0) != 1:
        raise ValueError("unsupported Zotero Markdown batch schema")
    run_id = str(batch.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("Zotero Markdown batch is missing run_id")
    document_manifest_keys = batch.get("document_manifest_keys")
    if not isinstance(document_manifest_keys, list) or not document_manifest_keys:
        raise ValueError("Zotero Markdown batch contains no documents")

    stats = MarkdownEtlStats(
        run_id=run_id,
        manifest_key=batch_manifest_key,
        documents=len(document_manifest_keys),
    )
    with tempfile.TemporaryDirectory(prefix="pas-zotero-markdown-etl-") as tmp:
        tmpdir = Path(tmp)
        for index, manifest_key in enumerate(document_manifest_keys):
            try:
                processed, entities = _process_document(
                    session,
                    str(manifest_key),
                    tmpdir / f"document-{index}.md",
                    s3_client=s3_client,
                )
                if processed:
                    stats.processed += 1
                    stats.entities += entities
                else:
                    stats.skipped_idempotent += 1
            except Exception as exc:
                session.rollback()
                stats.failed += 1
                stats.errors.append(
                    {
                        "manifest_key": str(manifest_key),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

    if run_postprocessing:
        _run_postprocessing(session, stats)
        stats.postprocessing_run = True
    report_bytes = json.dumps(
        {
            **stats.to_dict(),
            "completed_at": datetime.now(UTC).isoformat(),
            "status": "failed" if stats.failed else "complete",
        },
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    stats.report_key = put_file(
        f"etl-runs/zotero/{run_id}",
        "summary.json",
        report_bytes,
        "application/json",
        s3_client=s3_client,
        require_s3=True,
    )
    if stats.report_key is None:
        raise RuntimeError("failed to persist Zotero Markdown ETL report")
    return stats


def _process_document(
    session: Session,
    document_manifest_key: str,
    local_path: Path,
    *,
    s3_client=None,
) -> tuple[bool, int]:
    manifest = _read_json(document_manifest_key, s3_client=s3_client)
    if manifest.get("kind") != "zotero_markdown_document":
        raise ValueError("manifest is not a Zotero Markdown document")
    if int(manifest.get("schema_version") or 0) != 1:
        raise ValueError("unsupported Zotero Markdown document schema")

    paper_id = str(manifest.get("paper_id") or "").strip()
    idempotency_key = str(manifest.get("idempotency_key") or "").strip()
    if not paper_id or not idempotency_key:
        raise ValueError("document manifest is missing identity fields")
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise ValueError(f"paper not found: {paper_id}")
    prior = dict((paper.raw_metadata or {}).get("zotero_fulltext") or {})
    if (
        prior.get("status") == "etl_complete"
        and prior.get("idempotency_key") == idempotency_key
    ):
        return False, 0

    markdown = manifest.get("markdown")
    if not isinstance(markdown, dict):
        raise ValueError("document manifest is missing Markdown metadata")
    if str(markdown.get("bucket") or "") != settings.s3_artifacts_bucket:
        raise ValueError("document manifest references an unexpected S3 bucket")
    markdown_key = str(markdown.get("key") or "")
    if not markdown_key.startswith("raw/zotero/") or not markdown_key.endswith(".md"):
        raise ValueError("document manifest references an invalid raw Markdown key")
    markdown_bytes = get_file(
        markdown_key,
        s3_client=s3_client,
        require_s3=True,
    )
    if markdown_bytes is None:
        raise FileNotFoundError(f"Markdown object not found: {markdown_key}")
    actual_sha256 = hashlib.sha256(markdown_bytes).hexdigest()
    if actual_sha256 != str(markdown.get("sha256") or ""):
        raise ValueError("Markdown checksum does not match the document manifest")

    local_path.write_bytes(markdown_bytes)
    from app.services.entity_extractor import run_entity_extraction
    from app.services.fulltext_service import ingest_fulltext_file

    ingest_fulltext_file(session, paper_id, local_path)
    entity_summary = run_entity_extraction(session, paper_ids=[paper_id])
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise RuntimeError(f"paper disappeared during ETL: {paper_id}")
    raw = dict(paper.raw_metadata or {})
    fulltext = dict(raw.get("zotero_fulltext") or {})
    fulltext.update(
        {
            "status": "etl_complete",
            "idempotency_key": idempotency_key,
            "markdown_key": markdown_key,
            "markdown_sha256": actual_sha256,
            "document_manifest_key": document_manifest_key,
            "etl_completed_at": datetime.now(UTC).isoformat(),
        }
    )
    raw["zotero_fulltext"] = fulltext
    paper.raw_metadata = raw
    paper.pdf_path = f"s3://{settings.s3_artifacts_bucket}/{markdown_key}"
    session.commit()
    return True, int(entity_summary["entities"])


def _run_postprocessing(session: Session, stats: MarkdownEtlStats) -> None:
    from app.services.fulltext_service import build_chunk_embeddings
    from app.services.relevance_classifier import classify_new
    from app.services.review_queue import refresh_queue

    if settings.sdl_stage1_only:
        from app.services.zotero_ingestion_service import validate_stage1_corpus

        validate_stage1_corpus(session)
    else:
        from app.services.lab_service import load_labs_from_yaml, map_papers_to_labs

        load_labs_from_yaml(session)
        map_papers_to_labs(session)
    stats.embeddings = build_chunk_embeddings(session)
    _, stats.classified_new, stats.reclassified_stale = classify_new(session)
    stats.review_queue_updates = refresh_queue(session)
    session.commit()


def _read_json(key: str, *, s3_client=None) -> dict[str, Any]:
    content = get_file(key, s3_client=s3_client, require_s3=True)
    if content is None:
        raise FileNotFoundError(f"S3 object not found: {key}")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON object: {key}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {key}")
    return payload
