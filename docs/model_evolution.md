# Review-driven model evolution

## Production contract

Every distinct eligible paper review is persisted as an immutable training
feedback event. Validation and frozen evaluation paper IDs are excluded before
an event can enter a training batch. Reconciliation is idempotent, so a review
that was saved while the label boundary was unavailable can be recovered later
without double counting.

The API does not train in a request or FastAPI background task. Run the durable
worker once with:

```bash
python -m app.scripts.run_model_evolution --json
```

The worker reconciles feedback, claims complete batches, renews a database
lease while training, and leaves incomplete feedback pending. The default batch
size is 20 distinct eligible papers (`PAS_ACTIVE_RETRAIN_EVERY=20`).

## Candidate states and authority

- `STAGED`: the candidate passed the configured non-regression/improvement gate
  and is retained with its model artifact and audit metrics. This is the safe
  default.
- `REJECTED`: the candidate regressed, did not strictly improve, or failed a
  protected gate. Its artifact and metrics remain auditable.
- `PROMOTED`: the candidate passed and explicit automatic-promotion authority
  was enabled with `PAS_MODEL_AUTO_PROMOTE=1`.
- `FAILED` or `INVALIDATED`: execution failed or the claimed feedback batch
  became ineligible. The run remains visible for diagnosis.

Production promotion is intentionally disabled in AWS development configuration.
A passing candidate can still regress outside the measured sample, so staging
is not evidence that it should replace the incumbent. Promotion requires a
training-disjoint validation set with sufficient examples and label coverage,
non-regression on protected metrics, at least one strict improvement, and an
operator decision based on the stored run evidence.

`eval_labels.csv` is a frozen reporting holdout. It is never used for fitting,
candidate selection, threshold tuning, or promotion.

## AWS execution

Terraform creates one reusable Fargate worker task definition:

- every five minutes: reconcile feedback and drain complete model batches;
- daily at 06:00 UTC: run incremental classification and staged screening;
- on delivery/start/non-zero-exit failure: write an event to SQS and alarm.

The daily pipeline also runs reconciliation as a secondary recovery path. Both
paths use the same database lease, so simultaneous triggers cannot promote or
consume the same batch twice.

Useful endpoints:

```text
GET /model-evolution/status
GET /model-evolution/runs
GET /pipeline/runs/latest
GET /pipeline/runs
```
