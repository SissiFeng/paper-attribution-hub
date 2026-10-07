# Deployment Checklist

Three platforms, one stack:

| Platform | Role | Config |
|---|---|---|
| **Vercel** | Frontend SPA (React + Vite) | `frontend/vercel.json`, build `npm run build` → `dist/` |
| **Render** | Backend API (FastAPI in Docker) | `render.yaml` → `backend/Dockerfile` |
| **Supabase** | Postgres database | connection string → Render `PAS_DATABASE_URL` |

Data flow: Vercel frontend → (HTTPS) → Render API → (Postgres) → Supabase.

## Pre-demo verification (run locally)

Last verified 2026-07-23, all green:

```bash
# Backend boots, health/CORS/DB endpoints respond
cd backend && PYTHONPATH="$PWD" python -c "from fastapi.testclient import TestClient; \
from app.main import app; c=TestClient(app); print(c.get('/health').json())"

# Fresh-DB bootstrap (create_all + stamp head; never replays 0001)
python -m pytest tests/test_db_bootstrap.py tests/test_config_cors.py -q

# Frontend production build (same command Vercel runs)
cd ../frontend && npm install && npm run build   # → dist/, exit 0
```

## Required environment variables

### Render (backend) — set in dashboard, most are `sync: false`

| Var | Required | Notes |
|---|---|---|
| `PAS_DATABASE_URL` | **Yes** | Supabase Postgres URL (`postgresql://...`). Fresh DB is auto-bootstrapped on first boot. |
| `PAS_CORS_ORIGINS` | **Yes** | Must include the Vercel frontend origin. Accepts JSON (`["https://app.vercel.app"]`) **or** comma-separated (`https://app.vercel.app,https://x.io`). |
| `PORT` | auto | Render injects it; Dockerfile honors `${PORT:-8000}`. |
| `PAS_OPENALEX_MAILTO` | optional | Polite pool for OpenAlex. |
| `PAS_SEMANTIC_SCHOLAR_API_KEY` | optional | Higher S2 rate limits. |
| `PAS_KIMI_API_KEY` / `PAS_ANTHROPIC_API_KEY` | optional | LLM answer generation. Without either, `/retrieve/answer` returns grounded retrieval-only answers (no crash). |
| `PAS_ZOTERO_API_KEY` | **Yes** | Read-only key for the authoritative Zotero group library. |
| `PAS_ZOTERO_GROUP_ID` | **Yes** | Zotero group-library ID. |
| `PAS_ZOTERO_TIER1_COLLECTION` | **Yes** | Immutable Tier 1 collection key. |
| `PAS_ZOTERO_TIER2_COLLECTION` | optional | Immutable Tier 2 key; leave empty for the Tier 1-only pilot. |
| `PAS_ZOTERO_SYNC_ON_STARTUP` | recommended | Set `true` after the one-time cutover. |
| `PAS_ZOTERO_SOURCE_ONLY` | **Yes** | Keep `true` to prevent discovery APIs from adding papers outside Zotero. |

### Vercel (frontend) — set as build-time env vars

| Var | Required | Notes |
|---|---|---|
| `VITE_API_BASE` | **Yes** | The Render backend URL, no trailing slash. **Inlined at build time** — a rebuild is required after changing it. Defaults to `http://localhost:8000`, so if unset the deployed site cannot reach the API. |
| `VITE_USE_MOCK` | recommended | Set `false` for the demo (real API). `true` serves built-in mock data with no backend. |

### Supabase (database)

- Create a Postgres instance; copy the connection string into Render's `PAS_DATABASE_URL`.
- No manual schema step: the container's `db_bootstrap` builds the schema on an
  empty DB (`create_all` + `alembic stamp head`) and only runs incremental
  `alembic upgrade head` on an already-versioned DB.

## Container boot sequence (`backend/Dockerfile` CMD)

`CMD ["python", "-m", "app.scripts.serve"]` — a demo-safe entrypoint that runs:

```
db_bootstrap                                   # schema: create+stamp | stamp | upgrade
sync_zotero --seed-if-empty --classify         # only when startup sync is enabled
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

Bootstrap and Zotero sync are **best-effort**: a non-zero exit is logged as a
`[serve] WARNING` but uvicorn still starts, so `/health` and `/debug/db` stay
reachable for diagnosis. `uvicorn` is exec'd (replaces the process) so it
receives container signals.

The one-time backup and destructive replacement procedure is documented in
[`zotero_cutover.md`](zotero_cutover.md).

## Known risks / caveats

1. **Startup sync is best-effort, not fail-fast.** If Zotero sync fails, the API still
   boots but may serve an empty/partial dataset — check the `[serve] WARNING`
   lines in the Render logs and `/debug/papers` if the demo data looks thin.
   Retry with `python -m app.scripts.sync_zotero --seed-if-empty --classify`.
2. **`VITE_API_BASE` is build-time.** Changing it in Vercel requires a redeploy,
   not just an env update.
3. **pgvector on a *fresh* Postgres:** `db_bootstrap` stamps head, so migration
   `0002` (JSON→`vector(1536)`) does not run and the `embedding` column stays
   JSON. Harmless with the default `tfidf` embedder; only matters if you switch
   to `PAS_EMBEDDING_BACKEND=sbert` + pgvector, which then needs `0002` applied.
4. **Frontend bundle is ~3.3 MB (~1 MB gzip)**, single chunk. Loads fine; a
   code-split would speed first paint but is not demo-blocking.
5. **Render free plan cold starts** (~30–60 s) after idle — warm the API before
   the demo by hitting `/health`.
