# GNN Graph ML Development Plan

This plan tracks the paper-classification GNN path separately from the current
rule classifier and learned tabular classifier.

## Completed slices

- Export a heterogeneous paper graph as JSONL artifacts:
  - `nodes.jsonl`
  - `edges.jsonl`
  - `labels.jsonl`
  - `manifest.json`
- Include paper, author, institution, lab, entity, topic, and AC-core-paper nodes.
- Include authorship, affiliation, lab-link, entity-mention, citation, and topic edges.
- Keep export read-only; no change to production classification decisions.
- Add a graph-feature classification baseline:
  - derive fixed structural counts without reading classifier scores, labels,
    confidence values, edge weights, or classifier-derived topic edges;
  - train a balanced logistic regression inside leave-one-out folds using only
    overlapping canonical hand-curated gold labels;
  - accept `SDL_FIELD_RELEVANT` and normalize the legacy review label `INCLUDE`
    to `RELATED_RELEVANT` through the shared classification-label contract;
  - compare baseline metrics with non-human-confirmed current classifier labels
    on the same gold rows;
  - reject incompatible graph manifest versions, empty graphs, missing gold
    overlap, single-class targets, and untrainable leave-one-out folds;
  - write an optional JSON report without saving or deploying a model.

## Next slices

1. Add a real GNN experiment path.
   - Convert JSONL artifacts to PyTorch Geometric or DGL input.
   - Start with paper node classification before edge classification.
   - Keep dependencies optional and outside the production API path.

2. Add edge-classification tasks.
   - Predict `paper -> lab` attribution links.
   - Predict high-confidence `paper -> entity` or `paper -> AC core` links.
   - Use human-confirmed and AC-gold labels as the evaluation set.

3. Add model-gating before production use.
   - GNN output can only act as a reranker or review-priority signal until it
     beats the current classifier on held-out gold/human labels.
   - Do not train final labels from synthetic data alone; use synthetic data
     only for pretraining or stress tests.
