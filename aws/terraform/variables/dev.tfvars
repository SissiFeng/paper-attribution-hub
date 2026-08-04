# ---------------------------------------------------------------------------
# Development environment variables
# ---------------------------------------------------------------------------

environment = "dev"
aws_region  = "us-east-1"

# Domain — leave empty for dev (use ALB/CloudFront auto-generated DNS names)
route53_zone_id = ""
frontend_domain = ""
api_domain      = ""

# GitHub (for OIDC CI/CD)
# github_org  = ""
# github_repo = "paper-attribution-system"

# Cost-optimized database for development
db_instance_class        = "db.t3.micro"
db_allocated_storage     = 20
db_max_allocated_storage = 50

# Dev: single task, no auto-scaling needed
backend_desired_count = 1

# Log retention — shorter for dev
log_retention_days = 7

# CORS origins for dev
cors_origins = [
  "http://localhost:5173",
  "http://localhost:3000",
  "http://127.0.0.1:5173",
  "http://127.0.0.1:3000",
]
