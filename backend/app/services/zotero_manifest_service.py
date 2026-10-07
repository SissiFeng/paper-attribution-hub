"""Inventory verified Zotero Markdown manifests and publish replay batches."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.services.s3_storage import get_file, get_s3_client, put_file


@dataclass
class ZoteroManifestInventory:
    group_id: str
    objects_scanned: int = 0
    document_manifests: int = 0
    unique_papers: int = 0
    duplicate_versions: int = 0
    selected_manifest_by_paper: dict[str, str] = field(default_factory=dict)

    @property
    def paper_ids(self) -> set[str]:
        return set(self.selected_manifest_by_paper)


def inventory_ready_zotero_manifests(
    group_id: str,
    *,
    collection_key: str | None = None,
    s3_client=None,
) -> ZoteroManifestInventory:
    """Select one latest ready document manifest per paper."""
    if not settings.s3_artifacts_bucket:
        raise RuntimeError("PAS_S3_ARTIFACTS_BUCKET is required")
    client = s3_client or get_s3_client()
    if client is None:
        raise RuntimeError("S3 is unavailable")

    prefix = f"manifests/zotero/group={group_id}/"
    inventory = ZoteroManifestInventory(group_id=group_id)
    selected: dict[str, tuple[tuple[int, str, str], str]] = {}
    continuation: str | None = None
    while True:
        request: dict[str, Any] = {
            "Bucket": settings.s3_artifacts_bucket,
            "Prefix": prefix,
        }
        if continuation:
            request["ContinuationToken"] = continuation
        response = client.list_objects_v2(**request)
        for row in response.get("Contents", []):
            key = str(row.get("Key") or "")
            inventory.objects_scanned += 1
            if not key.endswith("/document-manifest.json"):
                continue
            payload = _read_manifest(key, s3_client=client)
            _validate_document_manifest(
                payload,
                key=key,
                group_id=group_id,
                collection_key=collection_key,
            )
            inventory.document_manifests += 1
            paper_id = str(payload["paper_id"])
            zotero = payload["zotero"]
            rank = (
                int(zotero.get("attachment_version") or 0),
                str(payload.get("created_at") or ""),
                key,
            )
            prior = selected.get(paper_id)
            if prior is not None:
                inventory.duplicate_versions += 1
            if prior is None or rank > prior[0]:
                selected[paper_id] = (rank, key)
        continuation = response.get("NextContinuationToken")
        if not response.get("IsTruncated"):
            break

    if not selected:
        raise ValueError(
            f"No ready Zotero Markdown manifests found for group {group_id}"
        )
    inventory.selected_manifest_by_paper = {
        paper_id: key
        for paper_id, (_rank, key) in sorted(selected.items())
    }
    inventory.unique_papers = len(inventory.selected_manifest_by_paper)
    return inventory


def publish_manifest_replay_batch(
    inventory: ZoteroManifestInventory,
    *,
    collection_key: str,
    s3_client=None,
) -> str:
    """Publish one immutable batch containing the selected unique manifests."""
    client = s3_client or get_s3_client()
    if client is None:
        raise RuntimeError("S3 is unavailable")
    run_id = (
        f"manifest-replay-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-"
        f"{uuid.uuid4().hex[:8]}"
    )
    payload = {
        "schema_version": 1,
        "kind": "zotero_markdown_batch",
        "phase": "acquisition_complete",
        "status": "ready",
        "classification_enabled": False,
        "source": "verified_unique_document_manifests",
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "zotero": {
            "group_id": inventory.group_id,
            "collection_keys": [collection_key],
        },
        "document_manifest_keys": list(
            inventory.selected_manifest_by_paper.values()
        ),
        "documents": inventory.unique_papers,
        "duplicate_versions_excluded": inventory.duplicate_versions,
    }
    key = put_file(
        f"manifests/zotero/runs/{run_id}",
        "batch-manifest.json",
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"),
        "application/json",
        s3_client=client,
        require_s3=True,
    )
    if key is None:
        raise RuntimeError("failed to publish Zotero manifest replay batch")
    return key


def _read_manifest(key: str, *, s3_client) -> dict:
    content = get_file(key, s3_client=s3_client, require_s3=True)
    if content is None:
        raise FileNotFoundError(f"Zotero document manifest not found: {key}")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid Zotero document manifest JSON: {key}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Zotero document manifest is not an object: {key}")
    return payload


def _validate_document_manifest(
    payload: dict,
    *,
    key: str,
    group_id: str,
    collection_key: str | None,
) -> None:
    if (
        int(payload.get("schema_version") or 0) != 1
        or payload.get("kind") != "zotero_markdown_document"
        or payload.get("status") != "ready"
    ):
        raise ValueError(f"Unexpected Zotero document manifest contract: {key}")
    paper_id = str(payload.get("paper_id") or "").strip()
    idempotency_key = str(payload.get("idempotency_key") or "").strip()
    zotero = payload.get("zotero")
    markdown = payload.get("markdown")
    if not paper_id or not idempotency_key:
        raise ValueError(f"Zotero document manifest lacks identity: {key}")
    if not isinstance(zotero, dict) or str(zotero.get("group_id")) != group_id:
        raise ValueError(f"Zotero document manifest has wrong group: {key}")
    collection_keys = {
        str(value) for value in zotero.get("collection_keys") or []
    }
    if collection_key and collection_key not in collection_keys:
        raise ValueError(f"Zotero document manifest is outside Tier 1: {key}")
    if not isinstance(markdown, dict):
        raise ValueError(f"Zotero document manifest lacks Markdown: {key}")
    markdown_key = str(markdown.get("key") or "")
    expected_prefix = f"raw/zotero/group={group_id}/"
    if (
        str(markdown.get("bucket") or "") != settings.s3_artifacts_bucket
        or not markdown_key.startswith(expected_prefix)
        or not markdown_key.endswith("/document.md")
        or not str(markdown.get("sha256") or "")
    ):
        raise ValueError(
            f"Zotero document manifest has invalid Markdown provenance: {key}"
        )
