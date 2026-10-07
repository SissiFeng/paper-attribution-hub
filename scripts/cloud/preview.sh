#!/usr/bin/env bash
# Private development preview with the existing synthetic member/admin fixture.
set -euo pipefail
PAS_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PAS_ROOT"
export PAS_BROWSER_TEST_DIR="$PAS_ROOT/.local/cloud-preview"
mkdir -p "$PAS_BROWSER_TEST_DIR"
chmod 700 "$PAS_BROWSER_TEST_DIR"
export PAS_BROWSER_TEST_ORIGIN=http://localhost:8877
if [[ "${CODESPACES:-false}" == true ]]; then
  export PAS_BROWSER_TEST_ORIGIN="https://${CODESPACE_NAME}-8877.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
fi
export PAS_EXPLORATION_WORKER=0
printf 'Synthetic development data only. Keep port 8877 private.\nOpen %s/fixture to select a sample member or administrator.\n' "$PAS_BROWSER_TEST_ORIGIN"
exec backend/.venv/bin/python -m uvicorn --app-dir backend/tests/browser research_server:app --host 127.0.0.1 --port 8877
