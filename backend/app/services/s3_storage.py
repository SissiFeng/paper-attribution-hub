"""
S3-backed artifact storage for reviews, exports, model snapshots, and pipeline runs.

Uses the ECS task IAM role (IRSA) for authentication — no explicit credentials needed.
In local dev without AWS access, operations gracefully degrade to local filesystem
when PAS_S3_ARTIFACTS_BUCKET is empty or not set.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]
_LOCAL_ARTIFACTS_DIR = _REPO_ROOT / "outputs" / "artifacts"


def _get_s3_client():
    """Return an S3 client. Returns None if S3 is not configured or unreachable."""
    if not settings.s3_artifacts_bucket:
        return None
    try:
        return boto3.client("s3", region_name=settings.aws_region)
    except NoCredentialsError:
        logger.warning("s3_storage: no AWS credentials found, falling back to local storage")
        return None
    except Exception as exc:
        logger.warning("s3_storage: failed to create S3 client: %s", exc)
        return None


def _utcnow_iso() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def put_json(
    key_prefix: str,
    name: str,
    data: dict[str, Any],
    *,
    s3_client=None,
) -> str | None:
    """Upload a JSON object to S3 and return the S3 key.

    Args:
        key_prefix: S3 key prefix, e.g. ``reviews/paper-123`` or ``exports``.
        name: Logical name for the file (timestamp + .json appended automatically).
        data: JSON-serializable dictionary.
        s3_client: Optional pre-created boto3 S3 client (for reuse in batch uploads).

    Returns:
        The S3 object key on success, ``None`` on failure (logged).
    """
    client = s3_client or _get_s3_client()
    key = f"{key_prefix.rstrip('/')}/{name}_{_utcnow_iso()}.json"
    body = json.dumps(data, ensure_ascii=False, indent=2, default=str).encode("utf-8")

    if client is None:
        # Local fallback
        local_path = _LOCAL_ARTIFACTS_DIR / key
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(body)
        logger.info("s3_storage (local): wrote %s", local_path)
        return key

    try:
        client.put_object(
            Bucket=settings.s3_artifacts_bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
        )
        logger.info("s3_storage: uploaded s3://%s/%s", settings.s3_artifacts_bucket, key)
        return key
    except ClientError as exc:
        logger.error("s3_storage: failed to upload %s: %s", key, exc)
        return None


def put_file(
    key_prefix: str,
    filename: str,
    content: bytes,
    content_type: str = "application/octet-stream",
    *,
    s3_client=None,
) -> str | None:
    """Upload raw bytes to S3.

    Args:
        key_prefix: S3 key prefix.
        filename: Full filename (with extension) for the object.
        content: Raw bytes to upload.
        content_type: MIME type for the object.
        s3_client: Optional pre-created S3 client.

    Returns:
        The S3 object key on success, ``None`` on failure.
    """
    client = s3_client or _get_s3_client()
    key = f"{key_prefix.rstrip('/')}/{filename}"

    if client is None:
        local_path = _LOCAL_ARTIFACTS_DIR / key
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(content)
        logger.info("s3_storage (local): wrote %s", local_path)
        return key

    try:
        client.put_object(
            Bucket=settings.s3_artifacts_bucket,
            Key=key,
            Body=BytesIO(content),
            ContentType=content_type,
        )
        logger.info("s3_storage: uploaded s3://%s/%s", settings.s3_artifacts_bucket, key)
        return key
    except ClientError as exc:
        logger.error("s3_storage: failed to upload %s: %s", key, exc)
        return None


def put_csv(
    key_prefix: str,
    name: str,
    csv_content: str,
    *,
    s3_client=None,
) -> str | None:
    """Upload a CSV string to S3.

    Args:
        key_prefix: S3 key prefix, e.g. ``exports``.
        name: Logical name for the file (timestamp + .csv appended automatically).
        csv_content: CSV content as a string.
        s3_client: Optional pre-created S3 client.

    Returns:
        The S3 object key on success, ``None`` on failure.
    """
    client = s3_client or _get_s3_client()
    filename = f"{name}_{_utcnow_iso()}.csv"
    return put_file(
        key_prefix=key_prefix,
        filename=filename,
        content=csv_content.encode("utf-8"),
        content_type="text/csv",
        s3_client=client,
    )


# ---------------------------------------------------------------------------
# Convenience: domain-specific uploads
# ---------------------------------------------------------------------------


def save_review_artifact(paper_id: str, review_data: dict[str, Any]) -> str | None:
    """Save a review result as a JSON artifact.

    Example key: ``reviews/paper-abc123/review_20250101T120000Z.json``
    """
    return put_json(f"reviews/{paper_id}", "review", review_data)


def save_evidence_tree(paper_id: str, evidence_data: dict[str, Any]) -> str | None:
    """Save attribution evidence tree data for a paper."""
    return put_json(f"reviews/{paper_id}", "evidence_tree", evidence_data)


def save_export_csv(name: str, csv_content: str) -> str | None:
    """Save a CSV export (papers, labels, analytics report, etc.)."""
    return put_csv("exports", name, csv_content)


def save_model_snapshot(
    model_type: str,
    version: str,
    file_content: bytes,
    filename: str,
) -> str | None:
    """Save a model snapshot (classifier .joblib, embeddings .npy, metrics .json).

    Example key: ``model-snapshots/classifier/v20250101-120000/classifier.joblib``
    """
    return put_file(
        key_prefix=f"model-snapshots/{model_type}/{version}",
        filename=filename,
        content=file_content,
    )


def save_pipeline_run(run_id: str, summary_data: dict[str, Any]) -> str | None:
    """Save a daily pipeline run summary."""
    return put_json(f"pipeline-runs/{run_id}", "summary", summary_data)


def get_s3_client():
    """Return a reusable S3 client for batch operations. None if unavailable."""
    return _get_s3_client()
