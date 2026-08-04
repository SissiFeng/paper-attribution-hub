# ---------------------------------------------------------------------------
# ACM Certificates — one in us-east-1 (CloudFront), one in the primary region (ALB)
# ---------------------------------------------------------------------------

# Certificate for CloudFront (MUST be in us-east-1)
resource "aws_acm_certificate" "frontend" {
  count = var.frontend_domain != "" ? 1 : 0

  provider          = aws.us-east-1
  domain_name       = var.frontend_domain
  validation_method = "DNS"

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-cf-cert" })

  lifecycle {
    create_before_destroy = true
  }
}

# Certificate for the ALB (in the primary region)
resource "aws_acm_certificate" "api" {
  count = var.api_domain != "" ? 1 : 0

  domain_name       = var.api_domain
  validation_method = "DNS"

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-api-cert" })

  lifecycle {
    create_before_destroy = true
  }
}

# NOTE: DNS validation records must be created manually in Route53 (or via
# the aws_route53_record resource). The user will see the validation CNAME
# values in the AWS console after `terraform apply` starts.
# To automate: use aws_acm_certificate_validation with the Route53 zone data.
