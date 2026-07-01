# GNN Graph ML Development Plan

This plan tracks the paper-classification GNN path separately from the current
rule classifier and learned tabular classifier.

## Completed slice

- Export a heterogeneous paper graph as JSONL artifacts:
  - `nodes.jsonl`
  - `edges.jsonl`
  - `labels.jsonl`
  - `manifest.json`
- Include paper, author, institution, lab, entity, topic, and AC-core-paper nodes.
- Include authorship, affiliation, lab-link, entity-mention, citation, and topic edges.
- Keep export read-only; no change to production classification decisions.

## Next slices

1. Add a graph-feature baseline.
   - Train/evaluate logistic regression or random forest on graph-derived features.
   - Compare against current rules on gold/human labels.

2. Add a real GNN experiment path.
   - Convert JSONL artifacts to PyTorch Geometric or DGL input.
   - Start with paper node classification before edge classification.
   - Keep dependencies optional and outside the production API path.

3. Add edge-classification tasks.
   - Predict `paper -> lab` attribution links.
   - Predict high-confidence `paper -> entity` or `paper -> AC core` links.
   - Use human-confirmed and AC-gold labels as the evaluation set.

4. Add model-gating before production use.
   - GNN output can only act as a reranker or review-priority signal until it
     beats the current classifier on held-out gold/human labels.
   - Do not train final labels from synthetic data alone; use synthetic data
     only for pretraining or stress tests.
