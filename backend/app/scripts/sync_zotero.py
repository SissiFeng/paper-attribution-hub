"""Synchronize authoritative Zotero Tier 1/Tier 2 collections into PAS."""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.config import settings
from app.db import SessionLocal, init_database
from app.models import Paper, PipelineRun
from app.services.zotero_client import ZoteroClient
from app.services.zotero_ingestion_service import (
    collect_zotero_papers,
    configured_collection_specs,
    sync_zotero_corpus,
)
from app.services.zotero_manifest_service import (
    inventory_ready_zotero_manifests,
    publish_manifest_replay_batch,
)


def _client() -> ZoteroClient:
    if not settings.zotero_group_id:
        raise ValueError("PAS_ZOTERO_GROUP_ID is required")
    return ZoteroClient(
        api_key=settings.zotero_api_key,
        group_id=settings.zotero_group_id,
        base_url=settings.zotero_api_url,
    )


def _specs(tier: str):
    specs = configured_collection_specs()
    return specs if tier == "all" else [spec for spec in specs if spec.tier == tier]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Synchronize Zotero group collections into PAS."
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--replace-corpus", action="store_true")
    parser.add_argument(
        "--backup-reference",
        default=settings.corpus_backup_reference,
        help="Verified s3:// backup or RDS snapshot reference; required for replacement.",
    )
    parser.add_argument("--seed-if-empty", action="store_true")
    parser.add_argument("--download-fulltexts", action="store_true")
    parser.add_argument("--classify", action="store_true")
    parser.add_argument(
        "--manifest-backed-only",
        action="store_true",
        help=(
            "Restrict the replacement corpus to unique verified Markdown "
            "document manifests already present in S3."
        ),
    )
    parser.add_argument(
        "--publish-replay-batch",
        action="store_true",
        help="Publish one ETL batch containing the selected unique manifests.",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--tier", choices=("tier1", "tier2", "all"), default="tier1"
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if settings.sdl_stage1_only and args.tier != "tier1":
        raise ValueError("SDL Stage 1 permits only --tier tier1")
    if args.replace_corpus and args.limit is not None:
        raise ValueError(
            "--replace-corpus cannot be combined with --limit; "
            "run the pilot against a separate database"
        )

    init_database()
    specs = _specs(args.tier)
    if not specs:
        raise ValueError(f"No configured Zotero collection for {args.tier}")

    manifest_inventory = None
    if args.manifest_backed_only or args.publish_replay_batch:
        manifest_inventory = inventory_ready_zotero_manifests(
            settings.zotero_group_id,
            collection_key=settings.zotero_tier1_collection,
        )
    if args.publish_replay_batch and not args.manifest_backed_only:
        raise ValueError(
            "--publish-replay-batch requires --manifest-backed-only"
        )

    with _client() as client:
        if settings.zotero_api_key:
            client.verify_key()
        if args.dry_run:
            records, stats = collect_zotero_papers(
                client,
                specs,
                limit=args.limit,
                pdf_backed_only=settings.sdl_stage1_only,
            )
            if manifest_inventory is not None:
                available_ids = {record.paper_id for record in records}
                missing = sorted(manifest_inventory.paper_ids - available_ids)
                if missing:
                    raise ValueError(
                        "S3 Markdown manifests reference papers outside the "
                        "authoritative Tier 1 collection "
                        f"(examples: {missing[:5]})"
                    )
                records = [
                    record for record in records
                    if record.paper_id in manifest_inventory.paper_ids
                ]
                stats.manifest_backed_papers = len(records)
                stats.unique_papers = len(records)
            payload = stats.to_dict()
            payload["sample_paper_ids"] = [row.paper_id for row in records[:10]]
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0

        with SessionLocal() as session:
            if args.seed_if_empty:
                paper_count = session.scalar(select(func.count(Paper.id))) or 0
                if paper_count:
                    print(
                        f"Zotero seed skipped: database already has {paper_count} papers"
                    )
                    return 0

            started_at = datetime.now(UTC)
            stats = sync_zotero_corpus(
                session,
                client,
                specs,
                replace=args.replace_corpus,
                backup_reference=args.backup_reference,
                limit=args.limit,
                download_fulltexts=(
                    args.download_fulltexts or settings.zotero_download_fulltexts
                ),
                allowed_paper_ids=(
                    manifest_inventory.paper_ids
                    if manifest_inventory is not None
                    else None
                ),
            )
            if args.publish_replay_batch:
                stats.batch_manifest_key = publish_manifest_replay_batch(
                    manifest_inventory,
                    collection_key=settings.zotero_tier1_collection,
                )

            classified = 0
            refreshed = 0
            if args.classify:
                from app.services.relevance_classifier import classify_new

                touched, classified, refreshed = classify_new(session)
                session.commit()
                _ = touched

            finished_at = datetime.now(UTC)
            run = PipelineRun(
                id=f"zotero_{uuid.uuid4().hex[:12]}",
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=(finished_at - started_at).total_seconds(),
                auto_ingested=stats.inserted,
                classified_new=classified,
                reclassified_stale=refreshed,
                status="success",
                steps=[
                    {
                        "name": "zotero_sync",
                        "status": "ok",
                        **stats.to_dict(),
                        "replace_corpus": args.replace_corpus,
                        "backup_reference": args.backup_reference or None,
                    }
                ],
                triggered_by="zotero_cli",
            )
            session.add(run)
            session.commit()

    payload = {
        **stats.to_dict(),
        "classified_new": classified,
        "reclassified_stale": refreshed,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(
            "Zotero sync complete:",
            f"seen={stats.seen_items}",
            f"unique={stats.unique_papers}",
            f"inserted={stats.inserted}",
            f"updated={stats.updated}",
            f"duplicates={stats.duplicates_merged}",
            f"markdown_exported={stats.markdown_exported}",
            f"markdown_failures={stats.markdown_failed}",
            f"batch_manifest={stats.batch_manifest_key or 'none'}",
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"Zotero sync failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
