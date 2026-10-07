# ---------------------------------------------------------------------------
# Development environment variables
# ---------------------------------------------------------------------------

environment = "dev"
aws_region  = "ca-central-1"
image_tag   = "zotero-sdl-stage1-20260807-r26"

# Domain — leave empty for dev (use ALB/CloudFront auto-generated DNS names)
route53_zone_id = ""
frontend_domain = ""
api_domain      = ""

# GitHub (for OIDC CI/CD)
github_org               = "SissiFeng"
github_repo              = "paper-attribution-hub"
github_oidc_provider_arn = "arn:aws:iam::247893369214:oidc-provider/token.actions.githubusercontent.com"

# Cost-optimized database for development
db_instance_class        = "db.t3.micro"
db_allocated_storage     = 20
db_max_allocated_storage = 50

# Dev: single task, no auto-scaling needed
backend_desired_count = 1

# Acquisition phase: keep classification/retraining schedules paused until
# the Tier 1 Markdown corpus passes coverage and quality gates.
worker_schedules_enabled = false
active_retrain_every     = 20
model_auto_promote       = false
pipeline_discovery       = false
pipeline_fulltext        = false

# Log retention — shorter for dev
log_retention_days = 7

# CORS origins for dev
cors_origins = [
  "http://localhost:5173",
  "http://localhost:3000",
  "http://127.0.0.1:5173",
  "http://127.0.0.1:3000",
]

# Authoritative Zotero collection keys (set before deployment).
zotero_group_id                          = "6631056"
zotero_tier1_collection                  = "ZYENR62J"
zotero_tier2_collection                  = ""
sdl_stage1_only                          = false
sdl_stage1_derived_views_enabled         = true
sdl_stage1_descriptive_analytics_enabled = true

zotero_source_only = false
# Keep current inference/retraining policy while opening metadata ingestion.
active_learning_enabled    = false
learned_classifier_enabled = false

pas_public_url = "https://d1ai8ldqsh81fz.cloudfront.net"
pas_slack_team_id = "T012M3T3U01"
pas_slack_app_id = "A0C6VPXEQ5C"
pas_slack_table = "paper-attribution-dev-slack"
