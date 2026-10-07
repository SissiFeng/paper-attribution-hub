#!/usr/bin/env bash
set -euo pipefail
PAS_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PAS_ROOT"
# Build with the committed AWS production defaults in frontend/.env.production.
npm run build --prefix frontend
npm run build:reading --prefix frontend
npm run check:navigation --prefix frontend
npm run check:paper-view --prefix frontend
backend/.venv/bin/python -m pytest tools/author-paper-monitor/tests -q --disable-warnings --maxfail=1
backend/.venv/bin/python -m pytest backend/tests/test_config_cors.py backend/tests/test_catalog.py backend/tests/test_access_control.py backend/tests/test_private_reading.py backend/tests/test_research_workspace.py backend/tests/test_research_exploration.py -q --disable-warnings --maxfail=1
