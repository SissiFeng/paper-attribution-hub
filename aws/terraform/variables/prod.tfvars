# ---------------------------------------------------------------------------
# Production environment variables
# Set your actual values BEFORE running `terraform apply`.
# ---------------------------------------------------------------------------

environment = "prod"
aws_region  = "ca-central-1"

# Domain — set your actual domain and Route53 zone ID here
route53_zone_id = "" # <-- SET THIS (find in Route53 console)
frontend_domain = "" # <-- SET THIS (e.g., app.example.com)
api_domain      = "" # <-- SET THIS (e.g., api.example.com)

# GitHub (for OIDC CI/CD — set your GitHub org/username)
github_org  = "SissiFeng"
github_repo = "paper-attribution-hub"

# Production database sizing
db_instance_class        = "db.t3.medium"
db_allocated_storage     = 20
db_max_allocated_storage = 100

# Production: at least 2 tasks for high availability
backend_desired_count = 2

worker_schedules_enabled = true
active_retrain_every     = 20
model_auto_promote       = false
pipeline_discovery       = false
pipeline_fulltext        = false

# Log retention
log_retention_days = 30

# CORS origins — add your frontend domain after deployment
cors_origins = [
  "http://localhost:5173",
  "http://localhost:3000",
  # "https://app.example.com",
]

# Authoritative Zotero collection keys (set before deployment).
zotero_group_id                          = "6631056"
zotero_tier1_collection                  = "ZYENR62J"
zotero_tier2_collection                  = ""
sdl_stage1_only                          = true
sdl_stage1_derived_views_enabled         = false
sdl_stage1_descriptive_analytics_enabled = false
