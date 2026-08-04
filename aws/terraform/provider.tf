terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

# Primary region provider — used for VPC, ECS, RDS, ALB, S3, etc.
provider "aws" {
  region = var.aws_region
  default_tags {
    tags = local.common_tags
  }
}

# us-east-1 provider — required for CloudFront ACM certificates and
# CloudFront Functions (which must be in us-east-1).
provider "aws" {
  alias  = "us-east-1"
  region = "us-east-1"
  default_tags {
    tags = local.common_tags
  }
}
