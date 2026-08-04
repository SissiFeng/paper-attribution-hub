# AWS Deployment Guide

This document describes the full AWS deployment architecture and operational procedures for the Paper Attribution System.

## Architecture

```
Internet
    │
    └── app.example.com → Route53 → ACM → CloudFront
                                      ├── S3 (static React SPA)
                                      └── /api/* → ALB → ECS Fargate → RDS PostgreSQL + pgvector

EventBridge
    ├── every 5 min → short-lived Fargate model worker → RDS + model registry
    └── daily 06:00 UTC → short-lived Fargate ETL worker → RDS + review queue

Side services:
    S3 (review artifacts, model snapshots, exports)
    SSM Parameter Store (API keys)
    Secrets Manager (database credentials)
    ECR (Docker images)
    CloudWatch (API/worker logs, metrics, alarms)
    SQS (worker invocation and non-zero-exit failure queue)
```

## File Structure

```
aws/
├── terraform/           # Infrastructure as Code
│   ├── provider.tf      # AWS providers
│   ├── backend.tf       # S3 state + DynamoDB lock
│   ├── main.tf          # Locals, data sources
│   ├── variables.tf     # Input variables
│   ├── outputs.tf       # Deployment output values
│   ├── vpc.tf           # VPC, subnets, NAT, endpoints
│   ├── security_groups.tf
│   ├── ecs.tf           # Fargate cluster, service, task
│   ├── workers.tf       # EventBridge, short-lived worker task, failure queue
│   ├── alb.tf           # Load balancer, target group
│   ├── ecr.tf           # Docker registry
│   ├── rds.tf           # PostgreSQL 16 + pgvector
│   ├── s3.tf            # Frontend + artifacts buckets
│   ├── cloudfront.tf    # CDN + SPA routing function
│   ├── route53.tf       # DNS records
│   ├── acm.tf           # SSL certificates
│   ├── iam.tf           # Roles (ECS, GitHub OIDC)
│   ├── secrets.tf       # SSM Parameter Store
│   ├── cloudwatch.tf    # Logs + alarms
│   └── variables/
│       ├── dev.tfvars
│       └── prod.tfvars
└── scripts/
    └── deploy.sh             # One-command deploy
```

## Quick Start

### Prerequisites

1. AWS account with an AdministratorAccess SSO role
2. Terraform >= 1.5 installed
3. Docker installed (for image builds)
4. Domain name (optional — use auto-generated AWS URLs instead)

### One-Time Setup

Follow [aws-console-setup.md](./aws-console-setup.md) for SSO and optional
domain setup, then use the deployment script:
```bash
./aws/scripts/deploy.sh dev
```

### CI/CD

On every push to `main`, GitHub Actions:
1. Builds and pushes the backend Docker image to ECR
2. Deploys to ECS (rolling update with health check)
3. Builds the frontend with production `VITE_API_BASE`
4. Syncs `dist/` to S3
5. Invalidates CloudFront cache

Authentication uses OIDC — no AWS access keys stored in GitHub.

## Environment Variables

### SSM Parameter Store (set manually once)

| Parameter | Type | Description |
|---|---|---|
| `/paper-attribution-{env}/anthropic-api-key` | SecureString | Anthropic Claude API key |
| `/paper-attribution-{env}/kimi-api-key` | SecureString | Kimi (MoonShot) API key |
| `/paper-attribution-{env}/semantic-scholar-api-key` | SecureString | Semantic Scholar API key |
| `/paper-attribution-{env}/openalex-mailto` | String | OpenAlex polite email |

### ECS Container Environment (auto-set by Terraform)

| Variable | Source |
|---|---|
| `PAS_DATABASE_URL` | Constructed from RDS endpoint + Secrets Manager |
| `PAS_CORS_ORIGINS` | From `var.cors_origins` tfvars |
| `PAS_S3_ARTIFACTS_BUCKET` | S3 bucket name |
| `PAS_AWS_REGION` | Primary region |
| `PAS_KIMI_MODEL` | From `var.kimi_model` tfvars |
| `PAS_ACTIVE_RETRAIN_EVERY` | Review batch size (20 by default) |
| `PAS_MODEL_AUTO_PROMOTE` | `false` by default; passing candidates stay staged |
| `PAS_BUILD_REVISION` | Immutable image tag used for audit lineage |

## Scheduled data and model workers

The API service is kept responsive and does not train models inside a web
request. Every five minutes EventBridge starts a short-lived Fargate task that
reconciles durable review feedback and trains only complete 20-paper batches.
At 06:00 UTC another task incrementally classifies unscored/stale papers and
refreshes staged screening. Both tasks use the same repository and image; ETL
is not split into a second repository.

The worker is sized at 2 vCPU, 4 GiB RAM, and 40 GiB ephemeral storage. This
corpus is currently a bounded, intermittent job, so Fargate is simpler and
cheaper operationally than maintaining EC2 instances. If measured training
duration or memory later exceeds this profile, the same container can move to
AWS Batch on EC2 Spot; that is a capacity change, not a reason to weaken model
validation or automatic-promotion controls.

EventBridge delivery failures, tasks that fail to start, and non-zero container
exits are routed to the worker failure SQS queue. A CloudWatch alarm fires when
the queue becomes non-empty. Model-training concurrency is additionally guarded
by the database lease in `model_training_state`.

## S3 Artifact Storage

### Bucket Structure

```
s3://paper-attribution-artifacts-{env}-{account_id}/
├── reviews/{paper_id}/
│   ├── review_{timestamp}.json
│   └── evidence_tree_{timestamp}.json
├── exports/
│   ├── papers_{timestamp}.csv
│   └── labels_{timestamp}.csv
├── model-snapshots/
│   ├── classifier/v{timestamp}/
│   │   └── classifier.joblib
│   └── embeddings/v{timestamp}/
│       └── embeddings.npy
├── pipeline-runs/{run_id}/
│   └── summary.json
└── logs/daily-pipeline/YYYY/MM/DD/
    └── run.log
```

### Lifecycle Policies

- **90 days**: Standard → Infrequent Access (lower storage cost)
- **365 days**: Infrequent Access → Glacier (archive)
- **2 years**: Auto-delete model snapshots
- **6 months**: Auto-delete pipeline runs
- **90 days**: Auto-delete logs

### Backend Integration

```python
from app.services.s3_storage import save_review_artifact, save_export_csv

# Save a review
save_review_artifact("paper-abc123", {
    "label": "ATTRIBUTED",
    "confidence": 0.92,
    "reviewer": "alice",
})

# Save an export
save_export_csv("papers", csv_content_string)
```

In local dev without AWS, files fall back to `outputs/artifacts/` on disk.

## Operational Tasks

### Deploy a Code Change

```bash
# Push to main — CI/CD handles the rest automatically
git push origin main
```

### Scale Backend

Edit `aws/terraform/variables/prod.tfvars` and change `backend_desired_count`, then:

```bash
cd aws/terraform
terraform plan -var-file="variables/prod.tfvars"
terraform apply
```

### View Logs

```bash
# CloudWatch Logs
aws logs tail /ecs/paper-attribution-prod-backend --follow
aws logs tail /ecs/paper-attribution-prod-worker --follow

# Or via AWS Console: CloudWatch → Log groups → /ecs/paper-attribution-prod-backend
```

### Database Access (via SSM Session Manager)

```bash
# Start a port-forwarding session
aws ssm start-session \
  --target <ecs-task-id> \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["<rds-endpoint>"],"portNumber":["5432"],"localPortNumber":["5433"]}'

# Then connect locally
psql -h localhost -p 5433 -U pas_admin -d paper_attribution
```

### Backup and Restore

```bash
# Export from RDS
pg_dump -h <rds-endpoint> -U pas_admin -d paper_attribution -Fc -f backup.dump

# Import to local
pg_restore -h localhost -U pas -d paper_attribution backup.dump
```

### Infrastructure Changes

```bash
cd aws/terraform
terraform plan -var-file="variables/prod.tfvars" -out=tfplan
terraform apply tfplan
```

## Cost Management

### Monthly Cost Estimates

| Service | Dev (~$175/mo) | Prod (~$700/mo) |
|---|---|---|
| RDS | $15 (t3.micro) | $55 (t3.medium) |
| ECS Fargate | $52 (1 task) | $104 (2 tasks) |
| ALB | $20 | $25 |
| NAT Gateway | $35 | $35 |
| CloudFront | $2 | $10 |
| S3 | $5 | $20 |
| Other | $46 | $451 |
| **Total** | **~$175** | **~$700** |

### Saving Costs

- Use `db.t3.micro` for dev (works for <100 concurrent users)
- Shut down dev ECS service outside working hours
- Use single NAT Gateway for dev
- Set CloudFront price class to `PriceClass_100` (US/Canada/Europe only)

## Backup Plan (Render + Vercel)

The existing Render + Vercel deployment is preserved as a fallback. The files are not touched:
- `render.yaml` (Render backend)
- `frontend/vercel.json` (Vercel frontend)

To switch back:
1. Point DNS to Render/Vercel endpoints
2. Dump RDS data and restore to Render's PostgreSQL
