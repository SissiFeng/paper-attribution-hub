# ---------------------------------------------------------------------------
# SSM Parameter Store — API keys and non-rotated config (SecureString)
# Values must be set manually in the AWS Console after `terraform apply`.
# ---------------------------------------------------------------------------

resource "aws_ssm_parameter" "anthropic_api_key" {
  name        = "/${local.name_prefix}/anthropic-api-key"
  description = "Anthropic API key for Claude LLM calls"
  type        = "SecureString"
  value       = "PLACEHOLDER" # Set manually in AWS Console

  lifecycle {
    ignore_changes = [value]
  }

  tags = local.common_tags
}

resource "aws_ssm_parameter" "kimi_api_key" {
  name        = "/${local.name_prefix}/kimi-api-key"
  description = "Kimi (MoonShot AI) API key"
  type        = "SecureString"
  value       = "PLACEHOLDER" # Set manually in AWS Console

  lifecycle {
    ignore_changes = [value]
  }

  tags = local.common_tags
}

resource "aws_ssm_parameter" "semantic_scholar_api_key" {
  name        = "/${local.name_prefix}/semantic-scholar-api-key"
  description = "Semantic Scholar API key"
  type        = "SecureString"
  value       = "PLACEHOLDER" # Set manually in AWS Console

  lifecycle {
    ignore_changes = [value]
  }

  tags = local.common_tags
}

resource "aws_ssm_parameter" "openalex_mailto" {
  name        = "/${local.name_prefix}/openalex-mailto"
  description = "OpenAlex polite-pool email"
  type        = "String"
  value       = "changeme@example.com"

  tags = local.common_tags
}
