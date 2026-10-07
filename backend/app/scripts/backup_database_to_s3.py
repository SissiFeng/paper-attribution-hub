"""Create a fail-closed database backup in the configured AWS S3 bucket."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy.engine import make_url

from app.config import settings


def main() -> int:
    if not settings.s3_artifacts_bucket:
        raise RuntimeError("PAS_S3_ARTIFACTS_BUCKET is required")

    created_at = datetime.now(UTC)
    stamp = created_at.strftime("%Y%m%dT%H%M%SZ")
    url = make_url(settings.database_url)
    extension = ".sqlite3" if url.get_backend_name() == "sqlite" else ".dump"
    key_prefix = f"database-backups/{stamp}"
    dump_key = f"{key_prefix}/paper_attribution{extension}"

    with tempfile.TemporaryDirectory(prefix="pas-db-backup-") as tmp:
        backup_path = Path(tmp) / f"paper_attribution{extension}"
        if url.get_backend_name() == "sqlite":
            _backup_sqlite(Path(url.database or ""), backup_path)
        elif url.get_backend_name().startswith("postgresql"):
            _backup_postgres(backup_path)
        else:
            raise RuntimeError(
                f"Unsupported backup database: {url.get_backend_name()}"
            )

        content_sha256 = _sha256(backup_path)
        size = backup_path.stat().st_size
        client = boto3.client("s3", region_name=settings.aws_region)
        client.upload_file(
            str(backup_path),
            settings.s3_artifacts_bucket,
            dump_key,
            ExtraArgs={
                "ServerSideEncryption": "AES256",
                "Metadata": {"sha256": content_sha256},
            },
        )
        head = client.head_object(
            Bucket=settings.s3_artifacts_bucket,
            Key=dump_key,
        )
        if int(head.get("ContentLength") or -1) != size:
            raise RuntimeError("S3 backup verification failed: size mismatch")
        if (head.get("Metadata") or {}).get("sha256") != content_sha256:
            raise RuntimeError("S3 backup verification failed: hash metadata mismatch")

        backup_reference = (
            f"s3://{settings.s3_artifacts_bucket}/{dump_key}"
        )
        manifest = {
            "backup_reference": backup_reference,
            "created_at": created_at.isoformat(),
            "database_backend": url.get_backend_name(),
            "sha256": content_sha256,
            "bytes": size,
        }
        manifest_key = f"{key_prefix}/manifest.json"
        client.put_object(
            Bucket=settings.s3_artifacts_bucket,
            Key=manifest_key,
            Body=json.dumps(manifest, indent=2).encode("utf-8"),
            ContentType="application/json",
            ServerSideEncryption="AES256",
        )

    print(json.dumps(manifest, indent=2))
    return 0


def _backup_sqlite(source: Path, target: Path) -> None:
    if not source.exists():
        raise RuntimeError(f"SQLite database does not exist: {source}")
    with sqlite3.connect(source) as source_db, sqlite3.connect(target) as target_db:
        source_db.backup(target_db)


def _backup_postgres(target: Path) -> None:
    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        raise RuntimeError("pg_dump is required for PostgreSQL backups")
    env = os.environ.copy()
    env["PGDATABASE"] = settings.database_url
    result = subprocess.run(
        [
            pg_dump,
            "--format=custom",
            "--no-owner",
            "--no-acl",
            "--file",
            str(target),
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        message = (result.stderr or "pg_dump failed").strip().splitlines()[-1]
        raise RuntimeError(f"pg_dump failed: {message}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (BotoCoreError, ClientError, RuntimeError) as exc:
        print(f"Database backup failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
