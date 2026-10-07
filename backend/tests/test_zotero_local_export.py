import json
from pathlib import Path

from app.config import settings
from app.services.zotero_ingestion_service import ZoteroPaper
from app.services.zotero_local_export_service import (
    _select_local_pdf,
    export_local_zotero_fulltexts,
)


def _record(paper_id: str, item_key: str) -> ZoteroPaper:
    return ZoteroPaper(
        paper_id=paper_id,
        title=paper_id,
        abstract=None,
        authors=[],
        year=2025,
        doi=None,
        venue=None,
        keywords=[],
        item_key=item_key,
        item_version=3,
        retrieval_tiers={"tier1"},
        corpus_sources={"STRICT_SDL_KEYWORD"},
        collection_keys={"TIER1"},
        source_items=[{"key": item_key}],
    )


class _Client:
    group_id = "42"

    def iter_attachments(self):
        for parent, key, version in (
            ("ITEM1", "ATTACH1", 4),
            ("ITEM2", "ATTACH2", 5),
        ):
            yield {
                "key": key,
                "version": version,
                "data": {
                    "key": key,
                    "parentItem": parent,
                    "contentType": "application/pdf",
                    "filename": f"{key}.pdf",
                    "linkMode": "imported_file",
                },
            }


class _S3:
    def get_paginator(self, operation):
        assert operation == "list_objects_v2"
        return self

    def paginate(self, **_kwargs):
        yield {"Contents": []}


class _ExistingS3(_S3):
    def paginate(self, **_kwargs):
        yield {
            "Contents": [
                {
                    "Key": (
                        "raw/zotero/group=42/item=ITEM1/"
                        "attachment=OLD/version=1/document.md"
                    )
                }
            ]
        }


def test_local_export_uses_standard_manifest_without_uploading_pdf(
    tmp_path: Path,
    monkeypatch,
):
    storage = tmp_path / "storage"
    pdf_dir = storage / "ATTACH1"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "ATTACH1.pdf").write_bytes(b"%PDF-local")
    writes = []

    def fake_put_file(prefix, name, content, content_type, **_kwargs):
        writes.append(
            {
                "key": f"{prefix}/{name}",
                "content": content,
                "content_type": content_type,
            }
        )
        return f"{prefix}/{name}"

    monkeypatch.setattr(settings, "s3_artifacts_bucket", "artifacts")
    monkeypatch.setattr(
        "app.services.zotero_local_export_service."
        "convert_file_to_markdown",
        lambda _path: (
            "# Local paper",
            "pdf-inspector",
            "test",
            {"quality_status": "complete_text"},
        ),
    )
    monkeypatch.setattr(
        "app.services.zotero_local_export_service.put_file",
        fake_put_file,
    )

    stats = export_local_zotero_fulltexts(
        _Client(),
        [_record("PAPER1", "ITEM1"), _record("PAPER2", "ITEM2")],
        storage_root=storage,
        allowed_paper_ids={"PAPER1"},
        s3_client=_S3(),
    )

    assert stats.markdown_exported == 1
    assert stats.batch_manifest_key
    assert all(not row["key"].endswith(".pdf") for row in writes)
    manifest = next(
        json.loads(row["content"])
        for row in writes
        if row["key"].endswith("document-manifest.json")
    )
    batch_manifest = next(
        json.loads(row["content"])
        for row in writes
        if row["key"].endswith("batch-manifest.json")
    )
    assert manifest["paper_id"] == "PAPER1"
    assert manifest["source"]["persisted"] is False
    assert manifest["source"]["acquisition"] == "zotero_local_storage"
    assert manifest["markdown"]["key"].startswith("raw/zotero/")
    assert batch_manifest["phase"] == "acquisition_complete"
    assert batch_manifest["classification_enabled"] is False


def test_local_export_skips_paper_with_an_existing_markdown_version(
    tmp_path: Path,
    monkeypatch,
):
    storage = tmp_path / "storage"
    pdf_dir = storage / "ATTACH1"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "ATTACH1.pdf").write_bytes(b"%PDF-new-version")
    monkeypatch.setattr(settings, "s3_artifacts_bucket", "artifacts")

    stats = export_local_zotero_fulltexts(
        _Client(),
        [_record("PAPER1", "ITEM1")],
        storage_root=storage,
        allowed_paper_ids={"PAPER1"},
        s3_client=_ExistingS3(),
    )

    assert stats.skipped_existing == 1
    assert stats.markdown_exported == 0
    assert stats.batch_manifest_key is None


def test_local_export_rejects_unverified_pdf_markdown(
    tmp_path: Path,
    monkeypatch,
):
    storage = tmp_path / "storage"
    pdf_dir = storage / "ATTACH1"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "ATTACH1.pdf").write_bytes(b"%PDF-local")
    writes = []

    monkeypatch.setattr(settings, "s3_artifacts_bucket", "artifacts")
    monkeypatch.setattr(
        "app.services.zotero_local_export_service."
        "convert_file_to_markdown",
        lambda _path: (
            "# Partial paper",
            "markitdown",
            "test",
            {"quality_status": "unverified_fallback"},
        ),
    )
    monkeypatch.setattr(
        "app.services.zotero_local_export_service.put_file",
        lambda *args, **kwargs: writes.append((args, kwargs)),
    )

    stats = export_local_zotero_fulltexts(
        _Client(),
        [_record("PAPER1", "ITEM1")],
        storage_root=storage,
        allowed_paper_ids={"PAPER1"},
        s3_client=_S3(),
    )

    assert stats.markdown_exported == 0
    assert stats.markdown_failed == 1
    assert "complete-text quality gate" in stats.errors[0]["error"]
    assert writes == []


def test_select_local_pdf_rejects_ambiguous_attachment_directory(
    tmp_path: Path,
):
    storage = tmp_path / "storage"
    pdf_dir = storage / "ATTACH1"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "one.pdf").write_bytes(b"%PDF-one")
    (pdf_dir / "two.pdf").write_bytes(b"%PDF-two")
    attachment = {
        "key": "ATTACH1",
        "version": 1,
        "data": {
            "key": "ATTACH1",
            "parentItem": "ITEM1",
            "contentType": "application/pdf",
            "filename": "missing.pdf",
            "linkMode": "imported_file",
        },
    }

    try:
        _select_local_pdf(storage, [attachment])
    except ValueError as exc:
        assert "Ambiguous local PDFs" in str(exc)
    else:
        raise AssertionError("ambiguous local PDFs must fail closed")
