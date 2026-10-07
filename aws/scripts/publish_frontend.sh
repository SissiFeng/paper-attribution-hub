#!/usr/bin/env bash
# Run after both frontend builds. Public uploads contain no admin assets/data.
set -euo pipefail
PAS_DIST="$1"
PAS_READING_DIST="$2"
PAS_FRONTEND_BUCKET="$3"
# Keep static reports/data authenticated. Public assets contain only compiled UI.
aws s3 sync "$PAS_DIST/" "s3://${PAS_FRONTEND_BUCKET}/protected-legacy/" --exclude "index.html" --exclude "assets/*" --cache-control "private,no-store"
aws s3 sync "$PAS_DIST/assets/" "s3://${PAS_FRONTEND_BUCKET}/assets/" --exclude "*" --include "*.js" --include "*.css" --cache-control "public,max-age=31536000,immutable"
aws s3 cp "$PAS_DIST/index.html" "s3://${PAS_FRONTEND_BUCKET}/index.html" --cache-control "no-store" --content-type "text/html"
aws s3 cp "$PAS_READING_DIST/reading.html" "s3://${PAS_FRONTEND_BUCKET}/reading/index.html" --cache-control "no-store" --content-type "text/html"
aws s3 sync "$PAS_READING_DIST/assets/" "s3://${PAS_FRONTEND_BUCKET}/reading/assets/" --cache-control "public,max-age=31536000,immutable"
