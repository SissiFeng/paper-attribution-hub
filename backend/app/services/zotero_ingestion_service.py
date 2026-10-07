"""Map authoritative Zotero collections into the PAS paper corpus."""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Author, Paper, PaperAuthor
from app.services.normalization_service import normalize_doi, normalize_name
from app.services.retrieval_operationalization import retrieval_query
from app.services.zotero_client import ZoteroClient, ZoteroDownload

_YEAR_RE = re.compile(r"\b(1[5-9]\d{2}|20\d{2}|21\d{2})\b")
_DOI_PREFIX_RE = re.compile(
    r"^(?:doi:\s*)?(?:https?://)?(?:dx\.)?doi\.org/", re.IGNORECASE
)
_NON_BIBLIOGRAPHIC_TYPES = {"annotation", "attachment", "note"}


@dataclass(frozen=True)
class ZoteroCollectionSpec:
    tier: str
    identifier: str
    corpus_source: str


@dataclass
class ZoteroPaper:
    paper_id: str
    title: str
    abstract: str | None
    authors: list[str]
    year: int | None
    doi: str | None
    venue: str | None
    keywords: list[str]
    item_key: str
    item_version: int
    retrieval_tiers: set[str] = field(default_factory=set)
    corpus_sources: set[str] = field(default_factory=set)
    collection_keys: set[str] = field(default_factory=set)
    source_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ZoteroSyncStats:
    collections: dict[str, str] = field(default_factory=dict)
    seen_items: int = 0
    bibliographic_papers: int = 0
    unique_papers: int = 0
    duplicates_merged: int = 0
    skipped_invalid: int = 0
    pdf_backed_papers: int = 0
    pdf_backed_raw_items: int = 0
    pdf_attachment_rows: int = 0
    papers_without_pdf: int = 0
    manifest_backed_papers: int = 0
    inserted: int = 0
    updated: int = 0
    papers_before_replace: int = 0
    fulltexts_ingested: int = 0
    fulltexts_missing: int = 0
    fulltexts_failed: int = 0
    fulltext_errors: list[dict[str, str]] = field(default_factory=list)
    markdown_exported: int = 0
    markdown_skipped_existing: int = 0
    markdown_missing: int = 0
    markdown_failed: int = 0
    markdown_errors: list[dict[str, str]] = field(default_factory=list)
    batch_manifest_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def configured_collection_specs() -> list[ZoteroCollectionSpec]:
    from app.config import settings

    if settings.sdl_stage1_only:
        if not settings.zotero_tier1_collection:
            raise ValueError(
                "SDL Stage 1 requires PAS_ZOTERO_TIER1_COLLECTION"
            )
        if settings.zotero_tier2_collection:
            raise ValueError(
                "SDL Stage 1 forbids PAS_ZOTERO_TIER2_COLLECTION"
            )
    specs: list[ZoteroCollectionSpec] = []
    if settings.zotero_tier1_collection:
        specs.append(
            ZoteroCollectionSpec(
                tier="tier1",
                identifier=settings.zotero_tier1_collection,
                corpus_source="STRICT_SDL_KEYWORD",
            )
        )
    if settings.zotero_tier2_collection:
        specs.append(
            ZoteroCollectionSpec(
                tier="tier2",
                identifier=settings.zotero_tier2_collection,
                corpus_source="ARCHITECTURE_BROAD_RETRIEVAL",
            )
        )
    if not specs:
        raise ValueError(
            "Configure PAS_ZOTERO_TIER1_COLLECTION and/or "
            "PAS_ZOTERO_TIER2_COLLECTION"
        )
    return specs


def collect_zotero_papers(
    client: ZoteroClient,
    specs: list[ZoteroCollectionSpec],
    *,
    limit: int | None = None,
    pdf_backed_only: bool = False,
) -> tuple[list[ZoteroPaper], ZoteroSyncStats]:
    stats = ZoteroSyncStats()
    by_identity: dict[str, ZoteroPaper] = {}
    for spec in specs:
        collection = client.resolve_collection(spec.identifier)
        collection_key = str(collection["key"])
        collection_name = str((collection.get("data") or {}).get("name") or "")
        stats.collections[spec.tier] = collection_key
        for item in client.iter_collection_top_items(collection_key, limit=limit):
            stats.seen_items += 1
            record = zotero_item_to_paper(
                item,
                group_id=client.group_id,
                collection_key=collection_key,
                tier=spec.tier,
                corpus_source=spec.corpus_source,
            )
            if record is None:
                stats.skipped_invalid += 1
                continue
            identity = _dedup_identity(record)
            existing = by_identity.get(identity)
            if existing is None:
                by_identity[identity] = record
            else:
                by_identity[identity] = _merge_records(existing, record)
                stats.duplicates_merged += 1
        stats.collections[f"{spec.tier}_name"] = collection_name
    records = sorted(by_identity.values(), key=lambda row: row.paper_id)
    stats.bibliographic_papers = len(records)
    if pdf_backed_only:
        records = _filter_pdf_backed_papers(client, records, stats)
    stats.unique_papers = len(records)
    return records, stats


def _filter_pdf_backed_papers(
    client: ZoteroClient,
    records: list[ZoteroPaper],
    stats: ZoteroSyncStats,
) -> list[ZoteroPaper]:
    """Keep only deduplicated papers with a stored Zotero PDF attachment."""
    by_parent: dict[str, list[dict[str, Any]]] = {}
    for attachment in client.iter_attachments():
        data = attachment.get("data") or {}
        parent_key = str(data.get("parentItem") or "")
        if parent_key:
            by_parent.setdefault(parent_key, []).append(attachment)

    backed: list[ZoteroPaper] = []
    raw_item_keys: set[str] = set()
    attachment_keys: set[str] = set()
    for record in records:
        item_keys = _record_item_keys(record)
        pdf_attachments = _pdf_attachment_candidates(
            [
                attachment
                for item_key in item_keys
                for attachment in by_parent.get(item_key, [])
            ]
        )
        if not pdf_attachments:
            continue
        backed.append(record)
        raw_item_keys.update(
            str((attachment.get("data") or {}).get("parentItem") or "")
            for attachment in pdf_attachments
        )
        attachment_keys.update(
            str(
                attachment.get("key")
                or (attachment.get("data") or {}).get("key")
                or ""
            )
            for attachment in pdf_attachments
        )

    stats.pdf_backed_papers = len(backed)
    stats.pdf_backed_raw_items = len(raw_item_keys)
    stats.pdf_attachment_rows = len(attachment_keys - {""})
    stats.papers_without_pdf = len(records) - len(backed)
    return backed


def zotero_item_to_paper(
    item: dict[str, Any],
    *,
    group_id: str,
    collection_key: str,
    tier: str,
    corpus_source: str,
) -> ZoteroPaper | None:
    data = item.get("data") or {}
    item_type = str(data.get("itemType") or "")
    title = str(data.get("title") or "").strip()
    item_key = str(item.get("key") or data.get("key") or "").strip()
    if item_type in _NON_BIBLIOGRAPHIC_TYPES or not title or not item_key:
        return None

    doi = _normalize_zotero_doi(data.get("DOI"))
    authors = _authors(data.get("creators"))
    year = _year(data.get("date") or (item.get("meta") or {}).get("parsedDate"))
    paper_id = (
        "DOI:" + doi.replace("/", "_")
        if doi
        else f"ZOTERO:{group_id}:{item_key}"
    )
    tags = [
        str(tag.get("tag") or "").strip()
        for tag in data.get("tags") or []
        if isinstance(tag, dict) and str(tag.get("tag") or "").strip()
    ]
    venue = next(
        (
            str(data.get(field)).strip()
            for field in (
                "publicationTitle",
                "conferenceName",
                "bookTitle",
                "proceedingsTitle",
                "university",
            )
            if data.get(field)
        ),
        None,
    )
    item_version = int(item.get("version") or data.get("version") or 0)
    return ZoteroPaper(
        paper_id=paper_id,
        title=title,
        abstract=str(data.get("abstractNote") or "").strip() or None,
        authors=authors,
        year=year,
        doi=doi,
        venue=venue,
        keywords=list(dict.fromkeys(tags)),
        item_key=item_key,
        item_version=item_version,
        retrieval_tiers={tier},
        corpus_sources={corpus_source},
        collection_keys={collection_key},
        source_items=[item],
    )


def sync_zotero_corpus(
    session: Session,
    client: ZoteroClient,
    specs: list[ZoteroCollectionSpec],
    *,
    replace: bool = False,
    backup_reference: str | None = None,
    limit: int | None = None,
    download_fulltexts: bool = False,
    allowed_paper_ids: set[str] | None = None,
) -> ZoteroSyncStats:
    from app.config import settings

    if replace and not str(backup_reference or "").strip():
        raise ValueError(
            "A verified AWS backup reference is required before corpus replacement"
        )
    if settings.sdl_stage1_only:
        _validate_stage1_specs(specs)
        if not replace:
            validate_stage1_corpus(session)

    records, stats = collect_zotero_papers(
        client,
        specs,
        limit=limit,
        pdf_backed_only=settings.sdl_stage1_only,
    )
    if allowed_paper_ids is not None:
        available_ids = {record.paper_id for record in records}
        missing = sorted(allowed_paper_ids - available_ids)
        if missing:
            raise ValueError(
                "S3 Markdown manifests reference papers outside the "
                f"authoritative Tier 1 collection (examples: {missing[:5]})"
            )
        records = [
            record for record in records
            if record.paper_id in allowed_paper_ids
        ]
        stats.manifest_backed_papers = len(records)
        stats.unique_papers = len(records)
    if not records:
        raise ValueError("Zotero returned no valid papers; refusing to modify the corpus")

    if replace:
        stats.papers_before_replace = session.scalar(
            select(func.count(Paper.id))
        ) or 0
        clear_application_data(session)
        seed_reference_data(session)

    inserted, updated = upsert_zotero_papers(
        session,
        records,
        backup_reference=backup_reference,
    )
    stats.inserted = inserted
    stats.updated = updated

    if settings.sdl_stage1_only:
        validate_stage1_corpus(session)
    else:
        from app.services.lab_service import load_labs_from_yaml, map_papers_to_labs

        load_labs_from_yaml(session)
        map_papers_to_labs(session)
    session.commit()

    if download_fulltexts:
        ingest_zotero_fulltexts(session, client, records, stats)
    return stats


def clear_application_data(session: Session) -> None:
    """Clear every application table while preserving Alembic schema state."""
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.flush()


def seed_reference_data(session: Session) -> None:
    """Restore non-paper vocabularies after a full data replacement."""
    from app.adapters import CsvPaperSource
    from app.config import settings
    from app.services.ingestion_service import (
        ingest_institutions,
        ingest_people,
        ingest_topics,
    )

    source = CsvPaperSource(
        papers_csv=settings.papers_csv,
        people_csv=settings.people_csv,
        institutions_csv=settings.institutions_csv,
        topics_yaml=settings.topics_yaml,
    )
    if not settings.sdl_stage1_only:
        ingest_institutions(session, source)
        ingest_people(session, source)
    ingest_topics(session, source)


def _validate_stage1_specs(specs: list[ZoteroCollectionSpec]) -> None:
    from app.config import settings

    expected = [
        ZoteroCollectionSpec(
            tier="tier1",
            identifier=settings.zotero_tier1_collection,
            corpus_source="STRICT_SDL_KEYWORD",
        )
    ]
    if specs != expected:
        raise ValueError(
            "SDL Stage 1 accepts only the configured Zotero Tier 1 collection"
        )


def validate_stage1_corpus(
    session: Session,
    *,
    require_nonempty: bool = False,
) -> int:
    """Fail closed if any persisted paper is not authoritative Tier 1 data."""
    from app.config import settings
    from app.models import (
        AcCorePaper,
        HumanReview,
        Institution,
        PaperClassification,
        PaperEvidence,
        PaperLabLink,
        SdlLab,
    )

    invalid: list[str] = []
    papers = list(session.execute(select(Paper)).scalars())
    if require_nonempty and not papers:
        raise ValueError("SDL Stage 1 corpus is empty")
    for paper in papers:
        zotero = dict((paper.raw_metadata or {}).get("zotero") or {})
        if (
            paper.source != "zotero"
            or paper.provenance != "zotero_group"
            or paper.retrieval_tier != "tier1"
            or paper.corpus_sources != ["STRICT_SDL_KEYWORD"]
            or paper.ac_known_publication
            or paper.ac_acknowledged is not None
            or paper.ac_highly_relevant is not None
            or paper.ac_high_impact is not None
            or paper.ac_members_matched is not None
            or paper.ac_programs is not None
            or paper.ac_attribution_score is not None
            or zotero.get("collection_keys")
            != [settings.zotero_tier1_collection]
        ):
            invalid.append(paper.id)
            if len(invalid) == 5:
                break
    if invalid:
        raise ValueError(
            "SDL Stage 1 corpus contains non-Tier-1 records; run the verified "
            f"replacement cutover first (examples: {invalid})"
        )
    forbidden_counts = {
        "ac_core_papers": session.scalar(select(func.count(AcCorePaper.id))) or 0,
        "ac_authors": session.scalar(
            select(func.count(Author.id)).where(Author.is_ac_member.is_(True))
        )
        or 0,
        "partner_institutions": session.scalar(
            select(func.count(Institution.id)).where(
                Institution.is_partner.is_(True)
            )
        )
        or 0,
        "sdl_labs": session.scalar(select(func.count(SdlLab.id))) or 0,
        "paper_lab_links": session.scalar(select(func.count(PaperLabLink.paper_id)))
        or 0,
        "ac_classifications": sum(
            1
            for classification in session.scalars(select(PaperClassification))
            if classification.ac_attribution_label is not None
            or classification.author_score != 0.0
            or classification.institution_score != 0.0
            or classification.network_score != 0.0
            or classification.citation_score != 0.0
            or classification.funding_signal != 0.0
            or classification.acknowledgement_signal != 0.0
            or bool(classification.graph_signals)
        ),
        "ac_evidence": session.scalar(
            select(func.count(PaperEvidence.id)).where(
                PaperEvidence.evidence_type.in_(
                    {
                        "funding_acknowledgement",
                        "partner_institution_acknowledgement",
                    }
                )
            )
        )
        or 0,
        "ac_or_legacy_reviews": session.scalar(
            select(func.count(HumanReview.id)).where(
                (HumanReview.human_label.is_not(None))
                | (HumanReview.ac_relevance_judgement.is_not(None))
            )
        )
        or 0,
    }
    present = {name: count for name, count in forbidden_counts.items() if count}
    if present:
        raise ValueError(
            "SDL Stage 1 contains forbidden AC-derived state: "
            f"{present}"
        )
    return len(papers)


def upsert_zotero_papers(
    session: Session,
    records: list[ZoteroPaper],
    *,
    backup_reference: str | None = None,
) -> tuple[int, int]:
    inserted = 0
    updated = 0
    for record in records:
        paper = session.get(Paper, record.paper_id)
        if paper is None and record.doi:
            paper = session.execute(
                select(Paper).where(Paper.doi == record.doi)
            ).scalar_one_or_none()
        if paper is None:
            paper = Paper(id=record.paper_id, title=record.title)
            session.add(paper)
            inserted += 1
        else:
            updated += 1

        tiers = sorted(record.retrieval_tiers)
        query_strings = [
            retrieval_query(tier) for tier in tiers if retrieval_query(tier)
        ]
        paper.title = record.title
        paper.abstract = record.abstract
        paper.doi = record.doi
        paper.year = record.year
        paper.venue = record.venue
        paper.source = "zotero"
        paper.provenance = "zotero_group"
        paper.corpus_sources = sorted(record.corpus_sources)
        paper.keywords = record.keywords
        paper.retrieval_tier = "+".join(tiers)
        paper.merge_tier_membership = "+".join(
            tier.removeprefix("tier") for tier in tiers
        )
        paper.query_string = "\n\n---\n\n".join(query_strings) or None
        paper.ac_known_publication = False
        paper.ac_acknowledged = None
        paper.ac_highly_relevant = None
        paper.ac_high_impact = None
        paper.ac_members_matched = None
        paper.ac_programs = None
        raw_metadata = dict(paper.raw_metadata or {})
        raw_metadata.update({
            "zotero": {
                "group_id": record.source_items[0].get("library", {}).get(
                    "id"
                ),
                "primary_item_key": record.item_key,
                "primary_item_version": record.item_version,
                "collection_keys": sorted(record.collection_keys),
                "retrieval_tiers": tiers,
                "items": record.source_items,
                "synced_at": datetime.now(UTC).isoformat(),
            },
            "corpus_replacement_backup": backup_reference,
        })
        paper.raw_metadata = raw_metadata
        _replace_author_links(session, paper, record.authors)
    session.flush()
    return inserted, updated


def ingest_zotero_fulltexts(
    session: Session,
    client: ZoteroClient,
    records: list[ZoteroPaper],
    stats: ZoteroSyncStats,
    *,
    max_exports: int | None = None,
) -> None:
    """Export Zotero PDFs as Markdown and publish one ETL-ready batch marker.

    Source PDFs live only in the Fargate task's temporary directory. The S3
    ``raw/`` prefix receives Markdown only; manifests are written separately
    and the batch manifest is uploaded last so downstream ETL cannot observe a
    partial export. ``max_exports`` caps successful Markdown documents, not
    attempted Zotero attachments, because some attachment records have no
    downloadable file.
    """
    from app.config import settings
    from app.services.pdf_parser import convert_file_to_markdown
    from app.services.s3_storage import get_s3_client, put_file

    if not settings.s3_artifacts_bucket:
        raise RuntimeError(
            "PAS_S3_ARTIFACTS_BUCKET is required for Zotero Markdown export"
        )
    if max_exports is not None and max_exports <= 0:
        raise ValueError("max_exports must be positive")

    by_parent: dict[str, list[dict[str, Any]]] = {}
    for attachment in client.iter_attachments():
        data = attachment.get("data") or {}
        parent_key = str(data.get("parentItem") or "")
        if parent_key:
            by_parent.setdefault(parent_key, []).append(attachment)

    s3_client = get_s3_client()
    existing_item_keys = (
        _existing_zotero_item_keys(
            s3_client,
            settings.s3_artifacts_bucket,
            client.group_id,
        )
        if s3_client is not None
        else set()
    )
    document_manifest_keys: list[str] = []
    run_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    with tempfile.TemporaryDirectory(prefix="pas-zotero-fulltext-") as tmp:
        tmpdir = Path(tmp)
        for record in records:
            if (
                max_exports is not None
                and stats.markdown_exported >= max_exports
            ):
                break
            paper = session.get(Paper, record.paper_id)
            if paper is None:
                continue
            item_keys = _record_item_keys(record)
            if item_keys & existing_item_keys:
                stats.markdown_skipped_existing += 1
                continue
            candidates = [
                attachment
                for item_key in item_keys
                for attachment in by_parent.get(item_key, [])
            ]
            pdf_attachments = _pdf_attachment_candidates(candidates)
            if not pdf_attachments:
                stats.fulltexts_missing += 1
                stats.markdown_missing += 1
                continue
            try:
                download_errors: list[str] = []
                for attachment in pdf_attachments:
                    data = attachment.get("data") or {}
                    attachment_key = str(
                        attachment.get("key") or data.get("key") or ""
                    )
                    attachment_version = int(attachment.get("version") or 0)
                    filename = str(
                        data.get("filename") or f"{paper.id}.pdf"
                    )
                    try:
                        download = client.download_attachment(
                            attachment_key, filename=filename
                        )
                        if not _is_pdf(download, filename):
                            raise ValueError(
                                "attachment is not a downloadable PDF"
                            )
                        break
                    except Exception as exc:
                        download_errors.append(
                            f"{attachment_key}:{type(exc).__name__}"
                        )
                else:
                    raise RuntimeError(
                        "no downloadable PDF attachment; attempted "
                        + ", ".join(download_errors)
                    )
                source_sha256 = hashlib.sha256(download.content).hexdigest()
                local_path = tmpdir / f"{attachment_key}.pdf"
                local_path.write_bytes(download.content)
                (
                    markdown,
                    converter,
                    converter_version,
                    inspection,
                ) = convert_file_to_markdown(local_path)
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
                artifact_suffix = (
                    f"group={client.group_id}/item={record.item_key}/"
                    f"attachment={attachment_key}/version={attachment_version}"
                )
                markdown_key = put_file(
                    f"raw/zotero/{artifact_suffix}",
                    "document.md",
                    markdown_bytes,
                    "text/markdown; charset=utf-8",
                    require_s3=True,
                )
                if markdown_key is None:
                    raise RuntimeError("failed to persist Zotero Markdown to S3")
                created_at = datetime.now(UTC).isoformat()
                manifest = {
                    "schema_version": 1,
                    "kind": "zotero_markdown_document",
                    "status": "ready",
                    "paper_id": paper.id,
                    "idempotency_key": idempotency_key,
                    "created_at": created_at,
                    "zotero": {
                        "group_id": client.group_id,
                        "item_key": record.item_key,
                        "item_version": record.item_version,
                        "attachment_key": attachment_key,
                        "attachment_version": attachment_version,
                        "collection_keys": sorted(record.collection_keys),
                    },
                    "source": {
                        "filename": filename,
                        "media_type": "application/pdf",
                        "sha256": source_sha256,
                        "persisted": False,
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
                manifest_key = put_file(
                    f"manifests/zotero/{artifact_suffix}",
                    "document-manifest.json",
                    json.dumps(
                        manifest, ensure_ascii=False, sort_keys=True
                    ).encode("utf-8"),
                    "application/json",
                    require_s3=True,
                )
                if manifest_key is None:
                    raise RuntimeError("failed to persist Zotero document manifest")
                document_manifest_keys.append(manifest_key)
                raw = dict(paper.raw_metadata or {})
                prior_fulltext = dict(raw.get("zotero_fulltext") or {})
                if not (
                    prior_fulltext.get("status") == "etl_complete"
                    and prior_fulltext.get("idempotency_key")
                    == idempotency_key
                ):
                    raw["zotero_fulltext"] = {
                        "status": "markdown_ready",
                        "idempotency_key": idempotency_key,
                        "attachment_key": attachment_key,
                        "attachment_version": attachment_version,
                        "source_sha256": source_sha256,
                        "markdown_sha256": markdown_sha256,
                        "markdown_key": markdown_key,
                        "manifest_key": manifest_key,
                        "filename": filename,
                    }
                paper.raw_metadata = raw
                session.commit()
                stats.markdown_exported += 1
            except Exception as exc:
                session.rollback()
                stats.fulltexts_failed += 1
                stats.markdown_failed += 1
                error = {
                    "paper_id": record.paper_id,
                    "attachment_key": attachment_key,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                stats.fulltext_errors.append(
                    error
                )
                stats.markdown_errors.append(error)

    if document_manifest_keys:
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
                        collection_key
                        for record in records
                        for collection_key in record.collection_keys
                    }
                ),
            },
            "document_manifest_keys": document_manifest_keys,
            "documents": len(document_manifest_keys),
        }
        stats.batch_manifest_key = put_file(
            f"manifests/zotero/runs/{run_id}",
            "batch-manifest.json",
            json.dumps(
                batch_manifest, ensure_ascii=False, sort_keys=True
            ).encode("utf-8"),
            "application/json",
            require_s3=True,
        )
        if stats.batch_manifest_key is None:
            raise RuntimeError("failed to publish Zotero ETL batch manifest")


def require_complete_zotero_pdf_markdown(
    inspection: dict[str, object],
) -> None:
    """Reject Markdown that was not verified as complete PDF text."""
    quality_status = str(inspection.get("quality_status") or "")
    if quality_status != "complete_text":
        raise ValueError(
            "Zotero PDF Markdown did not pass the complete-text quality gate "
            f"(quality_status={quality_status or 'missing'})"
        )


def _replace_author_links(
    session: Session, paper: Paper, author_names: list[str]
) -> None:
    for link in list(paper.authors):
        session.delete(link)
    session.flush()
    seen: set[str] = set()
    for order, name in enumerate(author_names):
        normalized = normalize_name(name)
        if not normalized:
            continue
        matches = list(
            session.execute(
                select(Author).where(Author.normalized_name == normalized)
            ).scalars()
        )
        if len(matches) == 1:
            author = matches[0]
        else:
            author_id = _stable_id("auth_zotero", normalized)
            author = session.get(Author, author_id)
            if author is None:
                author = Author(
                    id=author_id,
                    canonical_name=name,
                    aliases=[],
                    normalized_name=normalized,
                    is_ac_member=False,
                    raw_metadata={"source": "zotero"},
                )
                session.add(author)
                session.flush()
        if author.id in seen:
            continue
        seen.add(author.id)
        session.add(
            PaperAuthor(
                paper_id=paper.id,
                author_id=author.id,
                author_order=order,
                match_confidence=1.0,
            )
        )


def _authors(creators: object) -> list[str]:
    result: list[str] = []
    for creator in creators if isinstance(creators, list) else []:
        if not isinstance(creator, dict) or creator.get("creatorType") != "author":
            continue
        name = str(creator.get("name") or "").strip()
        if not name:
            name = " ".join(
                part
                for part in (
                    str(creator.get("firstName") or "").strip(),
                    str(creator.get("lastName") or "").strip(),
                )
                if part
            )
        if name:
            result.append(name)
    return list(dict.fromkeys(result))


def _year(value: object) -> int | None:
    match = _YEAR_RE.search(str(value or ""))
    return int(match.group(1)) if match else None


def _normalize_zotero_doi(value: object) -> str | None:
    text = _DOI_PREFIX_RE.sub("", str(value or "").strip()).rstrip(".,; ")
    return normalize_doi(text)


def _dedup_identity(record: ZoteroPaper) -> str:
    if record.doi:
        return f"doi:{record.doi}"
    first_author = normalize_name(record.authors[0]) if record.authors else ""
    title = re.sub(r"[^a-z0-9]+", " ", record.title.casefold()).strip()
    return f"fallback:{title}|{record.year}|{first_author}"


def _merge_records(left: ZoteroPaper, right: ZoteroPaper) -> ZoteroPaper:
    primary, secondary = (
        (right, left)
        if _completeness(right) > _completeness(left)
        else (left, right)
    )
    primary.retrieval_tiers |= secondary.retrieval_tiers
    primary.corpus_sources |= secondary.corpus_sources
    primary.collection_keys |= secondary.collection_keys
    primary.source_items.extend(secondary.source_items)
    primary.keywords = list(dict.fromkeys([*primary.keywords, *secondary.keywords]))
    return primary


def _completeness(record: ZoteroPaper) -> tuple[int, int]:
    fields = (
        record.abstract,
        record.authors,
        record.year,
        record.doi,
        record.venue,
        record.keywords,
    )
    return sum(bool(value) for value in fields), record.item_version


def _select_pdf_attachment(
    attachments: list[dict[str, Any]],
) -> dict[str, Any] | None:
    candidates = _pdf_attachment_candidates(attachments)
    return candidates[0] if candidates else None


def _record_item_keys(record: ZoteroPaper) -> set[str]:
    return {
        record.item_key,
        *[
            str(
                item.get("key")
                or (item.get("data") or {}).get("key")
                or ""
            )
            for item in record.source_items
        ],
    } - {""}


def _existing_zotero_item_keys(
    client: Any,
    bucket: str,
    group_id: str,
) -> set[str]:
    prefix = f"raw/zotero/group={group_id}/"
    keys: set[str] = set()
    for page in client.get_paginator("list_objects_v2").paginate(
        Bucket=bucket,
        Prefix=prefix,
    ):
        for row in page.get("Contents", []):
            for part in str(row.get("Key") or "").split("/"):
                if part.startswith("item="):
                    keys.add(part.removeprefix("item="))
                    break
    return keys


def _pdf_attachment_candidates(
    attachments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates = []
    for attachment in attachments:
        data = attachment.get("data") or {}
        if data.get("linkMode") not in {"imported_file", "imported_url"}:
            continue
        content_type = str(data.get("contentType") or "").lower()
        filename = str(data.get("filename") or "").lower()
        if content_type == "application/pdf" or filename.endswith(".pdf"):
            candidates.append(attachment)
    return sorted(
        candidates,
        key=lambda row: (
            (row.get("data") or {}).get("linkMode") == "imported_file",
            int(row.get("version") or 0),
            str(row.get("key") or ""),
        ),
        reverse=True,
    )


def _is_pdf(download: ZoteroDownload, filename: str) -> bool:
    return (
        download.content_type == "application/pdf"
        or filename.lower().endswith(".pdf")
        or download.content.startswith(b"%PDF-")
    )


def _stable_id(prefix: str, *parts: str) -> str:
    seed = "|".join(str(part).casefold() for part in parts)
    return f"{prefix}_{uuid.uuid5(uuid.NAMESPACE_URL, seed).hex[:12]}"
