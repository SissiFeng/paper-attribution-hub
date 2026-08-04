# Structured Extractor Data Factory

## Goal

Turn Cross-SDL extraction into a fixed-budget optimization loop:

```
generate/select training records
  -> train a LoRA adapter
  -> evaluate on one frozen gold benchmark
  -> analyze field-level failures
  -> generate targeted records for the next attempt
  -> select the best eligible checkpoint
```

The runner is an offline research control plane. It does not give an extractor,
Nexus, or HELIOS decision authority, and it does not publish a checkpoint into
production.

## Benchmark-specific profile

Each run starts from one YAML profile that freezes:

- seed training data and held-out gold test data;
- extraction schema, ontology, prompt, and model configuration;
- wall-clock, token, cost, human-review, attempt, and training-record budgets;
- evaluator command, metric paths, safety gates, and tie breakers;
- benchmark tier, required adversarial case types, and domain coverage;
- data identity, provenance, and lineage fields.

The evaluation fingerprint covers the benchmark, schema, ontology, selection
rules, evaluator command, resolved Python interpreter, and inference/verifier
source digests. Every `metrics.json` must echo this fingerprint. Changing any
of those inputs creates a different benchmark profile; it cannot be reported
as another attempt in the same comparison.

`profile.example.yaml` is a runnable profile-validation example, not a
scientific benchmark. Its model and command names are placeholders.

## Strict data boundary

The generator and LoRA trainer do not receive the benchmark path in their
step-scoped command context. Inference receives a derived file containing only
the fixed-safe `record_id`, `paper_id`, `chunk_id`, `input_text`, and optional
`context_chunks` fields; gold targets, provenance, case metadata, and all other
top-level values are omitted. Input roles must use distinct files/inodes, and
no non-benchmark input may duplicate benchmark content. Before training, the
runner also checks:

- no `record_id`, `paper_id`, or `chunk_id` overlaps the held-out test set;
- no normalized input content exactly overlaps test content;
- no input or adjacency-context content crosses the configured near-duplicate
  threshold, including padded containment and reordered-token cases;
- no training context chunk reuses a benchmark chunk identity;
- every training record declares `source_split: train`;
- every provenance kind is explicitly allowed;
- every synthetic, hard-negative, counterfactual, or paraphrase record points
  back to a trusted real training root;
- every record claiming `human_gold` or `curated_real` exactly matches an
  immutable seed record by ID and full-record hash;
- record IDs are present and unique;
- benchmark IDs and benchmark content are unique;
- training targets, benchmark targets, and predictions satisfy the frozen JSON
  Schema; every non-null claim has an exact source span; cited offsets resolve
  to the cited chunk; and research goals, strategies, decision operators,
  context conditions, and evidence types use their frozen ontology layers;
- the attempt stays below the training-record budget.

The three identity fields and `input_text` check are mandatory, `record_id` is
the fixed record key, and profiles may tighten but cannot loosen the system
near-duplicate ceiling of `0.92`.

Profiles may select only allowlisted executables and reviewed Python module
prefixes. The runner resolves the interpreter and every adapter source file,
hashes them into the run manifest, and checks an adapter again immediately
before execution. Subprocesses receive a minimal environment; model-registry
credentials are available only when their environment-variable names are
explicitly passed on the CLI with `--pass-env NAME` (names are audited, values
are redacted from logs regardless of variable name). Python and dynamic-loader
control variables are forbidden, and adapters execute with isolated Python
path handling. Profile adapters remain trusted code and require ordinary code
review—the runner enforces data contracts and provenance, but is not an
OS/container sandbox against malicious adapter code. Adapter entry sources are
hashed; a release run should additionally use an immutable wheel or container
because imported dependency closures are not frozen by this runner.

## Command contracts

Commands are argv lists and run with `shell=False`. Each step must use the
exact reviewed option/placeholder schema in the example profile; literal or
alternative output paths are rejected.

The generator must write:

- `train_records.jsonl`

The LoRA trainer must write:

- at least one file under `checkpoint/`

Checkpoint inference must write:

- `predictions.jsonl`

The separate deterministic verifier must score complete benchmark coverage and
write both `verification_records.jsonl` and `metrics.json`. Metrics must include
`evaluation_profile_sha256`, `checkpoint_sha256`, `predictions_sha256`, and
`verification_records_sha256`. Selection never trusts metrics emitted by
checkpoint inference.

The required analyzer must write a versioned `error_analysis.json` with complete
prediction counts, error categories, and non-empty targeting priorities when
failures exist.

Every external step atomically writes its own usage record with non-negative
`cost_usd`, `tokens`, `human_review_records`, and `training_seconds`. The runner
also requires the per-invocation `usage_nonce` exposed in the step environment,
rejects pre-existing future-step records, accounts usage before the next step,
and consolidates all records into `cost.json`; failed or interrupted attempts
are never silently recorded as zero-cost. Adapters must enforce the supplied
remaining budget with provider-side quotas where available: post-hoc usage
accounting cannot contain malicious or unmetered external code.

Usage values and selection metrics must be finite. Resume binds every completed
step—not only the active step—to its recorded nonce and digest. Failed and
interrupted attempts remain ineligible and their cost ledgers are revalidated.

The generator receives `previous_train_records` and
`previous_error_analysis`, which is the closed-loop signal for targeted
hard-negative, counterfactual, or cross-domain paraphrase generation.

## Evaluation contract

Do not select on a single blended F1. The example profile keeps four layers
visible:

1. evidence grounding: span F1 and unsupported-claim rate;
2. structured extraction: strategy and condition field metrics;
3. ontology normalization: hierarchical F1;
4. transfer usefulness: utility and negative-transfer risk.

The example selects by transfer utility only after every safety/quality gate
passes. A higher field F1 cannot compensate for an unsafe unsupported-claim
rate.

The runner also recomputes a separate `system_effectiveness.json` from the
benchmark targets and predictions. Case and domain correctness use strict
canonical JSON equality; the external verifier's `is_correct` contributes only
an agreement metric and cannot approve an attempt. Standard, hard-negative,
counterfactual-pair, cross-domain, and worst-domain results remain visible.
This prevents aggregate macro-F1 from hiding an unchanged counterfactual
prediction or an invented hard-negative claim anywhere in the structured
output.

The bundled five-record benchmark is marked `synthetic_smoke`. It validates the
gates, not scientific performance. A `release` benchmark accepts only
`human_gold` or `curated_real` provenance, requires all four adversarial case
types with at least 20 records per type across at least two domains, requires
minimum release thresholds for every mandatory system slice and verifier/gold
agreement, and must be independently curated.

## Audit artifacts

Each completed attempt contains:

```
attempt_001/
├── train_records.jsonl
├── extraction_schema.json
├── ontology_version.json
├── prompt_version.txt
├── model_config.json
├── checkpoint/
├── checkpoint_manifest.json
├── predictions.jsonl
├── verification_records.jsonl
├── error_analysis.json
├── metrics.json
├── system_effectiveness.json
├── cost.json
├── usage/
├── data_lineage.json
├── boundary_report.json
├── verifier.json
└── attempt_manifest.json
```

The run root adds:

- `benchmark_profile.yaml`
- `benchmark_manifest.json`
- `benchmark_inputs.jsonl`
- `initial_boundary_report.json`
- `initial_contract_report.json`
- `initial_system_effectiveness.json`
- `trajectory.jsonl`
- `selection.json`
- `run_manifest.json`
- `run_state.json`

`selection.json` points to the best eligible checkpoint; it never silently
copies or promotes model weights. Checkpoint, predictions, and metrics hashes
are bound together and rechecked after analysis. Every completed attempt is
revalidated again immediately before final checkpoint selection.
Resuming a finished run also recomputes the selection from its revalidated
attempts and reconciles root-level state, totals, selection, and manifest before
returning it.

## Run

From `backend/`:

```bash
uv run python -m app.scripts.run_extractor_data_factory \
  ../experiments/structured_extractor_autoresearch/profile.example.yaml \
  --validate-only --json
```

After replacing the smoke fixtures, pinned model revision, and five command
adapters:

```bash
uv run python -m app.scripts.run_extractor_data_factory \
  ../experiments/structured_extractor_autoresearch/profile.yaml \
  --out reports/autoresearch/structured_extractor/run_001 --json
```

The output directory must be new. This prevents an interrupted or later run
from overwriting an earlier audit trail.

If the process is interrupted, resume against the same frozen profile and run
directory:

```bash
uv run python -m app.scripts.run_extractor_data_factory \
  ../experiments/structured_extractor_autoresearch/profile.yaml \
  --out reports/autoresearch/structured_extractor/run_001 --resume --json
```

An interrupted attempt is preserved and rejected. Resume continues with the
next attempt only when the active step has its nonce-matched usage record.
Every completed attempt is revalidated against its frozen snapshots, boundary
report, structured contract, checkpoint, predictions, verifier records,
metrics, error analysis, artifact hashes, and usage ledger before it can remain
eligible. Unknown spend or modified history fails closed.

## Required before a real LoRA run

- a human-reviewed extraction train set and separately frozen gold test set;
- an immutable base-model revision;
- an immutable adapter runtime artifact (wheel or container) covering imported
  helpers and dependency versions;
- one LoRA trainer that honors the remaining time/token/cost budget;
- reviewed generation, LoRA, inference, deterministic verifier, and
  error-analysis adapters;
- compute/GPU capacity and any model-registry credentials used by those
  external commands.
