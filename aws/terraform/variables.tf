# ---------------------------------------------------------------------------
# Required variables (must be set in .tfvars or via -var)
# ---------------------------------------------------------------------------

variable "environment" {
  description = "Deployment environment: dev or prod"
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be 'dev' or 'prod'."
  }
}

variable "aws_region" {
  description = "Primary AWS region for regional resources (VPC, ECS, RDS, ALB, S3)"
  type        = string
  default     = "ca-central-1"
}

# ---------------------------------------------------------------------------
# Domain & DNS
# ---------------------------------------------------------------------------

variable "route53_zone_id" {
  description = "Route53 hosted zone ID for DNS records. Leave empty to skip DNS."
  type        = string
  default     = ""
}

variable "frontend_domain" {
  description = "Frontend domain (e.g., app.example.com). Used for CloudFront alias and ACM."
  type        = string
  default     = ""
}

variable "api_domain" {
  description = "API domain (e.g., api.example.com). Used for ALB alias and ACM."
  type        = string
  default     = ""
}

# ---------------------------------------------------------------------------
# GitHub OIDC (for CI/CD)
# ---------------------------------------------------------------------------

variable "github_org" {
  description = "GitHub organization or username owning the repository"
  type        = string
  default     = ""
}

variable "github_repo" {
  description = "GitHub repository name (e.g., paper-attribution-system)"
  type        = string
  default     = "paper-attribution-system"
}

variable "github_oidc_provider_arn" {
  description = "Existing GitHub Actions OIDC provider ARN. Leave empty to create one."
  type        = string
  default     = ""
}

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.medium"
}

variable "db_allocated_storage" {
  description = "RDS allocated storage (GB)"
  type        = number
  default     = 20
}

variable "db_max_allocated_storage" {
  description = "RDS max auto-scaled storage (GB)"
  type        = number
  default     = 100
}

variable "db_username" {
  description = "RDS master username. Leave empty to auto-generate 'pas_admin' + random password."
  type        = string
  default     = ""
  sensitive   = true
}

variable "db_password" {
  description = "RDS master password. Leave empty to auto-generate a random password."
  type        = string
  default     = ""
  sensitive   = true
}

# ---------------------------------------------------------------------------
# ECS / Backend
# ---------------------------------------------------------------------------

variable "backend_desired_count" {
  description = "Number of ECS Fargate tasks to run"
  type        = number
  default     = 1
}

variable "backend_cpu" {
  description = "CPU units for the backend task (1024 = 1 vCPU)"
  type        = number
  default     = 1024
}

variable "backend_memory" {
  description = "Memory for the backend task (MiB)"
  type        = number
  default     = 2048
}

variable "image_tag" {
  description = "Docker image tag to deploy (default: latest)"
  type        = string
  default     = "latest"
}

variable "worker_cpu" {
  description = "CPU units for scheduled Fargate ETL/model-evolution tasks"
  type        = number
  default     = 2048
}

variable "worker_memory" {
  description = "Memory (MiB) for scheduled Fargate ETL/model-evolution tasks"
  type        = number
  default     = 4096
}

variable "worker_ephemeral_storage" {
  description = "Ephemeral storage (GiB) for scheduled worker artifacts"
  type        = number
  default     = 40
}

variable "worker_schedules_enabled" {
  description = "Enable EventBridge schedules for model evolution and daily ETL"
  type        = bool
  default     = true
}

variable "model_evolution_schedule" {
  description = "EventBridge schedule for draining human-review retraining batches"
  type        = string
  default     = "rate(5 minutes)"
}

variable "pipeline_schedule" {
  description = "EventBridge schedule for the incremental daily pipeline"
  type        = string
  default     = "cron(0 6 * * ? *)"
}

variable "active_retrain_every" {
  description = "Distinct eligible human reviews required for one retraining batch"
  type        = number
  default     = 20

  validation {
    condition     = var.active_retrain_every >= 2
    error_message = "active_retrain_every must be at least 2."
  }
}

variable "model_auto_promote" {
  description = "Allow a passing candidate to replace the production model"
  type        = bool
  default     = false
}

variable "pipeline_discovery" {
  description = "Allow the scheduled daily pipeline to call external discovery APIs"
  type        = bool
  default     = false
}

variable "pipeline_fulltext" {
  description = "Allow the scheduled daily pipeline to fetch and extract full text"
  type        = bool
  default     = false
}

# ---------------------------------------------------------------------------
# Application settings
# ---------------------------------------------------------------------------

variable "cors_origins" {
  description = "CORS origins as JSON array of strings"
  type        = list(string)
  default     = ["http://localhost:5173", "http://localhost:3000"]
}

variable "kimi_model" {
  description = "Kimi LLM model name"
  type        = string
  default     = "moonshot-v1-32k"
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}
