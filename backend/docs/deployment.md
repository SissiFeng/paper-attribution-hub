# AWS Deployment Checklist

AWS is the only production deployment target. See the
[AWS deployment guide](../../docs/aws-deployment.md) for provisioning, releases,
backup and rollback. Docker Compose and GitHub Codespaces are development
environments.

## Runtime configuration

The frontend is served through S3 and CloudFront. The backend runs on ECS
Fargate behind an ALB and uses RDS PostgreSQL. Private artifacts use S3.
Production credentials belong in AWS SSM Parameter Store or Secrets Manager.

| Variable | Configuration |
|---|---|
| `PAS_DATABASE_URL` | RDS connection string supplied to the ECS task. |
| `PAS_CORS_ORIGINS` | Explicit frontend origins if cross-origin access is required; JSON arrays and comma-separated values are supported. |
| `PAS_S3_ARTIFACTS_BUCKET` / `PAS_AWS_REGION` | Artifact bucket and region for the deployment. |
| `PAS_KIMI_API_KEY` / `PAS_ANTHROPIC_API_KEY` | Optional model credentials supplied securely at runtime. |
| `VITE_API_BASE` | Build-time API base; production defaults to `/api`. |
| `VITE_USE_MOCK` | Production defaults to `false`; sample data is for development. |

Rebuild the frontend after changing any `VITE_*` setting. Keep production
credentials and data out of the development workspace.

## Verification and rollback

Before release, build the frontend and run relevant backend tests in Codespaces.
After release, check ECS service stability, CloudWatch logs, API health and actual
paper responses. A healthy process alone does not verify the data.

Keep the previous ECS task definition, ECR image tag and S3 frontend build for
rollback within AWS. Database restore is a separate operation and requires a
verified RDS snapshot or backup plus schema compatibility checks.
