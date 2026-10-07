#!/usr/bin/env bash
# One-command deployment for paper-attribution-system to AWS.
#
# Usage:
#   ./aws/scripts/deploy.sh [dev|prod]
#
# Prerequisites:
#   - AWS credentials with administrator access to the target account
#   - Terraform >= 1.5, Docker, Node.js 22, and npm
set -euo pipefail

ENVIRONMENT="${1:-dev}"
AWS_REGION="${AWS_REGION:-ca-central-1}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TF_DIR="$REPO_ROOT/aws/terraform"
TF_VARS="$TF_DIR/variables/${ENVIRONMENT}.tfvars"

if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
  echo "Environment must be dev or prod." >&2
  exit 1
fi

if [[ ! -f "$TF_VARS" ]]; then
  echo "Missing Terraform variables file: $TF_VARS" >&2
  exit 1
fi

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
STATE_BUCKET="${TF_STATE_BUCKET:-paper-attribution-tfstate-${ACCOUNT_ID}-${AWS_REGION}}"
LOCK_TABLE="${TF_LOCK_TABLE:-paper-attribution-terraform-locks}"
STATE_KEY="paper-attribution/${ENVIRONMENT}/terraform.tfstate"
IMAGE_TAG="${IMAGE_TAG:-$(git -C "$REPO_ROOT" rev-parse --short=12 HEAD)}"

echo "Deploying paper-attribution (${ENVIRONMENT}) to ${ACCOUNT_ID}/${AWS_REGION}"

echo "[1/8] Bootstrapping Terraform state"
if ! aws s3api head-bucket --bucket "$STATE_BUCKET" >/dev/null 2>&1; then
  if [[ "$AWS_REGION" == "us-east-1" ]]; then
    aws s3api create-bucket --bucket "$STATE_BUCKET" --region "$AWS_REGION"
  else
    aws s3api create-bucket \
      --bucket "$STATE_BUCKET" \
      --region "$AWS_REGION" \
      --create-bucket-configuration "LocationConstraint=${AWS_REGION}"
  fi
fi
aws s3api put-bucket-versioning \
  --bucket "$STATE_BUCKET" \
  --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption \
  --bucket "$STATE_BUCKET" \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-public-access-block \
  --bucket "$STATE_BUCKET" \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

if ! aws dynamodb describe-table \
  --table-name "$LOCK_TABLE" \
  --region "$AWS_REGION" >/dev/null 2>&1; then
  aws dynamodb create-table \
    --table-name "$LOCK_TABLE" \
    --region "$AWS_REGION" \
    --billing-mode PAY_PER_REQUEST \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH >/dev/null
  aws dynamodb wait table-exists --table-name "$LOCK_TABLE" --region "$AWS_REGION"
fi

echo "[2/8] Initializing Terraform"
terraform -chdir="$TF_DIR" init -upgrade -reconfigure \
  -backend-config="bucket=${STATE_BUCKET}" \
  -backend-config="key=${STATE_KEY}" \
  -backend-config="region=${AWS_REGION}" \
  -backend-config="dynamodb_table=${LOCK_TABLE}" \
  -backend-config="encrypt=true"

echo "[3/8] Creating the ECR repository"
terraform -chdir="$TF_DIR" apply \
  -var-file="$TF_VARS" \
  -var="aws_region=${AWS_REGION}" \
  -target=aws_ecr_repository.backend \
  -target=aws_ecr_lifecycle_policy.backend \
  -auto-approve

ECR_REPO="$(terraform -chdir="$TF_DIR" output -raw ecr_repository_url)"

echo "[4/8] Building and pushing the first backend image"
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "${ECR_REPO%%/*}"
docker build \
  --platform linux/amd64 \
  --file "$REPO_ROOT/backend/Dockerfile" \
  --tag "${ECR_REPO}:${IMAGE_TAG}" \
  --tag "${ECR_REPO}:latest" \
  "$REPO_ROOT"
docker push "${ECR_REPO}:${IMAGE_TAG}"
docker push "${ECR_REPO}:latest"

echo "[5/8] Planning infrastructure"
terraform -chdir="$TF_DIR" plan \
  -var-file="$TF_VARS" \
  -var="aws_region=${AWS_REGION}" \
  -var="image_tag=${IMAGE_TAG}" \
  -out=tfplan

echo "[6/8] Applying infrastructure"
terraform -chdir="$TF_DIR" apply tfplan

ECS_CLUSTER="$(terraform -chdir="$TF_DIR" output -raw ecs_cluster_name)"
ECS_SERVICE="$(terraform -chdir="$TF_DIR" output -raw ecs_service_name)"
FRONTEND_BUCKET="$(terraform -chdir="$TF_DIR" output -raw frontend_bucket_name)"
CF_DIST_ID="$(terraform -chdir="$TF_DIR" output -raw cloudfront_distribution_id)"
API_URL="$(terraform -chdir="$TF_DIR" output -raw api_endpoint)"
FRONTEND_URL="$(terraform -chdir="$TF_DIR" output -raw frontend_url)"

echo "[7/8] Building and uploading the frontend"
(
  cd "$REPO_ROOT/frontend"
  VITE_API_BASE="/api" VITE_USE_MOCK=false npm ci
  VITE_API_BASE="/api" VITE_USE_MOCK=false npm run build
  npm run build:reading
)
bash "$REPO_ROOT/aws/scripts/publish_frontend.sh" \
  "$REPO_ROOT/frontend/dist" "$REPO_ROOT/frontend/dist-reading" "$FRONTEND_BUCKET"
aws cloudfront create-invalidation \
  --distribution-id "$CF_DIST_ID" \
  --paths "/*" >/dev/null

echo "[8/8] Waiting for the backend and checking health"
aws ecs wait services-stable \
  --cluster "$ECS_CLUSTER" \
  --services "$ECS_SERVICE" \
  --region "$AWS_REGION"
curl --fail --retry 12 --retry-delay 10 "${API_URL}/health" >/dev/null

echo "Deployment complete"
echo "Frontend: ${FRONTEND_URL}"
echo "API:      ${API_URL}"
echo "Project:  paper-attribution"
echo "Env:      ${ENVIRONMENT}"
