# Classification Autoresearch Program

## Goal

Classification must be treated as a gated research loop, not a one-off model
run. Every new human review updates `data/eval_labels.csv`; after a batch of
reviews, the candidate classifier must be re-run and accepted only if it still
passes fixed gold-set gates.

## Inputs

- `data/eval_labels.csv`: human-confirmed labels from review. This is the main
  regression set and is allowed to contain all labels.
- `ac_known_publication=True`: AC Publications positive gold set. Every row
  must classify as `CORE_RELEVANT` or `RELATED_RELEVANT`.
- Current classifier outputs in `paper_classifications`.
- Optional learned model retrained by `active_learning.maybe_retrain`.

## Fixed Gates

1. `human_gold_labels_present`: at least one human gold row overlaps classified
   papers.
2. `human_gold_accuracy_100`: every human-confirmed label matches exactly.
3. `human_gold_macro_f1_100`: every label class remains perfect, not just the
   positive class.
4. `ac_publications_recall_100`: every AC Publications row is CORE/RELATED.
5. `ac_publications_precision_100`: no non-gold paper is promoted to
   CORE/RELATED without review.

If any non-skipped gate fails, the candidate is rejected. False positives should
be routed to human review; accepted positives expand gold, rejected positives
become veto features, negative keywords, or training examples.

## Command

```bash
cd backend
uv run python -m app.scripts.run_classification_autoresearch --reclassify --json
```

Use `--out backend/reports/autoresearch/classification_latest.json` in
deployment or CI to persist the full report.

## Iteration Loop

1. Human reviews ambiguous or high-impact papers.
2. `active_learning.on_review_submitted` upserts the gold row into
   `data/eval_labels.csv`.
3. After enough reviews, `maybe_retrain` rebuilds the learned classifier.
4. Run `run_classification_autoresearch --reclassify`.
5. Accept only if all gates pass; otherwise use the report details to update
   rules, vocab, negative keywords, or training examples.

## Why This Is Strict

The target is 100% precision/recall for the scoped gold standards. Generalizing
to other datasets is handled by promoting uncertain examples into review tiers,
then only trusting the algorithm after those new labels join the same fixed
gate suite.
