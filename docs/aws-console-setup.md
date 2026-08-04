# AWS Console Setup Guide

This guide covers the manual AWS console steps needed **before** running `terraform apply`. These steps cannot be automated (account creation, domain registration, etc.) or should be done manually for security (API keys).

## Prerequisites

- An AWS account with billing set up
- A domain name (optional — you can use the auto-generated AWS URLs instead)
- Your API keys ready:
  - Anthropic API key (`sk-ant-...`)
  - Kimi (MoonShot AI) API key (`sk-...`)
  - Semantic Scholar API key

---

## Step 1: Create IAM Admin User

1. Go to **IAM → Users → Create user**
2. Username: `terraform-admin`
3. Check **Provide user access to the AWS Management Console** (optional)
4. Attach policy: **AdministratorAccess**
5. Create the user
6. Under **Security credentials**, create an **Access Key**
   - Use case: **Command Line Interface (CLI)**
   - Save the **Access Key ID** and **Secret Access Key** securely
7. Configure locally:
   ```bash
   aws configure --profile paper-attribution
   # Enter Access Key ID and Secret Access Key
   # Default region: us-east-1
   ```

---

## Step 2: Create S3 Bucket for Terraform State

1. Go to **S3 → Create bucket**
2. Bucket name: `paper-attribution-tfstate`
   - If the name is taken, use `paper-attribution-tfstate-<random-suffix>`
   - Update `aws/terraform/backend.tf` with the new bucket name
3. Region: `us-east-1`
4. **Enable bucket versioning**
5. **Enable server-side encryption** (SSE-S3)
6. **Block all public access** (checked by default)
7. Create the bucket

---

## Step 3: Create DynamoDB Table for Terraform Lock

1. Go to **DynamoDB → Create table**
2. Table name: `terraform-locks`
3. Partition key: `LockID` (type: **String**)
4. Default settings (on-demand capacity mode)
5. Create the table

---

## Step 4: Register a Domain (Optional)

If you don't have a domain, you can use the auto-generated AWS endpoints:
- API: `https://<alb-dns-name>` (printed by `terraform output alb_dns_name`)
- Frontend: `https://<cloudfront-dns-name>` (printed by `terraform output frontend_url`)

If you want a custom domain:

### Option A: Register a new domain via Route53
1. Go to **Route53 → Registered domains → Register domains**
2. Search for and purchase your domain (e.g., `example.com`)
3. A hosted zone is created automatically

### Option B: Use an existing domain from another registrar
1. Go to **Route53 → Hosted zones → Create hosted zone**
2. Domain name: `example.com`
3. Type: **Public hosted zone**
4. Create
5. Copy the **4 NS records** from the hosted zone
6. Go to your domain registrar and update the nameservers to these 4 values

### Get the Hosted Zone ID
1. Go to **Route53 → Hosted zones**
2. Click your zone
3. Copy the **Hosted zone ID** (starts with `Z`...)
4. Set this in `aws/terraform/variables/prod.tfvars`:
   ```hcl
   route53_zone_id = "ZXXXXXXXXXXXXX"
   frontend_domain = "app.example.com"
   api_domain      = "api.example.com"
   ```

---

## Step 5: Request ACM Certificates (SSL)

### Certificate for CloudFront (must be in us-east-1)
1. Go to **ACM → Request certificate** (ensure region is **N. Virginia / us-east-1**)
2. Domain name: `*.example.com` (wildcard) or `app.example.com`
3. Validation method: **DNS validation**
4. Request
5. **If your domain is in Route53**: click "Create records in Route53"
6. **If your domain is elsewhere**: copy the CNAME record and add it to your DNS provider

### Certificate for ALB (in your primary region)
1. Switch region to your primary region (e.g., us-east-1)
2. Repeat the same steps as above
3. Use `*.example.com` or `api.example.com`

The certificates are referenced in `acm.tf` and the validation records will be created by Terraform if your Route53 zone is configured.

---

## Step 6: Store API Keys in SSM Parameter Store

After `terraform apply` completes, set your API keys:

```bash
# Get the prefix from Terraform output
PREFIX=$(terraform -chdir=aws/terraform output -raw ssm_parameter_prefix)

# Set each API key
aws ssm put-parameter \
  --name "${PREFIX}/anthropic-api-key" \
  --type SecureString \
  --value "sk-ant-api03-..." \
  --overwrite

aws ssm put-parameter \
  --name "${PREFIX}/kimi-api-key" \
  --type SecureString \
  --value "sk-..." \
  --overwrite

aws ssm put-parameter \
  --name "${PREFIX}/semantic-scholar-api-key" \
  --type SecureString \
  --value "..." \
  --overwrite

aws ssm put-parameter \
  --name "${PREFIX}/openalex-mailto" \
  --type String \
  --value "you@example.com" \
  --overwrite
```

---

## Step 7: Configure GitHub Actions Secrets

Go to your GitHub repository → **Settings → Secrets and variables → Actions** and add these secrets:

| Secret Name | Value | Where to Find |
|---|---|---|
| `AWS_DEPLOY_ROLE_ARN` | Role ARN | `terraform output github_actions_role_arn` |
| `AWS_REGION` | `us-east-1` | Your primary region |
| `ECR_REPO_URL` | ECR repo URL | `terraform output ecr_repository_url` |
| `ECS_CLUSTER_NAME` | Cluster name | `terraform output ecs_cluster_name` |
| `ECS_SERVICE_NAME` | Service name | `terraform output ecs_service_name` |
| `FRONTEND_S3_BUCKET` | S3 bucket name | `terraform output frontend_bucket_name` |
| `CLOUDFRONT_DISTRIBUTION_ID` | Distribution ID | `terraform output cloudfront_distribution_id` |
| `VITE_API_BASE` | API URL | `terraform output api_endpoint` |

---

## Step 8: Initial Docker Image Push

Push the first Docker image to ECR so ECS has something to run:

```bash
# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin <ecr_repo_url>

# Build and push
docker build -t <ecr_repo_url>:latest -f backend/Dockerfile .
docker push <ecr_repo_url>:latest
```

Replace `<ecr_repo_url>` with the output from `terraform output ecr_repository_url`.

---

## Step 9: Verify Deployment

1. Check ECS service: `aws ecs describe-services --cluster <cluster> --services <service>`
2. Check the ALB health: `curl https://<api_domain>/health`
3. Open the frontend in your browser: `https://<frontend_domain>`

---

## Summary

After completing these steps, your infrastructure is fully deployed. Every push to `main` will automatically:
1. Build and push the backend Docker image
2. Deploy to ECS (rolling update, zero downtime)
3. Build the frontend and sync to S3
4. Invalidate CloudFront cache

For infrastructure changes (adding new AWS services, changing instance sizes, etc.), edit the Terraform files and run:
```bash
cd aws/terraform
terraform plan -var-file="variables/prod.tfvars"
terraform apply
```
