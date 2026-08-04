# ---------------------------------------------------------------------------
# S3 — Frontend hosting bucket + Artifacts storage bucket
# ---------------------------------------------------------------------------

# =============================================
# Frontend Bucket (served via CloudFront)
# =============================================

resource "aws_s3_bucket" "frontend" {
  bucket = "paper-attribution-frontend-${var.environment}"
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
  bucket = "paper-attribution-artifacts-${var.environment}"
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

  # Transition to Infrequent Access after 90 days
  rule {
    id     = "transition-to-ia"
    status = "Enabled"
    filter { prefix = "" }

    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }
  }

  # Transition to Glacier after 365 days
  rule {
    id     = "transition-to-glacier"
    status = "Enabled"
    filter { prefix = "" }

    transition {
      days          = 365
      storage_class = "GLACIER"
    }
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
