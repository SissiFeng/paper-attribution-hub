from __future__ import annotations

import json

from sqlalchemy import func, select

from app.config import settings
from app.models import (
    AcCorePaper,
    Author,
    Institution,
    Paper,
    PaperLabLink,
    SdlLab,
    Topic,
)
from app.services.zotero_client import ZoteroAPIError, ZoteroDownload
from app.services.zotero_ingestion_service import (
    ZoteroCollectionSpec,
    ZoteroSyncStats,
    _select_pdf_attachment,
    collect_zotero_papers,
    ingest_zotero_fulltexts,
    sync_zotero_corpus,
)


def _item(
    key: str,
    *,
    title: str,
    doi: str | None = None,
    abstract: str = "",
    year: str = "2024",
) -> dict:
    return {
        "key": key,
        "version": 7,
        "library": {"id": 42},
        "data": {
            "key": key,
            "itemType": "journalArticle",
            "title": title,
            "abstractNote": abstract,
            "date": year,
            "DOI": doi or "",
            "publicationTitle": "Test Journal",
            "creators": [
                {
                    "creatorType": "author",
                    "firstName": "Ada",
                    "lastName": "Lovelace",
                }
            ],
            "tags": [{"tag": "SDL"}],
        },
    }


class _FakeClient:
    group_id = "42"

    def __init__(
        self,
        items_by_collection: dict[str, list[dict]],
        attachments: list[dict] | None = None,
    ):
        self.items_by_collection = items_by_collection
        self.attachments = attachments or []

    def resolve_collection(self, identifier: str) -> dict:
        return {"key": identifier, "data": {"name": f"Collection {identifier}"}}

    def iter_collection_top_items(self, collection_key: str, *, limit=None):
        rows = self.items_by_collection[collection_key]
        yield from rows if limit is None else rows[:limit]

    def iter_attachments(self):
        return iter(self.attachments)


def _pdf_attachment(parent_key: str, attachment_key: str) -> dict:
    return {
        "key": attachment_key,
        "version": 1,
        "data": {
            "key": attachment_key,
            "parentItem": parent_key,
            "contentType": "application/pdf",
            "filename": f"{attachment_key}.pdf",
            "linkMode": "imported_url",
        },
    }


class _EmptyS3:
    def get_paginator(self, operation: str):
        assert operation == "list_objects_v2"
        return self

    def paginate(self, **_kwargs):
        yield {"Contents": []}


def _spec(tier: str, key: str, source: str) -> ZoteroCollectionSpec:
    return ZoteroCollectionSpec(
        tier=tier,
        identifier=key,
        corpus_source=source,
    )


def test_collect_merges_tier_membership_by_normalized_doi():
    client = _FakeClient(
        {
            "ONE": [
                _item(
                    "A",
                    title="Sparse title",
                    doi="https://doi.org/10.1000/ABC",
                )
            ],
            "TWO": [
                _item(
                    "B",
                    title="Complete title",
                    doi="10.1000/abc",
                    abstract="Full abstract",
                )
            ],
        }
    )

    records, stats = collect_zotero_papers(
        client,
        [
            _spec("tier1", "ONE", "STRICT_SDL_KEYWORD"),
            _spec("tier2", "TWO", "ARCHITECTURE_BROAD_RETRIEVAL"),
        ],
    )

    assert len(records) == 1
    assert records[0].doi == "10.1000/abc"
    assert records[0].retrieval_tiers == {"tier1", "tier2"}
    assert records[0].collection_keys == {"ONE", "TWO"}
    assert stats.duplicates_merged == 1


def test_collect_pdf_backed_only_excludes_metadata_only_and_deduplicates():
    client = _FakeClient(
        {
            "ONE": [
                _item("PDF_A", title="First copy", doi="10.1000/same"),
                _item("PDF_B", title="Second copy", doi="10.1000/same"),
                _item("META", title="Metadata only", doi="10.1000/meta"),
            ]
        },
        attachments=[
            _pdf_attachment("PDF_A", "ATTACH_A"),
            _pdf_attachment("PDF_B", "ATTACH_B"),
        ],
    )

    records, stats = collect_zotero_papers(
        client,
        [_spec("tier1", "ONE", "STRICT_SDL_KEYWORD")],
        pdf_backed_only=True,
    )

    assert [record.doi for record in records] == ["10.1000/same"]
    assert stats.seen_items == 3
    assert stats.bibliographic_papers == 2
    assert stats.unique_papers == 1
    assert stats.pdf_backed_papers == 1
    assert stats.pdf_backed_raw_items == 2
    assert stats.pdf_attachment_rows == 2
    assert stats.papers_without_pdf == 1


def test_replace_requires_verified_backup_before_reading_zotero(session):
    client = _FakeClient({"ONE": [_item("A", title="Paper")]})

    try:
        sync_zotero_corpus(
            session,
            client,
            [_spec("tier1", "ONE", "STRICT_SDL_KEYWORD")],
            replace=True,
        )
    except ValueError as exc:
        assert "verified AWS backup" in str(exc)
    else:
        raise AssertionError("replacement without a backup reference must fail")


def test_replace_clears_old_papers_and_ac_core_then_imports_zotero(
    seeded_session,
):
    old_paper_ids = set(seeded_session.scalars(select(Paper.id)))
    assert old_paper_ids
    assert (
        seeded_session.scalar(select(func.count(AcCorePaper.id))) or 0
    ) > 0
    client = _FakeClient(
        {
            "ONE": [
                _item(
                    "Z1",
                    title="Authoritative Zotero paper",
                    doi="10.1000/zotero",
                    abstract="A self-driving laboratory.",
                )
            ]
        },
        attachments=[_pdf_attachment("Z1", "ATTACH_Z1")],
    )

    stats = sync_zotero_corpus(
        seeded_session,
        client,
        [_spec("tier1", "ONE", "STRICT_SDL_KEYWORD")],
        replace=True,
        backup_reference="s3://bucket/database-backups/verified.dump",
    )

    papers = list(seeded_session.scalars(select(Paper)))
    assert len(papers) == 1
    assert papers[0].id == "DOI:10.1000_zotero"
    assert papers[0].source == "zotero"
    assert papers[0].provenance == "zotero_group"
    assert papers[0].retrieval_tier == "tier1"
    assert papers[0].corpus_sources == ["STRICT_SDL_KEYWORD"]
    assert papers[0].raw_metadata["corpus_replacement_backup"].startswith("s3://")
    assert not old_paper_ids.intersection({paper.id for paper in papers})
    assert seeded_session.scalar(select(func.count(AcCorePaper.id))) == 0
    assert (seeded_session.scalar(select(func.count(Topic.id))) or 0) > 0
    assert stats.papers_before_replace == len(old_paper_ids)
    assert stats.inserted == 1

    again = sync_zotero_corpus(
        seeded_session,
        client,
        [_spec("tier1", "ONE", "STRICT_SDL_KEYWORD")],
    )
    assert again.inserted == 0
    assert again.updated == 1
    assert seeded_session.scalar(select(func.count(Paper.id))) == 1


def test_stage1_replace_removes_all_ac_seed_state(
    seeded_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "sdl_stage1_only", True)
    monkeypatch.setattr(settings, "zotero_tier1_collection", "ONE")
    monkeypatch.setattr(settings, "zotero_tier2_collection", "")
    client = _FakeClient(
        {
            "ONE": [
                _item(
                    "Z1",
                    title="Tier 1 self-driving laboratory",
                    doi="10.1000/stage1",
                )
            ]
        },
        attachments=[_pdf_attachment("Z1", "ATTACH_Z1")],
    )

    sync_zotero_corpus(
        seeded_session,
        client,
        [_spec("tier1", "ONE", "STRICT_SDL_KEYWORD")],
        replace=True,
        backup_reference=(
            "rds-snapshot:paper-attribution-dev-pre-zotero-20260805"
        ),
    )

    paper = seeded_session.scalar(select(Paper))
    assert paper.source == "zotero"
    assert paper.retrieval_tier == "tier1"
    assert seeded_session.scalar(select(func.count(AcCorePaper.id))) == 0
    assert seeded_session.scalar(select(func.count(Institution.id))) == 0
    assert seeded_session.scalar(select(func.count(SdlLab.id))) == 0
    assert seeded_session.scalar(select(func.count(PaperLabLink.paper_id))) == 0
    assert all(
        author.is_ac_member is False
        for author in seeded_session.scalars(select(Author))
    )


def test_stage1_replace_can_be_restricted_to_manifest_backed_papers(
    seeded_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "sdl_stage1_only", True)
    monkeypatch.setattr(settings, "zotero_tier1_collection", "ONE")
    monkeypatch.setattr(settings, "zotero_tier2_collection", "")
    client = _FakeClient(
        {
            "ONE": [
                _item("Z1", title="Manifest-backed", doi="10.1000/manifest"),
                _item("Z2", title="No Markdown", doi="10.1000/no-markdown"),
            ]
        },
        attachments=[
            _pdf_attachment("Z1", "ATTACH_Z1"),
            _pdf_attachment("Z2", "ATTACH_Z2"),
        ],
    )

    stats = sync_zotero_corpus(
        seeded_session,
        client,
        [_spec("tier1", "ONE", "STRICT_SDL_KEYWORD")],
        replace=True,
        backup_reference="rds-snapshot:verified",
        allowed_paper_ids={"DOI:10.1000_manifest"},
    )

    papers = list(seeded_session.scalars(select(Paper)))
    assert [paper.id for paper in papers] == ["DOI:10.1000_manifest"]
    assert stats.pdf_backed_papers == 2
    assert stats.manifest_backed_papers == 1
    assert stats.unique_papers == 1


def test_stage1_non_replace_rejects_legacy_corpus(
    seeded_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "sdl_stage1_only", True)
    monkeypatch.setattr(settings, "zotero_tier1_collection", "ONE")
    monkeypatch.setattr(settings, "zotero_tier2_collection", "")
    client = _FakeClient({"ONE": [_item("Z1", title="Tier 1 paper")]})

    try:
        sync_zotero_corpus(
            seeded_session,
            client,
            [_spec("tier1", "ONE", "STRICT_SDL_KEYWORD")],
        )
    except ValueError as exc:
        assert "non-Tier-1" in str(exc)
    else:
        raise AssertionError("legacy corpus must fail before Stage 1 sync")


def test_stage1_rejects_tier2_spec(session, monkeypatch):
    monkeypatch.setattr(settings, "sdl_stage1_only", True)
    monkeypatch.setattr(settings, "zotero_tier1_collection", "ONE")
    monkeypatch.setattr(settings, "zotero_tier2_collection", "")
    client = _FakeClient({"TWO": [_item("Z2", title="Tier 2 paper")]})

    try:
        sync_zotero_corpus(
            session,
            client,
            [_spec("tier2", "TWO", "ARCHITECTURE_BROAD_RETRIEVAL")],
        )
    except ValueError as exc:
        assert "only the configured Zotero Tier 1" in str(exc)
    else:
        raise AssertionError("Stage 1 must reject Tier 2")


def test_fulltext_export_persists_markdown_not_pdf(
    session, monkeypatch
):
    class FulltextClient(_FakeClient):
        def iter_attachments(self):
            yield {
                "key": "ATTACH1",
                "version": 4,
                "data": {
                    "key": "ATTACH1",
                    "parentItem": "ITEM1",
                    "contentType": "application/pdf",
                    "filename": "paper.pdf",
                    "linkMode": "imported_file",
                },
            }

        def download_attachment(self, attachment_key: str, *, filename=None):
            assert attachment_key == "ATTACH1"
            return ZoteroDownload(
                content=b"%PDF-source-must-stay-ephemeral",
                content_type="application/pdf",
                filename=filename,
            )

    writes: list[dict] = []

    def fake_put_file(
        key_prefix,
        filename,
        content,
        content_type="application/octet-stream",
        **_kwargs,
    ):
        key = f"{key_prefix}/{filename}"
        writes.append(
            {
                "key": key,
                "content": content,
                "content_type": content_type,
            }
        )
        return key

    monkeypatch.setattr(settings, "s3_artifacts_bucket", "artifacts")
    monkeypatch.setattr(
        "app.services.pdf_parser.convert_file_to_markdown",
        lambda _path: (
            "# Converted paper",
            "pdf-inspector",
            "test",
            {
                "quality_status": "complete_text",
                "pdf_type": "text_based",
            },
        ),
    )
    monkeypatch.setattr(
        "app.services.s3_storage.put_file",
        fake_put_file,
    )
    monkeypatch.setattr(
        "app.services.s3_storage.get_s3_client",
        lambda: _EmptyS3(),
    )
    client = FulltextClient(
        {"ONE": [_item("ITEM1", title="Markdown source paper")]}
    )

    stats = sync_zotero_corpus(
        session,
        client,
        [_spec("tier1", "ONE", "STRICT_SDL_KEYWORD")],
        download_fulltexts=True,
    )

    raw_writes = [row for row in writes if row["key"].startswith("raw/")]
    assert [row["key"] for row in raw_writes] == [
        "raw/zotero/group=42/item=ITEM1/attachment=ATTACH1/"
        "version=4/document.md"
    ]
    assert raw_writes[0]["content"] == b"# Converted paper\n"
    assert all(not row["key"].endswith(".pdf") for row in writes)
    assert all(b"%PDF-source" not in row["content"] for row in writes)
    document_manifest = next(
        json.loads(row["content"])
        for row in writes
        if row["key"].endswith("document-manifest.json")
    )
    assert document_manifest["source"]["persisted"] is False
    assert document_manifest["markdown"]["key"].endswith("document.md")
    assert document_manifest["markdown"]["converter"] == "pdf-inspector"
    assert (
        document_manifest["markdown"]["inspection"]["quality_status"]
        == "complete_text"
    )
    assert stats.markdown_exported == 1
    assert stats.batch_manifest_key.endswith("batch-manifest.json")
    paper = session.scalar(select(Paper))
    assert paper.raw_metadata["zotero_fulltext"]["status"] == "markdown_ready"
    assert paper.full_text_available is False

    raw = dict(paper.raw_metadata or {})
    fulltext = dict(raw["zotero_fulltext"])
    fulltext["status"] = "etl_complete"
    fulltext["etl_completed_at"] = "2026-08-06T00:00:00+00:00"
    raw["zotero_fulltext"] = fulltext
    paper.raw_metadata = raw
    session.commit()
    records, _ = collect_zotero_papers(
        client,
        [_spec("tier1", "ONE", "STRICT_SDL_KEYWORD")],
    )
    repeat_stats = ZoteroSyncStats()

    ingest_zotero_fulltexts(session, client, records, repeat_stats)

    session.refresh(paper)
    assert paper.raw_metadata["zotero_fulltext"]["status"] == "etl_complete"
    assert (
        paper.raw_metadata["zotero_fulltext"]["idempotency_key"]
        == fulltext["idempotency_key"]
    )


def test_select_pdf_attachment_excludes_link_only_records():
    linked_pdf = {
        "key": "LINKED",
        "version": 20,
        "data": {
            "contentType": "application/pdf",
            "filename": "linked.pdf",
            "linkMode": "linked_url",
        },
    }
    imported_pdf = {
        "key": "IMPORTED",
        "version": 10,
        "data": {
            "contentType": "application/pdf",
            "filename": "stored.pdf",
            "linkMode": "imported_file",
        },
    }
    imported_url = {
        "key": "IMPORTED_URL",
        "version": 30,
        "data": {
            "contentType": "application/pdf",
            "filename": "url.pdf",
            "linkMode": "imported_url",
        },
    }

    assert _select_pdf_attachment([linked_pdf]) is None
    assert _select_pdf_attachment([linked_pdf, imported_url]) == imported_url
    assert (
        _select_pdf_attachment([linked_pdf, imported_url, imported_pdf])
        == imported_pdf
    )


def test_fulltext_export_stops_after_requested_success_count(
    session, monkeypatch
):
    class LimitedClient(_FakeClient):
        def __init__(self):
            super().__init__(
                {
                    "ONE": [
                        _item("ITEM1", title="First"),
                        _item("ITEM2", title="Second"),
                    ]
                }
            )
            self.downloaded: list[str] = []

        def iter_attachments(self):
            for item_key, attachment_key in (
                ("ITEM1", "ATTACH1"),
                ("ITEM2", "ATTACH2"),
            ):
                yield {
                    "key": attachment_key,
                    "version": 1,
                    "data": {
                        "key": attachment_key,
                        "parentItem": item_key,
                        "contentType": "application/pdf",
                        "filename": f"{item_key}.pdf",
                        "linkMode": "imported_url",
                    },
                }

        def download_attachment(self, attachment_key: str, *, filename=None):
            self.downloaded.append(attachment_key)
            return ZoteroDownload(
                content=b"%PDF-downloadable",
                content_type="application/pdf",
                filename=filename,
            )

    def fake_put_file(key_prefix, filename, *_args, **_kwargs):
        return f"{key_prefix}/{filename}"

    monkeypatch.setattr(settings, "s3_artifacts_bucket", "artifacts")
    monkeypatch.setattr(
        "app.services.pdf_parser.convert_file_to_markdown",
        lambda _path: (
            "# Converted",
            "pdf-inspector",
            "test",
            {"quality_status": "complete_text"},
        ),
    )
    monkeypatch.setattr("app.services.s3_storage.put_file", fake_put_file)
    monkeypatch.setattr(
        "app.services.s3_storage.get_s3_client",
        lambda: _EmptyS3(),
    )
    client = LimitedClient()
    records, _ = collect_zotero_papers(
        client,
        [_spec("tier1", "ONE", "STRICT_SDL_KEYWORD")],
    )
    sync_zotero_corpus(
        session,
        client,
        [_spec("tier1", "ONE", "STRICT_SDL_KEYWORD")],
    )
    stats = ZoteroSyncStats()

    ingest_zotero_fulltexts(
        session,
        client,
        records,
        stats,
        max_exports=1,
    )

    assert stats.markdown_exported == 1
    assert client.downloaded == ["ATTACH1"]


def test_fulltext_export_falls_back_when_newest_attachment_is_unavailable(
    session, monkeypatch
):
    class FallbackClient(_FakeClient):
        def __init__(self):
            super().__init__({"ONE": [_item("ITEM1", title="Fallback")]})
            self.downloaded: list[str] = []

        def iter_attachments(self):
            for attachment_key, version in (
                ("NEW_MISSING", 20),
                ("OLD_AVAILABLE", 10),
            ):
                yield {
                    "key": attachment_key,
                    "version": version,
                    "data": {
                        "key": attachment_key,
                        "parentItem": "ITEM1",
                        "contentType": "application/pdf",
                        "filename": f"{attachment_key}.pdf",
                        "linkMode": "imported_url",
                    },
                }

        def download_attachment(self, attachment_key: str, *, filename=None):
            self.downloaded.append(attachment_key)
            if attachment_key == "NEW_MISSING":
                raise ZoteroAPIError("HTTP 404")
            return ZoteroDownload(
                content=b"%PDF-downloadable",
                content_type="application/pdf",
                filename=filename,
            )

    def fake_put_file(key_prefix, filename, *_args, **_kwargs):
        return f"{key_prefix}/{filename}"

    monkeypatch.setattr(settings, "s3_artifacts_bucket", "artifacts")
    monkeypatch.setattr(
        "app.services.pdf_parser.convert_file_to_markdown",
        lambda _path: (
            "# Converted",
            "pdf-inspector",
            "test",
            {"quality_status": "complete_text"},
        ),
    )
    monkeypatch.setattr("app.services.s3_storage.put_file", fake_put_file)
    monkeypatch.setattr(
        "app.services.s3_storage.get_s3_client",
        lambda: _EmptyS3(),
    )
    client = FallbackClient()
    records, _ = collect_zotero_papers(
        client,
        [_spec("tier1", "ONE", "STRICT_SDL_KEYWORD")],
    )
    sync_zotero_corpus(
        session,
        client,
        [_spec("tier1", "ONE", "STRICT_SDL_KEYWORD")],
    )
    stats = ZoteroSyncStats()

    ingest_zotero_fulltexts(
        session,
        client,
        records,
        stats,
        max_exports=1,
    )

    assert stats.markdown_exported == 1
    assert client.downloaded == ["NEW_MISSING", "OLD_AVAILABLE"]
