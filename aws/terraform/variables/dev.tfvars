# ---------------------------------------------------------------------------
# Development environment variables
# ---------------------------------------------------------------------------

environment = "dev"
aws_region  = "ca-central-1"

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

# Review-driven learning is drained by a separate Fargate task. Passing
# candidates remain staged until a human explicitly promotes them.
worker_schedules_enabled = true
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
