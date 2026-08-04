#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# deploy.sh — One-command deployment for paper-attribution-system to AWS.
#
# Usage:
#   ./aws/scripts/deploy.sh [dev|prod]
#
# Prerequisites:
#   1. Terraform state bucket + DynamoDB lock table created (see docs/aws-console-setup.md)
#   2. AWS credentials configured (AWS_PROFILE or default credentials)
#   3. Terraform >= 1.5 installed
# ---------------------------------------------------------------------------
set -euo pipefail

ENV="${1:-dev}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TF_DIR="$REPO_ROOT/aws/terraform"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}==> Deploying paper-attribution-system to AWS (${ENV})${NC}"

# --- Step 1: Terraform Init ---
echo -e "${YELLOW}[1/5] Initializing Terraform...${NC}"
cd "$TF_DIR"
terraform init -upgrade

# --- Step 2: Terraform Plan ---
echo -e "${YELLOW}[2/5] Planning infrastructure changes...${NC}"
terraform plan \
  -var-file="variables/${ENV}.tfvars" \
  -out=tfplan

# --- Step 3: Terraform Apply ---
echo -e "${YELLOW}[3/5] Applying infrastructure...${NC}"
terraform apply tfplan

# --- Step 4: Capture outputs ---
echo -e "${YELLOW}[4/5] Capturing deployment outputs...${NC}"
ECR_REPO=$(terraform output -raw ecr_repository_url)
ECS_CLUSTER=$(terraform output -raw ecs_cluster_name)
ECS_SERVICE=$(terraform output -raw ecs_service_name)
FRONTEND_BUCKET=$(terraform output -raw frontend_bucket_name)
CF_DIST_ID=$(terraform output -raw cloudfront_distribution_id)
API_URL=$(terraform output -raw api_endpoint)

echo ""
echo -e "${GREEN}===== Deployment Summary =====${NC}"
echo "ECR Repository:       $ECR_REPO"
echo "ECS Cluster:          $ECS_CLUSTER"
echo "ECS Service:          $ECS_SERVICE"
echo "Frontend S3 Bucket:   $FRONTEND_BUCKET"
echo "CloudFront Dist ID:   $CF_DIST_ID"
echo "API Endpoint:         $API_URL"
echo ""

# --- Step 5: Manual steps reminder ---
echo -e "${YELLOW}[5/5] Next steps (manual):${NC}"
echo ""
echo "  1. Set API keys in SSM Parameter Store:"
echo "     aws ssm put-parameter --name \"/paper-attribution-${ENV}/anthropic-api-key\" --type SecureString --value \"sk-...\" --overwrite"
echo "     aws ssm put-parameter --name \"/paper-attribution-${ENV}/kimi-api-key\" --type SecureString --value \"sk-...\" --overwrite"
echo "     aws ssm put-parameter --name \"/paper-attribution-${ENV}/semantic-scholar-api-key\" --type SecureString --value \"...\" --overwrite"
echo "     aws ssm put-parameter --name \"/paper-attribution-${ENV}/openalex-mailto\" --type String --value \"you@example.com\" --overwrite"
echo ""
echo "  2. Set GitHub Actions secrets:"
echo "     - AWS_DEPLOY_ROLE_ARN       = $(terraform output -raw github_actions_role_arn 2>/dev/null || echo '<from Terraform outputs>')"
echo "     - AWS_REGION                = us-east-1"
echo "     - ECR_REPO_URL              = $ECR_REPO"
echo "     - ECS_CLUSTER_NAME          = $ECS_CLUSTER"
echo "     - ECS_SERVICE_NAME          = $ECS_SERVICE"
echo "     - FRONTEND_S3_BUCKET        = $FRONTEND_BUCKET"
echo "     - CLOUDFRONT_DISTRIBUTION_ID = $CF_DIST_ID"
echo "     - VITE_API_BASE             = $API_URL"
echo ""
echo "  3. Push to main branch to trigger CI/CD, or manually build and push the first Docker image:"
echo "     aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR_REPO"
echo "     docker build -t $ECR_REPO:latest -f backend/Dockerfile ."
echo "     docker push $ECR_REPO:latest"
echo ""
echo -e "${GREEN}Done!${NC}"
