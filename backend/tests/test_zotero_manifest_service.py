from __future__ import annotations

import json
from io import BytesIO

from app.config import settings
from app.services.zotero_manifest_service import (
    inventory_ready_zotero_manifests,
    publish_manifest_replay_batch,
)


class _FakeS3:
    def __init__(self, objects: dict[str, bytes]):
        self.objects = objects

    def list_objects_v2(self, *, Bucket, Prefix, ContinuationToken=None):
        assert Bucket == "artifacts"
        assert ContinuationToken is None
        return {
            "Contents": [
                {"Key": key}
                for key in sorted(self.objects)
                if key.startswith(Prefix)
            ],
            "IsTruncated": False,
        }

    def get_object(self, *, Bucket, Key):
        assert Bucket == "artifacts"
        return {"Body": BytesIO(self.objects[Key])}

    def put_object(self, *, Bucket, Key, Body, ContentType):
        assert Bucket == "artifacts"
        self.objects[Key] = Body.read() if hasattr(Body, "read") else Body
        return {}


def _manifest(paper_id: str, item: str, attachment_version: int) -> bytes:
    return json.dumps(
        {
            "schema_version": 1,
            "kind": "zotero_markdown_document",
            "status": "ready",
            "paper_id": paper_id,
            "idempotency_key": f"idem-{paper_id}-{attachment_version}",
            "created_at": f"2026-08-0{attachment_version}T00:00:00+00:00",
            "zotero": {
                "group_id": "42",
                "item_key": item,
                "attachment_key": f"ATT{attachment_version}",
                "attachment_version": attachment_version,
                "collection_keys": ["TIER1"],
            },
            "markdown": {
                "bucket": "artifacts",
                "key": (
                    f"raw/zotero/group=42/item={item}/"
                    f"attachment=ATT{attachment_version}/"
                    f"version={attachment_version}/document.md"
                ),
                "sha256": f"sha-{attachment_version}",
            },
        }
    ).encode()


def test_manifest_inventory_deduplicates_versions_and_publishes_replay(
    monkeypatch,
):
    monkeypatch.setattr(settings, "s3_artifacts_bucket", "artifacts")
    old = (
        "manifests/zotero/group=42/item=ONE/attachment=ATT1/"
        "version=1/document-manifest.json"
    )
    latest = (
        "manifests/zotero/group=42/item=ONE/attachment=ATT2/"
        "version=2/document-manifest.json"
    )
    second = (
        "manifests/zotero/group=42/item=TWO/attachment=ATT1/"
        "version=1/document-manifest.json"
    )
    fake = _FakeS3(
        {
            old: _manifest("P1", "ONE", 1),
            latest: _manifest("P1", "ONE", 2),
            second: _manifest("P2", "TWO", 1),
        }
    )

    inventory = inventory_ready_zotero_manifests(
        "42",
        collection_key="TIER1",
        s3_client=fake,
    )
    batch_key = publish_manifest_replay_batch(
        inventory,
        collection_key="TIER1",
        s3_client=fake,
    )
    batch = json.loads(fake.objects[batch_key])

    assert inventory.document_manifests == 3
    assert inventory.unique_papers == 2
    assert inventory.duplicate_versions == 1
    assert inventory.selected_manifest_by_paper["P1"] == latest
    assert batch["documents"] == 2
    assert batch["duplicate_versions_excluded"] == 1
    assert batch["classification_enabled"] is False
    assert batch["document_manifest_keys"] == [latest, second]
