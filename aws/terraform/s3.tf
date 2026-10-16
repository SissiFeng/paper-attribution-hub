# ---------------------------------------------------------------------------
# S3 — Frontend hosting bucket + Artifacts storage bucket
# ---------------------------------------------------------------------------

# =============================================
# Frontend Bucket (served via CloudFront)
# =============================================

resource "aws_s3_bucket" "frontend" {
  bucket = "paper-attribution-frontend-${var.environment}-${data.aws_caller_identity.current.account_id}"
  tags   = merge(local.common_tags, { Name = "${local.name_prefix}-frontend" })
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  versioning_configuration {
    status = "Enabled"
  }
}

# CloudFront access is granted via OAC, so no S3 bucket policy needed
# that grants public read — the OAC handles it.

# =============================================
# Artifacts Bucket (review data, exports, models)
# =============================================

resource "aws_s3_bucket" "artifacts" {
  bucket = "paper-attribution-artifacts-${var.environment}-${data.aws_caller_identity.current.account_id}"
  tags   = merge(local.common_tags, { Name = "${local.name_prefix}-artifacts" })
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# --- Lifecycle Policies for Artifacts ---

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  # Explicit data prefixes keep monitor release bundles and live state online.
  dynamic "rule" {
    for_each = toset(["database-backups/", "etl-runs/", "manifests/", "raw/",
                     "workspace-backups/", "model-snapshots/", "pipeline-runs/", "logs/"])
    content {
      id     = "archive-${trimsuffix(rule.value, "/")}"
      status = "Enabled"
      filter { prefix = rule.value }
      transition {
        days          = 90
        storage_class = "STANDARD_IA"
      }
      transition {
        days          = 365
        storage_class = "GLACIER"
      }
    }
  }

  rule {
    id     = "monitor-verification"
    status = "Enabled"
    filter { prefix = "author-monitor/verification/" }
    expiration { days = 7 }
    noncurrent_version_expiration { noncurrent_days = 7 }
  }

  rule {
    id     = "monitor-state-versions"
    status = "Enabled"
    filter { prefix = "author-monitor/production/state.db" }
    noncurrent_version_expiration {
      noncurrent_days           = 7
      newer_noncurrent_versions = 10
    }
  }

  # Only processed raw messages older than 90 days are deleted by the worker.
  # Unprocessed/quarantined originals remain available for replay.
  rule {
    id     = "monitor-mail-versions"
    status = "Enabled"
    filter { prefix = "author-monitor/production/mail-raw/" }
    noncurrent_version_expiration { noncurrent_days = 7 }
    expiration { expired_object_delete_marker = true }
  }

  # Expire old model snapshots after 2 years
  rule {
    id     = "expire-old-model-snapshots"
    status = "Enabled"
    filter { prefix = "model-snapshots/" }

    expiration { days = 730 }
  }

  # Expire old pipeline runs after 6 months
  rule {
    id     = "expire-old-pipeline-runs"
    status = "Enabled"
    filter { prefix = "pipeline-runs/" }

    expiration { days = 180 }
  }

  # Expire old logs after 90 days
  rule {
    id     = "expire-old-logs"
    status = "Enabled"
    filter { prefix = "logs/" }

    expiration { days = 90 }
  }
}
