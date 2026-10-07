"""Export locally stored Zotero PDFs into the existing Markdown ETL contract."""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.pdf_parser import PdfNeedsOcrError, convert_file_to_markdown
from app.services.s3_storage import put_file
from app.services.zotero_client import ZoteroClient
from app.services.zotero_ingestion_service import (
    ZoteroPaper,
    _existing_zotero_item_keys,
    _pdf_attachment_candidates,
    require_complete_zotero_pdf_markdown,
)


@dataclass
class ZoteroLocalExportStats:
    papers_considered: int = 0
    local_pdfs_found: int = 0
    skipped_missing_local_pdf: int = 0
    skipped_existing: int = 0
    markdown_exported: int = 0
    markdown_failed: int = 0
    ocr_required: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)
    batch_manifest_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def export_local_zotero_fulltexts(
    client: ZoteroClient,
    records: list[ZoteroPaper],
    *,
    storage_root: Path,
    allowed_paper_ids: set[str],
    max_exports: int | None = None,
    ocr_backend: str | None = None,
    dry_run: bool = False,
    s3_client=None,
) -> ZoteroLocalExportStats:
    """Convert matched local PDFs and publish the standard Zotero batch marker.

    Tier membership comes from ``records`` fetched from the authoritative
    Zotero collection. ``allowed_paper_ids`` may select the whole verified
    Tier 1 corpus during acquisition or model roles in later workflows. Source
    PDF bytes are read locally and never uploaded.
    """
    from app.config import settings

    root = Path(storage_root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Zotero storage root not found: {root}")
    if not allowed_paper_ids:
        raise ValueError("No Stage 1 paper IDs were allowed for local export")
    if max_exports is not None and max_exports <= 0:
        raise ValueError("max_exports must be positive")
    if ocr_backend not in {None, "docling"}:
        raise ValueError(f"Unsupported OCR backend: {ocr_backend}")
    if not dry_run and not settings.s3_artifacts_bucket:
        raise RuntimeError(
            "PAS_S3_ARTIFACTS_BUCKET is required for local Zotero export"
        )
    existing_item_keys = (
        _existing_zotero_item_keys(
            s3_client,
            settings.s3_artifacts_bucket,
            client.group_id,
        )
        if s3_client is not None
        else set()
    )

    by_parent: dict[str, list[dict[str, Any]]] = {}
    for attachment in client.iter_attachments():
        data = attachment.get("data") or {}
        parent_key = str(data.get("parentItem") or "")
        if parent_key:
            by_parent.setdefault(parent_key, []).append(attachment)

    stats = ZoteroLocalExportStats()
    manifest_keys: list[str] = []
    run_id = (
        f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-"
        f"{uuid.uuid4().hex[:8]}"
    )
    for record in records:
        if record.paper_id not in allowed_paper_ids:
            continue
        if (
            max_exports is not None
            and stats.markdown_exported >= max_exports
        ):
            break
        stats.papers_considered += 1
        item_keys = {
            record.item_key,
            *[
                str(
                    item.get("key")
                    or (item.get("data") or {}).get("key")
                    or ""
                )
                for item in record.source_items
            ],
        }
        if item_keys & existing_item_keys:
            stats.skipped_existing += 1
            continue
        attachments = [
            attachment
            for item_key in item_keys
            for attachment in by_parent.get(item_key, [])
        ]
        selected = _select_local_pdf(
            root,
            _pdf_attachment_candidates(attachments),
        )
        if selected is None:
            stats.skipped_missing_local_pdf += 1
            continue
        attachment, local_pdf = selected
        stats.local_pdfs_found += 1
        attachment_key = str(
            attachment.get("key")
            or (attachment.get("data") or {}).get("key")
            or ""
        )
        attachment_version = int(attachment.get("version") or 0)
        artifact_suffix = (
            f"group={client.group_id}/item={record.item_key}/"
            f"attachment={attachment_key}/version={attachment_version}"
        )
        if dry_run:
            continue
        try:
            source_bytes = local_pdf.read_bytes()
            source_sha256 = hashlib.sha256(source_bytes).hexdigest()
            conversion_options = (
                {"ocr_backend": ocr_backend} if ocr_backend else {}
            )
            (
                markdown,
                converter,
                converter_version,
                inspection,
            ) = convert_file_to_markdown(
                local_pdf,
                **conversion_options,
            )
            require_complete_zotero_pdf_markdown(inspection)
            markdown_bytes = (markdown.rstrip() + "\n").encode("utf-8")
            markdown_sha256 = hashlib.sha256(markdown_bytes).hexdigest()
            idempotency_key = hashlib.sha256(
                (
                    f"{client.group_id}:{record.item_key}:{attachment_key}:"
                    f"{attachment_version}:{source_sha256}:{converter}:"
                    f"{converter_version}"
                ).encode("utf-8")
            ).hexdigest()
            markdown_key = put_file(
                f"raw/zotero/{artifact_suffix}",
                "document.md",
                markdown_bytes,
                "text/markdown; charset=utf-8",
                s3_client=s3_client,
                require_s3=True,
            )
            if markdown_key is None:
                raise RuntimeError("failed to persist Zotero Markdown to S3")
            document_manifest = {
                "schema_version": 1,
                "kind": "zotero_markdown_document",
                "status": "ready",
                "paper_id": record.paper_id,
                "idempotency_key": idempotency_key,
                "created_at": datetime.now(UTC).isoformat(),
                "zotero": {
                    "group_id": client.group_id,
                    "item_key": record.item_key,
                    "item_version": record.item_version,
                    "attachment_key": attachment_key,
                    "attachment_version": attachment_version,
                    "collection_keys": sorted(record.collection_keys),
                },
                "source": {
                    "filename": local_pdf.name,
                    "media_type": "application/pdf",
                    "sha256": source_sha256,
                    "persisted": False,
                    "acquisition": "zotero_local_storage",
                },
                "markdown": {
                    "bucket": settings.s3_artifacts_bucket,
                    "key": markdown_key,
                    "sha256": markdown_sha256,
                    "bytes": len(markdown_bytes),
                    "converter": converter,
                    "converter_version": converter_version,
                    "inspection": inspection,
                },
            }
            persisted_manifest_key = put_file(
                f"manifests/zotero/{artifact_suffix}",
                "document-manifest.json",
                json.dumps(
                    document_manifest,
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8"),
                "application/json",
                s3_client=s3_client,
                require_s3=True,
            )
            if persisted_manifest_key is None:
                raise RuntimeError(
                    "failed to persist Zotero document manifest"
                )
            manifest_keys.append(persisted_manifest_key)
            stats.markdown_exported += 1
        except PdfNeedsOcrError as exc:
            stats.ocr_required += 1
            stats.markdown_failed += 1
            stats.errors.append(
                _error(record, attachment_key, local_pdf, exc)
            )
        except Exception as exc:
            stats.markdown_failed += 1
            stats.errors.append(
                _error(record, attachment_key, local_pdf, exc)
            )

    if manifest_keys and not dry_run:
        batch_manifest = {
            "schema_version": 1,
            "kind": "zotero_markdown_batch",
            "phase": "acquisition_complete",
            "status": "ready",
            "classification_enabled": False,
            "run_id": run_id,
            "created_at": datetime.now(UTC).isoformat(),
            "zotero": {
                "group_id": client.group_id,
                "collection_keys": sorted(
                    {
                        key
                        for record in records
                        if record.paper_id in allowed_paper_ids
                        for key in record.collection_keys
                    }
                ),
            },
            "source": "zotero_local_storage",
            "document_manifest_keys": manifest_keys,
            "documents": len(manifest_keys),
        }
        stats.batch_manifest_key = put_file(
            f"manifests/zotero/runs/{run_id}",
            "batch-manifest.json",
            json.dumps(
                batch_manifest,
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8"),
            "application/json",
            s3_client=s3_client,
            require_s3=True,
        )
        if stats.batch_manifest_key is None:
            raise RuntimeError("failed to publish Zotero ETL batch manifest")
    return stats


def _select_local_pdf(
    storage_root: Path,
    attachments: list[dict[str, Any]],
) -> tuple[dict[str, Any], Path] | None:
    for attachment in attachments:
        data = attachment.get("data") or {}
        attachment_key = str(
            attachment.get("key") or data.get("key") or ""
        )
        storage_dir = storage_root / attachment_key
        if not storage_dir.is_dir():
            continue
        filename = str(data.get("filename") or "")
        exact = storage_dir / filename
        if filename and exact.is_file() and exact.suffix.lower() == ".pdf":
            return attachment, exact
        pdfs = sorted(
            path
            for path in storage_dir.iterdir()
            if path.is_file() and path.suffix.lower() == ".pdf"
        )
        if len(pdfs) == 1:
            return attachment, pdfs[0]
        if len(pdfs) > 1:
            raise ValueError(
                f"Ambiguous local PDFs for Zotero attachment {attachment_key}"
            )
    return None


def _error(
    record: ZoteroPaper,
    attachment_key: str,
    local_pdf: Path,
    exc: Exception,
) -> dict[str, str]:
    return {
        "paper_id": record.paper_id,
        "attachment_key": attachment_key,
        "filename": local_pdf.name,
        "error": f"{type(exc).__name__}: {exc}",
    }
