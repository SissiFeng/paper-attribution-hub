# Development Progress

This document tracks the current implementation state for the knowledge-base,
SAG-lite, and graph-ML work. Keep it current when a slice lands or when a
planned item moves out of scope.

## Current Status

| Area | Status | Notes |
|---|---|---|
| Cross-SDL KB | Built | Lab registry, paper-to-lab links, typed entities, entity pages, lab pages, and transfer analytics are in place. |
| OKF export | Built | `export_kb_md` writes OKF-compatible Markdown under `outputs/kb/`. |
| SAG-lite | First slice built | Entity pages expose derived event trails from existing paper/entity/chunk/lab rows. No event tables yet. |
| GNN graph ML | Baseline built | Graph JSONL export plus a leakage-safe structural-feature baseline with leave-one-out evaluation are in place. |
| Review semantics | P0/P1 built | Corpus sources are explicit; SDL, AC, and AI-for-science judgements are independent; the review queue exposes the context needed to adjudicate them. |
| Staged screening | P2 built | The broad corpus is scored, but only positive, uncertain, and full-text-needed routes enter the human queue; route counts are audited per pipeline run. |
| Human-review model evolution | Built | Every 20 distinct eligible reviews trigger a full candidate retrain; leakage-safe metrics gate atomic promotion and every attempt is auditable. |
| Auditable analytics and filters | Built | Shared URL/SQL filters, scope fingerprints, paper-set hashes, coverage counts, metric contracts, graph thresholds, and defensible collaboration views are exposed end to end. |
| Production classifier | Gated evolution | The rule classifier remains the baseline; only a promoted learned candidate may provide the existing soft override. SAG-lite and graph exports remain non-authoritative. |

## Completed Work

### Auditable corpus and independent review dimensions

- `Paper.corpus_sources` preserves every known retrieval route instead of
  forcing one paper into one provenance bucket.
- `HumanReview` stores independent SDL, AC relevance, and AI-for-science
  judgements together with review status, evidence level, and judgement basis.
- A dimensional review without `human_label` cannot enter the legacy
  active-learning dataset. Explicit classifier-label corrections remain
  backward compatible.
- The review queue returns title, abstract, ordered authors, institutions,
  publication metadata, corpus sources, model evidence, and a full-text/DOI
  link where available.
- An `INSUFFICIENT_EVIDENCE` judgement becomes `NEEDS_FULLTEXT` and remains in
  the review queue instead of being silently treated as completed.
- The bundled 11-row reference set is marked `AC_REPORTING`; evaluation
  responses state that its metrics are not strict SDL accuracy.

Verification:

```bash
uv run pytest \
  backend/tests/test_review_dimensions.py \
  backend/tests/test_review_queue.py \
  backend/tests/test_review_queue_api.py \
  backend/tests/test_label_dataset.py \
  backend/tests/test_eval.py \
  backend/tests/test_alembic_migrations.py
cd frontend && npm run build
```

### Staged broad-corpus screening

- `PaperClassification` persists `screening_stage`, `screening_route`, and
  `screening_reason` without changing classifier authority over label and
  confidence.
- Eligible explicit training feedback becomes `SEED_REFERENCE`; validation
  and frozen-holdout IDs cannot become training seeds.
- Positive labels, uncertain/low-confidence predictions, and full-text-needed
  reviews are the only routes that can enter the human queue.
- High-confidence non-positive papers remain searchable as `SCREENED_OUT`
  rather than consuming review capacity.
- Every scheduled run records the complete funnel counts in a
  `staged_screening` audit step.

Detailed contract: `docs/staged_screening.md`.

### Gated full-model evolution

- Complete reviews contribute immutable, de-duplicated training-feedback
  events; incomplete/full-text-needed reviews and reserved evaluation IDs are
  excluded.
- The 20th distinct pending paper claims one batch under a database lock and
  schedules a response-time background run that retrains the learned
  classifier from scratch on all curated and eligible human labels.
- Trigger-batch out-of-fold evaluation is always required. Promotion also
  requires a training-disjoint fixed validation set with at least 20 examples
  across at least two labels by default; an undersized set fails closed.
- Accuracy, macro-F1, and supported per-label recall cannot regress, and at
  least one protected metric must strictly improve before atomic promotion.
- Candidate and incumbent metrics, data hashes, artifact hashes, versioned
  model bytes, and the promotion/rejection reason are persisted.
- Frozen holdout labels remain release-only. Promoted versions make unlocked
  classifications stale for the next incremental pipeline refresh.
- The scheduled pipeline retries complete/stale batches so a process restart
  cannot permanently strand a response-time background task.

Detailed contract: `docs/model_evolution.md`.

### Auditable filters and defensible visual analytics

- Every list and trust-sensitive analytics endpoint uses the same
  `PaperFilter`; values within one dimension use OR and dimensions combine
  with AND. Invalid enum values and inverted ranges return 422.
- Human SDL/AC judgements take precedence over explicitly mapped legacy model
  scope labels. The audit response states this resolution rule.
- Analytics expose a stable filter fingerprint and paper-set hash together
  with included/classified/reviewed/full-text counts and corpus provenance.
- Multi-graph presets implement author, institution, country, author-paper,
  institution-paper, and topic-paper projections. `min_papers`, iterative
  `min_degree`, and deterministic top-N thresholds run server-side.
- Timeline, institutional network, and geographic views count distinct papers.
  Multi-membership timelines are not stacked, and collaboration weights are
  never labelled as influence.
- Geographic center growth defaults to University of Toronto when available
  and can project around any persisted institution or country. The URL and
  audit distinguish the center projection from the shared paper filter, and
  evidence-subset hashes support replay of center/collaboration counts.

Detailed contract: `docs/filter_spec.md` and `docs/visualization_design.md`.

### OKF-compatible KB export

- `backend/app/scripts/export_kb_md.py` writes Markdown pages with OKF-style
  front matter.
- The root `index.md` declares `okf_version: "0.1"`.
- Entity and lab pages include API-style `resource` fields so agents can map
  static pages back to live endpoints.

Verification:

```bash
uv run pytest backend/tests/test_export_kb_md.py
python -m ruff check backend/app/scripts/export_kb_md.py backend/tests/test_export_kb_md.py
```

### SAG-lite event trail

- `backend/app/services/sag_lite_service.py` derives event-like records from
  `PaperEntity`, `PaperChunk`, `Paper`, and `PaperLabLink`.
- `/kb/entities/{entity_type}/{name}` now returns an `events` list.
- KB Markdown entity pages render a `SAG-lite Event Trail` section.

Verification:

```bash
uv run pytest backend/tests/test_sag_lite_service.py backend/tests/test_kb_service.py backend/tests/test_export_kb_md.py
python -m ruff check backend/app/services/sag_lite_service.py backend/app/services/kb_service.py backend/app/schemas.py backend/app/scripts/export_kb_md.py backend/tests/test_sag_lite_service.py backend/tests/test_kb_service.py backend/tests/test_export_kb_md.py
```

Detailed plan: `backend/docs/sag_lite_development_plan.md`.

### GNN-ready graph ML dataset

- `backend/app/services/graph_ml_dataset_service.py` collects a heterogeneous
  paper graph from the current DB.
- `backend/app/scripts/export_graph_ml_dataset.py` writes:
  - `nodes.jsonl`
  - `edges.jsonl`
  - `labels.jsonl`
  - `manifest.json`
- The export includes paper, author, institution, lab, entity, topic, and
  AC-core-paper nodes.
- The export includes authorship, affiliation, lab-link, entity-mention,
  citation, and topic edges.

Verification:

```bash
uv run pytest backend/tests/test_graph_ml_dataset_service.py
python -m ruff check backend/app/services/graph_ml_dataset_service.py backend/app/scripts/export_graph_ml_dataset.py backend/tests/test_graph_ml_dataset_service.py
```

Detailed plan: `backend/docs/gnn_graph_ml_development_plan.md`.

### Graph-feature classification baseline

- `backend/app/services/graph_feature_baseline.py` derives fixed structural
  features from the graph export without consuming classifier labels,
  confidence values, score fields, edge weights, or classifier-derived topic
  edges.
- `backend/app/scripts/run_graph_feature_baseline.py` evaluates a balanced
  logistic-regression baseline with leave-one-out validation on the canonical
  hand-curated gold-label CSV.
- The shared label contract includes `SDL_FIELD_RELEVANT`; the legacy review
  label `INCLUDE` is normalized to `RELATED_RELEVANT` before evaluation.
- The report includes non-human-confirmed current classifier labels on the same
  overlapping gold rows as a comparator. No model is saved and production
  decisions remain unchanged.
- Empty graphs, incompatible manifest versions, missing gold overlap,
  single-class labels, and untrainable leave-one-out folds fail closed.

Verification:

```bash
uv run pytest backend/tests/test_graph_feature_baseline.py backend/tests/test_graph_ml_dataset_service.py
python -m ruff check backend/app/services/graph_feature_baseline.py backend/app/scripts/run_graph_feature_baseline.py backend/tests/test_graph_feature_baseline.py
```

## Commands

Build the KB and graph export from a populated database:

```bash
python -m app.scripts.export_kb_md --output-dir outputs/kb
python -m app.scripts.export_graph_ml_dataset --output-dir outputs/graph_ml
python -m app.scripts.run_graph_feature_baseline \
  --graph-dir outputs/graph_ml \
  --labels data/eval_labels.csv \
  --json \
  --out backend/reports/graph_feature_baseline.json
```

Run the targeted verification set:

```bash
uv run pytest \
  backend/tests/test_export_kb_md.py \
  backend/tests/test_sag_lite_service.py \
  backend/tests/test_kb_service.py \
  backend/tests/test_graph_ml_dataset_service.py
```

## Next Work

1. Persist SAG events after the derived event shape stabilizes.
   - Add `paper_events` and `paper_event_entities`.
   - Keep the derived service as a fallback during rollout.

2. Add SAG-style retrieval.
   - Query path: text query -> entity/proposition match -> event hop -> source chunk.
   - Return the traversal trace to the caller.

3. Add a GNN experiment path only after the baseline is useful.
   - Convert JSONL artifacts to PyTorch Geometric or DGL input.
   - Keep new ML dependencies outside the production API path.

4. Gate any model output before production use.
   - Use GNN output as review priority or rerank signal first.
   - Replace classification behavior only after evaluation shows a clear gain.
