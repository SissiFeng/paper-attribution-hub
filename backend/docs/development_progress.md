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
| GNN graph ML | First slice built | `export_graph_ml_dataset` writes graph JSONL artifacts for future GNN and baseline experiments. |
| Production classifier | Unchanged | SAG-lite and graph-ML exports do not replace the rule classifier or learned tabular classifier. |

## Completed Work

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

## Commands

Build the KB and graph export from a populated database:

```bash
python -m app.scripts.export_kb_md --output-dir outputs/kb
python -m app.scripts.export_graph_ml_dataset --output-dir outputs/graph_ml
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

3. Add a graph-feature baseline before a real GNN.
   - Train a small baseline on exported graph features.
   - Compare against the current rules on held-out gold and human labels.

4. Add a GNN experiment path only after the baseline is useful.
   - Convert JSONL artifacts to PyTorch Geometric or DGL input.
   - Keep new ML dependencies outside the production API path.

5. Gate any model output before production use.
   - Use GNN output as review priority or rerank signal first.
   - Replace classification behavior only after evaluation shows a clear gain.
