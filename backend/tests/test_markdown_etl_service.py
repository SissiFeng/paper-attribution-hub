from __future__ import annotations

import hashlib
import json
from io import BytesIO

from app.config import settings
from app.models import Paper
from app.services import markdown_etl_service


class _FakeS3:
    def __init__(self, objects: dict[str, bytes]):
        self.objects = objects

    def get_object(self, *, Bucket, Key):
        assert Bucket == "artifacts"
        return {"Body": BytesIO(self.objects[Key])}

    def put_object(self, *, Bucket, Key, Body, ContentType):
        assert Bucket == "artifacts"
        self.objects[Key] = Body.read() if hasattr(Body, "read") else Body
        return {}


def test_markdown_batch_etl_is_checksum_verified_and_idempotent(
    seeded_session, monkeypatch
):
    markdown = b"""# Test paper

Methods
We used an autonomous laboratory and Bayesian optimization.
"""
    markdown_key = (
        "raw/zotero/group=42/item=ITEM1/attachment=ATTACH1/"
        "version=4/document.md"
    )
    document_manifest_key = (
        "manifests/zotero/group=42/item=ITEM1/attachment=ATTACH1/"
        "version=4/document-manifest.json"
    )
    batch_manifest_key = (
        "manifests/zotero/runs/run-test/batch-manifest.json"
    )
    document_manifest = {
        "schema_version": 1,
        "kind": "zotero_markdown_document",
        "paper_id": "P001",
        "idempotency_key": "idem-1",
        "markdown": {
            "bucket": "artifacts",
            "key": markdown_key,
            "sha256": hashlib.sha256(markdown).hexdigest(),
        },
    }
    batch_manifest = {
        "schema_version": 1,
        "kind": "zotero_markdown_batch",
        "run_id": "run-test",
        "document_manifest_keys": [document_manifest_key],
    }
    objects = {
        markdown_key: markdown,
        document_manifest_key: json.dumps(document_manifest).encode(),
        batch_manifest_key: json.dumps(batch_manifest).encode(),
    }
    fake_s3 = _FakeS3(objects)
    monkeypatch.setattr(settings, "s3_artifacts_bucket", "artifacts")
    monkeypatch.setattr(
        markdown_etl_service,
        "_run_postprocessing",
        lambda _session, _stats: None,
    )

    first = markdown_etl_service.process_zotero_markdown_batch(
        seeded_session,
        batch_manifest_key,
        s3_client=fake_s3,
    )
    second = markdown_etl_service.process_zotero_markdown_batch(
        seeded_session,
        batch_manifest_key,
        s3_client=fake_s3,
    )

    assert first.processed == 1
    assert first.failed == 0
    assert second.processed == 0
    assert second.skipped_idempotent == 1
    paper = seeded_session.get(Paper, "P001")
    assert paper.full_text_available is True
    assert paper.pdf_path == f"s3://artifacts/{markdown_key}"
    assert paper.raw_metadata["zotero_fulltext"]["status"] == "etl_complete"
    assert first.report_key == "etl-runs/zotero/run-test/summary.json"
    assert first.postprocessing_run is False


def test_markdown_batch_rejects_checksum_mismatch(
    seeded_session, monkeypatch
):
    markdown_key = (
        "raw/zotero/group=42/item=ITEM1/attachment=ATTACH1/"
        "version=4/document.md"
    )
    document_manifest_key = (
        "manifests/zotero/group=42/item=ITEM1/attachment=ATTACH1/"
        "version=4/document-manifest.json"
    )
    batch_manifest_key = (
        "manifests/zotero/runs/run-bad/batch-manifest.json"
    )
    objects = {
        markdown_key: b"# Changed",
        document_manifest_key: json.dumps(
            {
                "schema_version": 1,
                "kind": "zotero_markdown_document",
                "paper_id": "P001",
                "idempotency_key": "idem-bad",
                "markdown": {
                    "bucket": "artifacts",
                    "key": markdown_key,
                    "sha256": "not-the-checksum",
                },
            }
        ).encode(),
        batch_manifest_key: json.dumps(
            {
                "schema_version": 1,
                "kind": "zotero_markdown_batch",
                "run_id": "run-bad",
                "document_manifest_keys": [document_manifest_key],
            }
        ).encode(),
    }
    monkeypatch.setattr(settings, "s3_artifacts_bucket", "artifacts")
    monkeypatch.setattr(
        markdown_etl_service,
        "_run_postprocessing",
        lambda _session, _stats: None,
    )

    stats = markdown_etl_service.process_zotero_markdown_batch(
        seeded_session,
        batch_manifest_key,
        s3_client=_FakeS3(objects),
    )

    assert stats.processed == 0
    assert stats.failed == 1
    assert "checksum" in stats.errors[0]["error"]


def test_markdown_batch_runs_postprocessing_only_when_explicit(
    seeded_session,
    monkeypatch,
):
    called = {"count": 0}

    def fake_postprocessing(_session, stats):
        called["count"] += 1
        stats.classified_new = 3

    monkeypatch.setattr(
        markdown_etl_service,
        "_run_postprocessing",
        fake_postprocessing,
    )
    monkeypatch.setattr(settings, "s3_artifacts_bucket", "artifacts")
    batch_key = "manifests/zotero/etl-ready/empty/batch-manifest.json"
    fake_s3 = _FakeS3(
        {
            batch_key: json.dumps(
                {
                    "schema_version": 1,
                    "kind": "zotero_markdown_batch",
                    "run_id": "explicit-postprocess",
                    "document_manifest_keys": ["missing-document"],
                }
            ).encode(),
        }
    )

    stats = markdown_etl_service.process_zotero_markdown_batch(
        seeded_session,
        batch_key,
        s3_client=fake_s3,
        run_postprocessing=True,
    )

    assert called["count"] == 1
    assert stats.postprocessing_run is True
    assert stats.classified_new == 3
