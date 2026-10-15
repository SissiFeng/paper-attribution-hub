# Paper Attribution System (MVP v0.6)

Evidence-based paper attribution pipeline with structured analytics, proactive missed-paper discovery, and **research-intelligence reporting**. The system judges papers it's given, walks the corpus to find papers it should have, and now also produces leadership-grade dashboards + an auto-generated annual-report-style summary where **every number in the prose is a clickable link to the SQL query that produced it**.

Six layers, deliberately not mixed: visualization (ECharts) → analytics (SQL + NetworkX) → graph (`graph_service`) → persistence → external enrichment → **reporting & intelligence (v0.6)**. The RAG / LLM layer is parallel — it only narrates structured numbers; it never invents edges or digits. See `docs/research_intelligence_design.md` for the v0.6 contract.

The global bottom-right chat is stricter than the separate Graph-RAG workspace:
it uses deterministic, allow-listed, parameter-bound Text-to-SQL and renders
answers directly from returned rows. It never invokes an LLM and fails closed
when a question cannot be mapped to an approved query template.

**v0.1**: CSV metadata ingestion, entity normalization, multi-signal matching, rule-based classification, review API, CSV export, co-author network.
**v0.2**: PDF/text full-text ingestion, section-aware chunking, TF-IDF embeddings, BM25+cosine hybrid retrieval, evidence extractor, classifier extension with `fulltext_evidence_score`, versioned reference-set evaluation.
**P2 screening**: broad-corpus scoring persists an auditable route for every classified paper; only positive, uncertain, or full-text-needed subsets enter human review.
**v0.3**: citation graph + `ac_core_papers`, second-degree collaborator detection, citation-based attribution rules, unified `PaperFilter`, analytics endpoints, Graph-RAG explanation, ECharts dashboard.
**v0.4**: GROBID adapter with PyMuPDF fallback, contextual chunking, domain-aware retokenization, proposition extractor, optional cross-encoder reranker, `/papers/{id}/propositions` API.
**v0.5**: OpenAlex / Semantic Scholar / Crossref clients with SQLite-backed cache, source reliability ladder, author disambiguation hardening (ORCID-first), hybrid discovery service (cite-of-core / ac-coauthor / S2 recommendations), `/discovery` API + page, paper `provenance` tracking.
**v0.6** (this repo): **Research impact dashboard** (`/analytics/impact` — YoY paper growth, citation impact, top emerging collaborators, top growing themes) · **Topic drift detection** (`/analytics/drift` — yearly topic vectors + cosine similarity + drift events) · **Missed-paper grouped view** (`/analytics/missed-papers` — re-cuts the discovery queue by reviewer-facing rationale) · **Reporting assistant** (`/analytics/report` — SQL → MetricTriple list → templated English with `[src:]` tags → optional Anthropic Claude rewriter with strict no-invent-numbers contract).
**v0.8**: Cross-SDL knowledge base with lab registry, typed entities, transfer analytics, OKF-compatible Markdown export, SAG-lite derived event trails, and GNN-ready graph dataset export.
**v0.9+ extension points**: persistent SAG event graph, graph-feature baseline, optional GNN experiments, self-evolving agent loop (`newidea.md` Option A), external citation impact via OpenAlex `cited_by_count`, geographic collaboration map, multi-language reporting.

## Quick start

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Run the full pipeline on bundled sample data:
python -m app.scripts.run_classification --reset                # v0.1 path (metadata only)
python -m app.scripts.run_classification --reset --with-fulltext  # v0.2 path (also indexes data/fulltexts/)
python -m app.scripts.run_eval                                   # P/R/F1 + evidence-recall@k
# Start API:
uvicorn app.main:app --reload --port 8000
```

Open <http://localhost:8000/docs> for the OpenAPI UI.

### Scheduled daily pipeline (v0.7 review loop)

The system has a single CLI entrypoint that runs the full automated cycle:
discover new papers → ingest + classify them incrementally → refresh the
review queue → write an audit row. Human-confirmed labels are never
overwritten, so re-running is idempotent.

```bash
# Plain pass — only re-classifies papers already in the corpus that need it.
python -m app.scripts.run_daily_pipeline

# Also pull new candidates from OpenAlex / Semantic Scholar / Crossref.
PAS_PIPELINE_DISCOVERY=1 python -m app.scripts.run_daily_pipeline

# Full upgrade: discovery + full-text evidence + learned classifier + LLM judge.
PAS_PIPELINE_DISCOVERY=1 PAS_PIPELINE_FULLTEXT=1 \
    PAS_LEARNED_CLASSIFIER=1 PAS_LLM_JUDGE=1 \
    PAS_LLM_JUDGE_BACKEND=anthropic ANTHROPIC_API_KEY=... \
    python -m app.scripts.run_daily_pipeline --json
```

Exit code is `0` on success and `1` on failure, so cron will email you on
errors. Add `--json` for a machine-readable summary.

**cron (Linux server):**

```
# /etc/cron.d/paper-attribution
PATH=/usr/local/bin:/usr/bin:/bin
PYTHONUNBUFFERED=1
0 6 * * * pas cd /srv/paper-attribution/backend && \
    PAS_DATABASE_URL=postgresql://... PAS_PIPELINE_DISCOVERY=1 \
    .venv/bin/python -m app.scripts.run_daily_pipeline --json \
    >> /var/log/paper-attribution/daily.log 2>&1
```

**launchd (macOS dev):**

```xml
<!-- ~/Library/LaunchAgents/com.ac.paper-attribution.plist -->
<plist version="1.0"><dict>
  <key>Label</key><string>com.ac.paper-attribution</string>
  <key>StartCalendarInterval</key><dict>
    <key>Hour</key><integer>6</integer><key>Minute</key><integer>0</integer>
  </dict>
  <key>WorkingDirectory</key><string>/Users/me/paper-attribution/backend</string>
  <key>ProgramArguments</key><array>
    <string>/Users/me/paper-attribution/backend/.venv/bin/python</string>
    <string>-m</string><string>app.scripts.run_daily_pipeline</string>
  </array>
  <key>StandardErrorPath</key><string>/tmp/pas-daily.err</string>
</dict></plist>
```

Then `launchctl load ~/Library/LaunchAgents/com.ac.paper-attribution.plist`.

**Manual trigger from the UI / curl:**

```
curl -X POST http://localhost:8000/pipeline/run \
     -H 'content-type: application/json' \
     -d '{"do_discovery": true, "use_judge": true}'
```

### Review loop (human-in-the-loop)

After the daily pipeline runs, papers in the borderline / auto-ingested-low-
confidence / disqualifying-evidence-conflict bands get `needs_review=true`.
A reviewer hits:

```
GET  /reviews/queue              # priority-sorted list
GET  /reviews/queue/next         # the single highest-priority paper
POST /reviews/{paper_id}/confirm # "the system was right" → locks label
POST /reviews/{paper_id}/skip    # defer for cooldown_days
POST /reviews/{paper_id}         # correct label (existing endpoint)
```

`POST /reviews/{paper_id}` and the confirm endpoint feed the **active learning
loop** when a complete review contains an explicit classifier label. Every 20
distinct eligible reviewed papers trigger a full retrain on all allowed
training labels. The candidate is evaluated out-of-fold and on a required,
training-disjoint fixed validation set; it is atomically promoted only when accuracy,
macro-F1, and supported per-label recall do not regress and at least one
protected metric strictly improves. Frozen `eval_labels.csv` rows never enter
training. See [`docs/model_evolution.md`](docs/model_evolution.md).

`GET /pipeline/runs/latest` and `GET /pipeline/runs` expose the audit log
so the dashboard can show "last run @ 06:00 — 12 new papers, 3 flagged."
`GET /model-evolution/status` and `GET /model-evolution/runs` expose the
20-review pulse and every promoted, rejected, or failed candidate.

Every trust-sensitive analytics response (timeline, institution network,
geographic collaboration, and multi-graph) includes the canonical filter,
filter fingerprint, paper-set hash, coverage counts, corpus-source breakdown,
algorithm identifier, and metric definitions. `GET /analytics/scope` replays
the same evidence scope independently; see [`docs/filter_spec.md`](docs/filter_spec.md).

### Cross-SDL knowledge base (v0.8)

Typed entity extraction (methods / materials / instruments / software, evidence-linked)
+ a real lab registry (77 AC PI groups generated from `data/ac_members.csv`)
+ paper→lab links (explicit `AC Members` column at confidence 1.0, author-roster fallback)
power per-entity and per-lab knowledge pages and lab-to-lab transfer analytics.

```bash
# Build / refresh the KB (idempotent):
python -m app.scripts.ingest_scopus_batch --reset   # corpus (11,268 papers incl. 483 AC gold)
python -m app.scripts.build_lab_registry            # regenerate data/sdl_labs.yaml from ac_members.csv
python -m app.scripts.seed_sdl_labs                 # upsert labs + map papers to labs
python -m app.scripts.run_entity_extraction         # typed entities with evidence links
python -m app.scripts.backfill_references           # citation edges via OpenAlex (network required)
python -m app.scripts.export_kb_md                  # OKF-compatible Markdown KB → outputs/kb/
python -m app.scripts.run_evolutionary_transfer_search --target sdl4
python -m app.scripts.export_graph_ml_dataset       # GNN-ready graph JSONL → outputs/graph_ml/
```

APIs: `/kb/summary`, `/kb/entities`, `/kb/entities/{type}/{name}`, `/kb/labs/{id}/profile`,
`/analytics/transfer/{flows,adoption,summary}`, `/labs`. Frontend: **Knowledge Base**,
**Knowledge Transfer**, and per-lab profile pages. `/transfer/evolve` runs a deterministic
evolutionary search over DB TKUs plus the 483 AC focused `knowledge_json` files, then the CLI
writes Karpathy-style autosearch run cards under `llm-wiki/autosearch/`. Gold-label expansion
workflow: see `docs/labeling_workflow.md`.

The KB Markdown export now follows the Open Knowledge Format shape: each page has
YAML front matter with `type`, `title`, `description`, `resource`, `tags`, and
`timestamp`. Entity pages also include a **SAG-lite Event Trail**, derived from
existing paper/entity/chunk/lab rows. This is a read-only event view, not a
persistent event graph yet.

The graph ML export is a data contract for future paper-classification GNN work.
It writes `nodes.jsonl`, `edges.jsonl`, `labels.jsonl`, and `manifest.json`.
It does not change production classification decisions.

Development status and next steps live in `backend/docs/development_progress.md`.
Detailed follow-up plans live in `backend/docs/sag_lite_development_plan.md` and
`backend/docs/gnn_graph_ml_development_plan.md`.

### Frontend

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

The frontend expects the backend at `http://localhost:8000` (override with `VITE_API_BASE`).

## Architecture

```
data sources (CSV / future DB / future PDF)
        │  source adapter (swappable)
        ▼
┌──────────────────────┐
│ 1. Ingestion         │  load_papers / load_people / load_topics
├──────────────────────┤
│ 2. Normalization     │  unicode-fold, alias expand, dedup DOI, fuzzy join
├──────────────────────┤
│ 3. Matching          │  author / institution / topic / network scoring
├──────────────────────┤
│ 4. Classification    │  deterministic rules → label + confidence + reasons
├──────────────────────┤
│ 5. Review / Export   │  REST API, CSV export, co-author network JSON
└──────────────────────┘
```

Modules are independent — swapping the CSV source adapter for a DB or full-text adapter doesn't require rewriting the matching/classification layer.

## Project layout

```
backend/
  app/
    main.py                  FastAPI entrypoint
    config.py                Settings + paths
    db.py                    SQLAlchemy session (SQLite for MVP)
    models/                  ORM tables
    adapters/                Source adapters (CSV today, DB/PDF tomorrow)
    services/                ingestion / normalization / matchers / classifier
    api/                     REST routes
    scripts/                 CLI: import_papers, run_classification
  docs/                      current development progress and experimental plans
  tests/
data/
  sample_papers.csv
  ac_members.csv
  institution_aliases.csv
  topic_taxonomy.yaml
frontend/                    React + Vite + TanStack Table
docs/
  mvp_spec.md
  data_schema.md
  classification_rules.md
```

## Classification labels

| Label | Meaning | Default rule |
|---|---|---|
| `CORE_RELEVANT` | AC author + on-topic | `author ≥ 0.9 ∧ topic ≥ 0.5` |
| `RELATED_RELEVANT` | AC author OR (strong topic + UofT) | `author ≥ 0.9` or `topic ≥ 0.8 ∧ inst ≥ 0.5` |
| `ADJACENT` | Topic-only signal | `topic ≥ 0.7` |
| `UNCERTAIN` | Mid-range, send to human | any score in `[0.4, 0.7)` |
| `EXCLUDE` | No meaningful signal | otherwise |

Thresholds live in `backend/app/services/relevance_classifier.py` and `docs/classification_rules.md`.

## What is intentionally NOT in v0.2

- Citation graph / Graph RAG (planned v0.3)
- Cross-encoder reranker (planned v0.3)
- LLM-generated explanations (kept deterministic + chunk-cited to avoid the 40%-accuracy hallucination failure mode)
- HyDE / Doc2Query (planned v0.3)
- Multi-tenant auth, scheduled OpenAlex/Crossref ingestion

## AWS Deployment

AWS is the only supported deployment target: ECS Fargate (backend), RDS PostgreSQL with pgvector (database), S3 + CloudFront (frontend), and S3 (artifact storage). Codespaces and Docker Compose are development environments.

### Quick Deploy

```bash
# 1. Run the one-time AWS console setup (see docs/aws-console-setup.md)
# 2. Deploy infrastructure
./aws/scripts/deploy.sh prod

# 3. Set API keys in SSM (see docs/aws-console-setup.md Step 6)
# 4. Set GitHub Actions secrets (see docs/aws-console-setup.md Step 7)
# 5. Push to main → CI/CD auto-deploys
```

### Architecture

- **Backend**: ECS Fargate (1-4 tasks, auto-scaled) behind ALB with HTTPS
- **Database**: RDS PostgreSQL 16 with pgvector extension
- **Frontend**: React SPA on S3 + CloudFront with SPA routing
- **Artifacts**: S3 bucket with lifecycle policies for reviews, exports, model snapshots
- **CI/CD**: GitHub Actions with OIDC (no long-lived credentials)
- **Infrastructure**: Terraform (see `aws/terraform/`)

### Documentation

- **Setup**: `docs/aws-console-setup.md` — Manual AWS console steps (one-time)
- **Operations**: `docs/aws-deployment.md` — Full deployment guide, cost estimates, backup procedures

---

See `docs/mvp_spec.md` for v0.1 scope, `docs/rag_design.md` for the v0.2 RAG design, and `docs/eval_methodology.md` for evaluation.
