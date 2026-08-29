# Domain Adapter Packages

The Domain Adaptation subsystem is separate from paper attribution. It reads
the same imported S3 Markdown source, but its source projection does not include
classification labels, propositions, reviews, authors, affiliations, or
institution records.

## Package layout

```text
oer-electrocatalysis/0.2.1-pre-review/
├── manifest.json
├── source/selection_manifest.json
├── corpus/continued_pretraining.jsonl
├── knowledge/paper_records.jsonl
├── knowledge/protocols.jsonl
├── tasks/sft/train.jsonl
├── tasks/evaluation/eval.jsonl
├── reports/quality_report.json
├── reports/teacher_field_audit.jsonl
└── gold/                         # created by the review-queue command
    ├── candidate_claims.jsonl
    ├── evidence_dependencies.jsonl
    ├── gold_protocols.jsonl
    ├── gold_entities.jsonl
    └── schemas/
```

- `corpus` contains exact-deduplicated, non-boilerplate scientific chunks.
- `knowledge` contains Protocol Units with materials, instruments, software,
  ordered steps, characterization, results, caveats, relations, and exact
  evidence spans. Each unit records whether the source is a primary or secondary
  report.
- `tasks` contains extractive instruction and evaluation records. The pilot
  does not generate experimental advice, and automatic tasks are generated only
  from primary reports. Task schema v0.3 embeds the exact evidence context and
  a value-free JSON shape so a student is never trained to answer without source
  text or an explicit output contract.
- `reports` records exclusions, duplicates, every repaired or rejected teacher
  field, rejection-reason distributions, teacher token usage, and the package
  claims boundary.
- `gold` is a human-review workspace. Queue generation never labels a teacher
  claim as reviewed and refuses to overwrite existing annotations.
- `evidence_dependencies.jsonl` records field-level origin, support, and
  modification proposals plus direct spans and optional derivation inputs.

## OER pilot

The fixed selection contains 20 papers in three auditable tiers:

- primary OER research;
- OER workflow case studies;
- OER reviews used partly as abstention and false-positive controls.

The package scope is OER electrocatalysis. Electrodeposition is a protocol
subtype only when the source supports it.

Build the deterministic baseline from the repository root:

```bash
cd backend
python -m app.scripts.build_domain_adapter_package --extractor heuristic
```

Build with an Amazon Bedrock teacher after AWS SSO authentication:

```bash
cd backend
aws sso login --profile pas-sdl0-dev
python -m app.scripts.build_domain_adapter_package \
  --extractor bedrock \
  --aws-profile pas-sdl0-dev \
  --model-id us.anthropic.claude-sonnet-4-6
```

Bedrock uses IAM/SSO credentials and does not require a model API key. Every
teacher field must carry a quote that can be deterministically aligned to one
supplied chunk. Exact matches are preferred; whitespace, line-break
hyphenation, Unicode dash/superscript/temperature-symbol, and unit-spacing
differences are repaired while retaining the exact original source substring
and offsets. Unsupported fields fail closed and receive a stable rejection
reason in `reports/teacher_field_audit.jsonl`.

The S3 source region and teacher inference region are independent. For example,
Kimi K2.5 is available through Bedrock in `us-east-1`, while the source Markdown
remains in the `ca-central-1` bucket:

```bash
python -m app.scripts.build_domain_adapter_package \
  --extractor bedrock \
  --aws-profile pas-sdl0-dev \
  --aws-region ca-central-1 \
  --teacher-region us-east-1 \
  --model-id moonshotai.kimi-k2.5 \
  --bedrock-read-timeout 300 \
  --bedrock-max-attempts 4 \
  --bedrock-max-output-tokens 14000
```

Long teacher calls are checkpointed per paper. A resumed build reuses only
cache records matching the model, prompt version, paper ID, and source chunk
hashes. The cache also restores field-audit counters and Bedrock usage metadata.
Package artifacts are still written deterministically after all papers have
completed.

That configuration sends selected paper text to the configured teacher region;
it should be chosen only when the project's data-residency policy permits it.

The default source is the original S3 `document.md` object. The builder resolves
each selected paper through its Zotero document manifest, verifies the Markdown
SHA-256, restores heading and paragraph boundaries, and records the exact S3
manifest key, Markdown key, and checksum. `--source imported-api` exists only as
a local fallback when AWS authentication is unavailable.

## Human gold set

Create pending review queues from a completed package:

```bash
cd backend
python -m app.scripts.prepare_domain_gold_set \
  --package ../outputs/domain-adapters/oer-electrocatalysis/0.2.1-pre-review
```

Follow `domain_adapter_gold_annotation.md`. A protocol contributes to metrics
only when `review_status` is `reviewed` and `annotation_complete` is `true`.
Pending entity or evidence-dependency rows inside such a scope are an error.
After review, calculate field precision, recall, per-entity metrics, and exact
span alignment:

```bash
python -m app.scripts.evaluate_domain_gold_set \
  --package ../outputs/domain-adapters/oer-electrocatalysis/0.2.1-pre-review
```

The result is written to `reports/gold_score.json`. Before any human review,
precision and recall are intentionally unavailable rather than inferred from
teacher-validator acceptance.

For a package whose gold queue predates the dependency schema, add the new
non-overwriting annotation layer with:

```bash
python -m app.scripts.prepare_evidence_dependency_annotations \
  --package ../outputs/domain-adapters/oer-electrocatalysis/0.2.1-pre-review
```

The `0.2.1-pre-review` package currently contains 481 pending dependency
annotations: 228 proposed primary author-reported fields, 41 cited-method
fields, and 212 secondary-summary fields. Support is exact for 476 fields and
deterministically aligned for five. These counts describe deterministic
proposals, not reviewed scientific accuracy.

## Cross-model teacher benchmark

Teacher selection is a benchmark, not a hard-coded Kimi dependency. The frozen
matrix lives in `data/domain_adapters/oer_teacher_benchmark.json` and currently
includes Kimi K2.5, Claude Opus and Sonnet, GPT-5.6 Sol, DeepSeek V3.2, Qwen3
Next 80B, and GLM-5 candidates exposed by Amazon Bedrock.

First record account access and minimal JSON behavior:

```bash
cd backend
python -m app.scripts.benchmark_domain_teachers \
  --spec ../data/domain_adapters/oer_teacher_benchmark.json \
  preflight \
  --aws-profile pas-sdl0-dev \
  --output ../outputs/domain-adapters/oer-electrocatalysis/model-benchmark/preflight.json
```

Preflight is not an extraction-quality result. A model can appear in the
Bedrock catalog while remaining unavailable to the current account. Access
denials are retained as benchmark outcomes and are never silently replaced by
an older model.

For a bounded first pass, build exactly the four frozen evaluation papers. Use
the previously recorded source-selection manifest so a temporary metadata API
failure cannot alter or block the benchmark:

```bash
python -m app.scripts.build_domain_adapter_package \
  --extractor bedrock \
  --source s3 \
  --source-metadata-manifest \
    ../outputs/domain-adapters/oer-electrocatalysis/0.2.1-pre-review/source/selection_manifest.json \
  --task-split evaluation \
  --aws-profile pas-sdl0-dev \
  --teacher-region us-east-1 \
  --model-id us.anthropic.claude-opus-4-6-v1 \
  --package-version benchmark-eval4-claude-opus-4-6 \
  --output ../outputs/domain-adapters/oer-electrocatalysis/model-benchmark/packages/claude-opus-4-6
```

Repeat the command with one isolated output directory per model. Then create a
machine-readable comparison by passing repeated `--package ALIAS=PATH` values
to `app.scripts.benchmark_domain_teachers compare`.

The comparator fails when source-selection hashes, prompt versions, or
inference settings differ. It reports coverage, evidence-field acceptance,
rejection reasons, response failures, token use, and latency. It does not rank
scientific accuracy from validator acceptance or package-local gold files.
Scientific ranking is enabled only by a shared, source-first human gold set
whose `candidate_model` is null and whose annotations cover every candidate.

### 2026-08-27 evaluation-slice run

Six models completed the same four-paper, prompt-v0.2, temperature-zero run on
real S3 Markdown and Bedrock inference. The deterministic cache rebuild returned
`changed_files = 0` for every package.

| Model | Papers with protocols | Protocols | Accepted / proposed fields | Response failures | Output tokens | Total latency (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Kimi K2.5 | 4/4 | 15 | 150 / 343 | 0 | 21,890 | 325.576 |
| Claude Opus 4.6 | 2/4 | 10 | 73 / 200 | 1 salvaged | 17,244 | 192.795 |
| Claude Sonnet 4.6 | 3/4 | 12 | 92 / 284 | 1 salvaged | 26,095 | 265.855 |
| DeepSeek V3.2 | 2/4 | 2 | 65 / 92 | 0 | 5,738 | 71.709 |
| Qwen3 Next 80B | 1/4 | 1 | 55 / 145 | 1 unsalvaged | 25,884 | 391.296 |
| GLM-5 | 1/4 | 9 | 82 / 173 | 0 | 9,176 | 189.080 |

These are operational measurements, not a quality leaderboard. For example,
DeepSeek's high validator acceptance rate can reflect precision or severe
under-extraction; only shared gold recall can distinguish them. Claude Opus 5
and GPT-5.6 Sol were visible in the Bedrock catalog but returned account-level
`AccessDeniedException`, so the required final matrix remains incomplete.

The four-paper slice is not four interchangeable positive examples. It contains
two primary OER papers, one workflow case study, and one review control. Kimi,
Claude Opus 4.6, Claude Sonnet 4.6, and DeepSeek V3.2 retained protocols for
both primary papers. Qwen3 Next 80B and GLM-5 retained protocols for one of two.
Most other missing-paper outcomes were explicit `protocols: []` abstentions on
the case-study or review control. Qwen also had one unrecoverable max-token
response on a primary paper. `comparison.json` reports coverage by selection
tier and per-paper outcomes instead of treating raw 4/4 coverage as recall.

## Training boundary

The package is suitable as input to separate downstream jobs:

1. continued pretraining on the cleaned corpus when token volume justifies it;
2. RAG and structured grounding on Protocol Units;
3. SFT and evaluation on the Task Suite.

Retokenization is an optional downstream experiment, not an ingest step. It
must be benchmarked against the base tokenizer before changing model vocabulary.
Trained LoRA or other weight artifacts are versioned separately and are not
assumed to compose safely merely because their source data packages compose.

## Post-training escalation policy

Post-training is considered only after a paper-held-out evaluation separates
source/segmentation failures from model failures. The evidence validator remains
a hard constraint at every stage; training must not convert unsupported claims
into accepted knowledge.

Use the following escalation order:

1. Fix Markdown cleaning, section boundaries, protocol grouping, retrieval, or
   schema validation when the required evidence was not presented correctly.
2. Improve the teacher prompt or model when the evidence was present but teacher
   extraction accuracy, completeness, or abstention was inadequate.
3. Run conventional SFT on reviewed Task Suite records when a deployable student
   has not yet learned the extraction contract.
4. Use on-policy sequence distillation when the student performs well on static
   tasks but makes systematic errors on its own generated trajectories. The
   student generates candidate JSON; a stronger teacher reviews it against the
   source evidence; accepted corrections and hard negatives are mixed with the
   reviewed static suite for SFT, preference optimization, or rejection sampling.
5. Use token-level generalized knowledge distillation or reverse-KL objectives
   only when the training stack has access to teacher token probabilities. A
   black-box Bedrock teacher does not expose the logits required for a faithful
   implementation of those objectives.

Promotion requires improvement on a frozen, paper-disjoint evaluation set for
field accuracy, protocol completeness, exact-evidence support, and abstention on
secondary or non-protocol text. Teacher-generated training records and teacher-
scored evaluation records must not be the only evidence of improvement.

### Local mechanism pilot

A three-seed Apple-MPS pilot used `SmolLM2-360M-Instruct`, 12 seed-SFT tasks,
six task-disjoint rollout tasks, and nine paper-held-out evaluation tasks per
seed. Static SFT raised JSON validity from 0% to 100%. Seed-replay on-policy hard
example training reached mean field F1 0.3164 versus 0.3102 for an equal-compute
continued-SFT control, but evidence-grounded leaf rate fell from 0.6676 to
0.6503. The on-policy variant therefore failed the promotion rule.

This result is a mechanism test on heuristic targets, not a scientific quality
claim. The experiment must be repeated on the S3 + teacher package before any
model adapter is retained.

### Real S3 and Bedrock Kimi pilot

The 20-paper pilot was run against the original S3 Markdown objects and the
Bedrock `moonshotai.kimi-k2.5` model in `us-east-1`. The completed package has
284 cleaned corpus records, 64 grounded Protocol Units across 17 papers, and 51
primary-report tasks. Retained knowledge contains 75 materials, 35 instruments,
18 software uses, 163 ordered steps, 14 characterization records, 11 reported
results, 19 caveats, 335 relations, and 241 exact evidence spans.

The validator rejected 501 teacher fields or claims that could not satisfy the
exact evidence contract. No complete Protocol Unit was rejected, and rejected
fields were not written to the knowledge or task artifacts. This is a useful
fail-closed result, but the retained package still requires human sampling before
scientific-quality claims or production training.

The build was rerun entirely from per-paper checkpoints and produced
`changed_files = 0`, confirming deterministic package output without additional
teacher calls.

### Audit-enabled teacher rerun

Package `0.2.1-pre-review` reran the same 20 S3 Markdown papers with Kimi and
prompt v0.2, then rebuilt the structured layer from cached raw responses using
field mapper v0.2. The package contains 45 Protocol Units (17 primary and 28
secondary), 78 materials, 44 instruments, 14 software uses, 164 exact-evidence
steps, 13 characterization records, five reported results, 12 caveats, 330
relations, 227 evidence spans, and 51 tasks.

The teacher proposed 992 auditable fields. The mapper accepted 315 literal or
deterministically normalized fields and rejected 677 teacher fields: 514 were
over-generalized relative to the cited span, 129 cited spans could not be found,
30 values occurred elsewhere rather than in the cited span, and four values
were schema-invalid. Two whitespace-only citations were repaired. A separate
response-level failure occurred when one secondary review hit the 14,000-token
output limit; nine complete protocol objects were conservatively salvaged and
the incomplete tail was discarded.

Summarized step actions are rejected as teacher fields but do not erase a valid
procedure. When their citation aligns exactly, the original evidence quote is
stored as the canonical step action. This restored 164 grounded steps without
accepting the teacher paraphrase.

The run used 95,690 input and 76,010 output tokens across 20 Bedrock calls. A
raw-cache rebuild produced `changed_files = 0`. The pending gold workspace has
481 candidate claims across 45 protocols. Review batch 001 selects all 17
primary-report protocols plus three small secondary controls: 20 protocols and
275 candidate claims. Since no human annotation is complete, gold precision,
recall, and span-alignment metrics remain `null` by design.

### Real-teacher post-training pilot

The paper-disjoint SmolLM2 experiment was repeated on the Kimi-derived Task
Suite with seeds 23, 41, and 59. Adding the value-free Task Suite v0.3 response
shape changed mean base field F1 from 0 to 0.0503 and mean static-SFT field F1
to 0.2050. Static SFT reached mean JSON validity 0.963 and grounded-leaf rate
0.753.

The equal-compute matched continued-SFT control reached mean field F1 0.2000,
JSON validity 1.0, and grounding 0.7901. Student-error-conditioned on-policy
training reached mean field F1 0.1912, JSON validity 1.0, and grounding 0.7716.
It was promoted in zero of three seeds and is therefore not retained. These
metrics measure agreement with Kimi-derived targets, not independent human
scientific correctness.
