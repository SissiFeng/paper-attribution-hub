# S3 backend for Terraform state. The bucket and DynamoDB table must be
# created manually before running `terraform init` (see docs/aws-console-setup.md).
terraform {
  backend "s3" {
    bucket         = "paper-attribution-tfstate"
    key            = "terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}
