# AWS Console Setup Guide

This guide covers the manual AWS console steps that remain around the automated
deployment. The deploy script bootstraps Terraform state, builds both
applications, and verifies health.

## Prerequisites

- An AWS account with billing set up and an AdministratorAccess SSO role
- A domain name (optional — you can use the auto-generated AWS URLs instead)
- Your API keys ready:
  - Anthropic API key (`sk-ant-...`)
  - Kimi (MoonShot AI) API key (`sk-...`)
  - Semantic Scholar API key

---

## Step 1: Authenticate with AWS IAM Identity Center

Use an AdministratorAccess role in the target account and region:

```bash
aws sso login --profile paper-attribution
export AWS_PROFILE=paper-attribution
export AWS_REGION=ca-central-1
aws sts get-caller-identity
```

The deploy script creates an account-scoped, encrypted Terraform state bucket
and an on-demand DynamoDB lock table. Long-lived IAM access keys are not
required.

---

## Step 2: Register a Domain (Optional)

If you don't have a domain, you can use the auto-generated AWS endpoints:
- Application: `https://<cloudfront-dns-name>`
- API: `https://<cloudfront-dns-name>/api`

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

## Step 3: Request ACM Certificates (SSL)

### Certificate for CloudFront (must be in us-east-1)
1. Go to **ACM → Request certificate** (ensure region is **N. Virginia / us-east-1**)
2. Domain name: `*.example.com` (wildcard) or `app.example.com`
3. Validation method: **DNS validation**
4. Request
5. **If your domain is in Route53**: click "Create records in Route53"
6. **If your domain is elsewhere**: copy the CNAME record and add it to your DNS provider

### Certificate for ALB (in your primary region)
1. Switch region to your primary region (for SDL0, `ca-central-1`)
2. Repeat the same steps as above
3. Use `*.example.com` or `api.example.com`

The certificates are referenced in `acm.tf` and the validation records will be created by Terraform if your Route53 zone is configured.

---

## Step 4: Store API Keys in SSM Parameter Store

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

## Step 5: Configure GitHub Actions Secrets

Go to your GitHub repository → **Settings → Secrets and variables → Actions** and add these secrets:

| Secret Name | Value | Where to Find |
|---|---|---|
| `AWS_DEPLOY_ROLE_ARN` | Role ARN | `terraform output github_actions_role_arn` |
| `AWS_REGION` | `ca-central-1` | Your primary region |
| `ECR_REPO_URL` | ECR repo URL | `terraform output ecr_repository_url` |
| `ECS_CLUSTER_NAME` | Cluster name | `terraform output ecs_cluster_name` |
| `ECS_SERVICE_NAME` | Service name | `terraform output ecs_service_name` |
| `FRONTEND_S3_BUCKET` | S3 bucket name | `terraform output frontend_bucket_name` |
| `CLOUDFRONT_DISTRIBUTION_ID` | Distribution ID | `terraform output cloudfront_distribution_id` |
| `VITE_API_BASE` | API URL | `terraform output api_endpoint` |

---

## Step 6: Deploy and Verify

```bash
./aws/scripts/deploy.sh dev
```

1. Check ECS service: `aws ecs describe-services --cluster <cluster> --services <service>`
2. Check API health: `curl "$(terraform -chdir=aws/terraform output -raw api_endpoint)/health"`
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
