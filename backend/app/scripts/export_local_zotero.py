"""Export local Zotero Tier 1 PDFs to the existing S3 Markdown ETL."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import boto3

from app.config import settings
from app.services.s3_storage import get_file, get_s3_client
from app.services.zotero_client import ZoteroClient
from app.services.zotero_ingestion_service import (
    collect_zotero_papers,
    configured_collection_specs,
)
from app.services.zotero_local_export_service import (
    export_local_zotero_fulltexts,
)


_STAGE1_ROLES = {"train", "validation", "frozen_test", "pool"}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Export PDFs from local Zotero storage without uploading source "
            "PDF bytes."
        )
    )
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument("--split-manifest-key", default="")
    parser.add_argument(
        "--roles",
        default="train",
        help="Comma-separated Stage 1 roles; default: train",
    )
    parser.add_argument(
        "--all-tier1",
        action="store_true",
        help=(
            "Acquire every paper in the authoritative Tier 1 collection. "
            "This bypasses model-role filtering but does not run ETL, "
            "training, validation, or classification."
        ),
    )
    parser.add_argument("--max-exports", type=int, default=None)
    parser.add_argument(
        "--ocr-backend",
        choices=("none", "docling"),
        default="none",
        help=(
            "OCR fallback for PDFs rejected by pdf-inspector. "
            "Use docling only in the dedicated OCR worker environment."
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--release-frozen-test", action="store_true")
    parser.add_argument(
        "--api-key-ssm-parameter",
        default="",
        help="Read the Zotero key from SSM when PAS_ZOTERO_API_KEY is unset.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not settings.sdl_stage1_only:
        raise ValueError("PAS_SDL_STAGE1_ONLY=true is required")
    roles = {
        role.strip()
        for role in args.roles.split(",")
        if role.strip()
    }
    unknown = roles - _STAGE1_ROLES
    if not roles or unknown:
        raise ValueError(f"Invalid Stage 1 roles: {sorted(unknown)}")
    if (
        not args.all_tier1
        and "frozen_test" in roles
        and not args.release_frozen_test
    ):
        raise ValueError(
            "frozen_test is sealed; pass --release-frozen-test only after "
            "model selection is complete"
        )

    s3_client = get_s3_client()
    if s3_client is None:
        raise RuntimeError("Authenticated S3 access is required")
    split = None
    assignments: list[dict] = []
    role_paper_ids: set[str] = set()
    if not args.all_tier1:
        if not args.split_manifest_key:
            raise ValueError(
                "--split-manifest-key is required unless --all-tier1 is used"
            )
        split_bytes = get_file(
            args.split_manifest_key,
            s3_client=s3_client,
            require_s3=True,
        )
        if split_bytes is None:
            raise FileNotFoundError(args.split_manifest_key)
        split = json.loads(split_bytes)
        if split.get("frozen_test_policy") != (
            "release_once_after_model_selection"
        ):
            raise ValueError("Unexpected Stage 1 frozen-test policy")
        raw_assignments = split.get("assignments")
        if not isinstance(raw_assignments, list):
            raise ValueError("Stage 1 split manifest has no assignments")
        assignments = raw_assignments
        role_paper_ids = {
            str(row["paper_id"])
            for row in assignments
            if row.get("role") in roles
        }

    api_key = settings.zotero_api_key
    if not api_key and args.api_key_ssm_parameter:
        api_key = boto3.client(
            "ssm",
            region_name=settings.aws_region,
        ).get_parameter(
            Name=args.api_key_ssm_parameter,
            WithDecryption=True,
        )["Parameter"]["Value"]
    if not api_key:
        raise ValueError(
            "PAS_ZOTERO_API_KEY or --api-key-ssm-parameter is required"
        )

    with ZoteroClient(
        api_key=api_key,
        group_id=settings.zotero_group_id,
        base_url=settings.zotero_api_url,
    ) as client:
        client.verify_key()
        records, corpus_stats = collect_zotero_papers(
            client,
            configured_collection_specs(),
            pdf_backed_only=True,
        )
        record_ids = {record.paper_id for record in records}
        if split is not None:
            assignment_ids = {
                str(row["paper_id"]) for row in assignments
            }
            if (
                corpus_stats.unique_papers
                != int(split.get("unique_papers") or 0)
                or record_ids != assignment_ids
            ):
                raise ValueError(
                    "Live Tier 1 corpus no longer matches the frozen split manifest"
                )
        allowed_paper_ids = record_ids if args.all_tier1 else role_paper_ids
        stats = export_local_zotero_fulltexts(
            client,
            records,
            storage_root=args.storage_root,
            allowed_paper_ids=allowed_paper_ids,
            max_exports=args.max_exports,
            ocr_backend=(
                None if args.ocr_backend == "none" else args.ocr_backend
            ),
            dry_run=args.dry_run,
            s3_client=s3_client,
        )

    payload = {
        "scope": {
            "group_id": settings.zotero_group_id,
            "collection_key": settings.zotero_tier1_collection,
            "split_manifest_key": args.split_manifest_key,
            "acquisition_scope": (
                "all_tier1" if args.all_tier1 else "stage1_roles"
            ),
            "roles": [] if args.all_tier1 else sorted(roles),
            "frozen_test_released": args.release_frozen_test,
            "classification_enabled": False,
        },
        "dry_run": args.dry_run,
        **stats.to_dict(),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            "Local Zotero export complete:",
            f"found={stats.local_pdfs_found}",
            f"existing={stats.skipped_existing}",
            f"exported={stats.markdown_exported}",
            f"ocr={stats.ocr_required}",
            f"failed={stats.markdown_failed}",
            f"batch={stats.batch_manifest_key or 'none'}",
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(
            f"Local Zotero export failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1)
