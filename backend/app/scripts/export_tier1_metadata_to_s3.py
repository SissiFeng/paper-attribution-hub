"""Export the latest Tier 1 metadata snapshot to S3 and verify every object."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import settings
from app.db import SessionLocal, init_database
from app.services.tier1_metadata_snapshot import (
    build_tier1_metadata_snapshot,
    upload_tier1_metadata_snapshot,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build an immutable Tier 1 metadata snapshot, upload it under "
            "raw/metadata/tier1, and download-verify every S3 object."
        )
    )
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument(
        "--bucket",
        default=settings.s3_artifacts_bucket,
        help="S3 artifact bucket; defaults to PAS_S3_ARTIFACTS_BUCKET.",
    )
    parser.add_argument(
        "--region",
        default=settings.aws_region,
        help="AWS region; defaults to PAS_AWS_REGION.",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Optional local AWS profile. ECS should omit this option.",
    )
    args = parser.parse_args()
    if not args.bucket:
        raise RuntimeError("--bucket or PAS_S3_ARTIFACTS_BUCKET is required")

    init_database()
    with SessionLocal() as session:
        snapshot = build_tier1_metadata_snapshot(session, args.csv)
    aws = boto3.Session(profile_name=args.profile, region_name=args.region)
    result = upload_tier1_metadata_snapshot(
        snapshot,
        s3_client=aws.client("s3"),
        bucket=args.bucket,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (BotoCoreError, ClientError, RuntimeError, ValueError) as exc:
        print(
            f"Tier 1 metadata export failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
