# ---------------------------------------------------------------------------
# Locals and data sources shared across all resources.
# ---------------------------------------------------------------------------

locals {
  name_prefix = "paper-attribution-${var.environment}"

  common_tags = {
    Project     = "paper-attribution"
    Environment = var.environment
    ManagedBy   = "terraform"
  }

  # Convenience: full postgresql connection URL for the ECS container.
  db_connection_url = "postgresql://${var.db_username != "" ? var.db_username : "pas_admin"}:${urlencode(random_password.db.result)}@${aws_db_instance.main.address}:5432/${aws_db_instance.main.db_name}"
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Look up the Route53 hosted zone by ID so we can create alias records.
data "aws_route53_zone" "main" {
  count   = var.route53_zone_id != "" ? 1 : 0
  zone_id = var.route53_zone_id
}
