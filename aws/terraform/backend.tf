# S3 backend for Terraform state. Deployment supplies account- and
# environment-specific settings after bootstrapping the bucket and lock table.
terraform {
  backend "s3" {}
}
