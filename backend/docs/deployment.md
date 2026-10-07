# AWS Deployment Checklist

AWS is the only supported deployment target. Use the
[AWS deployment guide](../../docs/aws-deployment.md) for provisioning, releases
and rollback, and the [Codespaces guide](../../docs/cloud-development.zh.md)
for development. Local Docker Compose remains available for development.

## Runtime

CloudFront serves both frontend builds from S3 and routes `/api/*` through the
ALB to ECS Fargate. The backend uses RDS PostgreSQL; private artifacts use S3.
SSM Parameter Store and Secrets Manager supply production credentials.

| Variable | Configuration |
|---|---|
| `PAS_DATABASE_URL` | RDS PostgreSQL URL supplied to the ECS task; do not commit credentials. |
| `PAS_CORS_ORIGINS` | Explicit allowed frontend origins when cross-origin requests are needed. JSON arrays and comma-separated values are supported. |
| `PAS_S3_ARTIFACTS_BUCKET` / `PAS_AWS_REGION` | Artifact bucket and region for the target AWS environment. |
| `PAS_KIMI_API_KEY` / `PAS_ANTHROPIC_API_KEY` | Optional model credentials supplied through SSM. |
| `PAS_OPENALEX_API_KEY` / `PAS_SEMANTIC_SCHOLAR_API_KEY` | Optional external data credentials supplied through SSM. |
| `VITE_API_BASE` | Build-time frontend API base; production defaults to `/api`. |
| `VITE_USE_MOCK` | Production defaults to `false`; sample data is for development only. |

Changing a `VITE_*` setting requires rebuilding the frontend. Publish both
`frontend/dist` and `frontend/dist-reading` through
`aws/scripts/publish_frontend.sh` so the main PAS and reading pages are retained.

## Container startup

`backend/Dockerfile` starts `python -m app.scripts.serve`. This runs database
bootstrap, optionally syncs Zotero when enabled, and starts Uvicorn on
`PORT` (default `8000`). PostgreSQL schema changes are managed by Alembic.

Bootstrap failures are logged but do not prevent Uvicorn from starting.
Zotero sync is also best-effort except when strict SDL Stage 1 validation is
enabled. Check CloudWatch startup logs and actual data responses in addition
to `/health`; a healthy process alone does not verify the corpus.

Zotero-only corpus policies are separate from deployment configuration. Keep
the active environment's corpus policy when releasing changes; author-monitor
ingestion uses the open-corpus deployment. Destructive corpus replacement is
covered separately in [zotero_cutover.md](zotero_cutover.md).

## Verification

Run `bash scripts/cloud/check.sh` in Codespaces before releasing. It builds
both frontends and tests CORS configuration, preserved navigation, author
monitoring, public paper access and private research permissions.

After an AWS release, verify ECS service stability, the public paper API,
paper/Wiki links, and rejection of unauthenticated requests to admin or private
data endpoints. Keep the previously verified ECS task definition and frontend
builds for rollback within AWS.
