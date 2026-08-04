# ---------------------------------------------------------------------------
# Outputs — values needed for CI/CD and manual configuration
# ---------------------------------------------------------------------------

output "api_endpoint" {
  description = "Same-origin API base URL through CloudFront"
  value       = "${var.frontend_domain != "" ? "https://${var.frontend_domain}" : "https://${aws_cloudfront_distribution.frontend.domain_name}"}/api"
}

output "frontend_url" {
  description = "Frontend URL (CloudFront or custom domain)"
  value       = var.frontend_domain != "" ? "https://${var.frontend_domain}" : "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

output "rds_endpoint" {
  description = "RDS instance endpoint (hostname)"
  value       = aws_db_instance.main.address
}

output "rds_port" {
  description = "RDS instance port"
  value       = aws_db_instance.main.port
}

output "ecr_repository_url" {
  description = "ECR repository URL for pushing Docker images"
  value       = aws_ecr_repository.backend.repository_url
}

output "ecs_cluster_name" {
  description = "ECS cluster name (for CI/CD)"
  value       = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  description = "ECS service name (for CI/CD)"
  value       = aws_ecs_service.backend.name
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID (for cache invalidation)"
  value       = aws_cloudfront_distribution.frontend.id
}

output "frontend_bucket_name" {
  description = "S3 bucket name for frontend deployment"
  value       = aws_s3_bucket.frontend.id
}

output "artifacts_bucket_name" {
  description = "S3 bucket name for artifacts storage"
  value       = aws_s3_bucket.artifacts.id
}

output "alb_dns_name" {
  description = "ALB DNS name (use if no custom API domain configured)"
  value       = aws_lb.main.dns_name
}

output "github_actions_role_arn" {
  description = "ARN of the IAM role for GitHub Actions (for OIDC setup)"
  value       = var.github_org != "" ? aws_iam_role.github_actions[0].arn : null
}

output "ssm_parameter_prefix" {
  description = "SSM parameter path prefix for API keys"
  value       = "/${local.name_prefix}"
}
