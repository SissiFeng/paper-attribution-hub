#!/usr/bin/env bash
set -euo pipefail
PAS_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PAS_ROOT"
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install --disable-pip-version-check --no-cache-dir -r backend/requirements-dev.txt
npm ci --prefix frontend --no-audit --no-fund
bash scripts/cloud/check.sh
printf '\nPAS setup complete. Start the private sample preview with: bash scripts/cloud/preview.sh\n'
