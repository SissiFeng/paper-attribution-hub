# Domain Adapter Gold Annotation Guide

## Goal

The gold set measures whether each retained paper-knowledge field is explicitly
supported by the paper. It does not assess paper attribution, institutions,
author identity, scientific novelty, or whether an experiment is advisable.

Review the source Markdown, not only the teacher-generated candidate. Do not add
common knowledge or infer an omitted condition. A value may be normalized, but
it must resolve to one sentence or two adjacent sentences in the source.

## Files

- `gold_protocols.jsonl` defines review completeness for one Protocol Unit.
- `gold_entities.jsonl` contains positive, pending, or rejected field
  annotations.
- `candidate_claims.jsonl` is immutable model output used for scoring.
- `evidence_dependencies.jsonl` contains one field-level provenance annotation
  for every candidate claim.
- `schemas/*.schema.json` defines the machine-readable record contracts.

Queue generation sets every record to `pending`. It is not a gold set until a
human reviewer changes statuses and completes the relevant protocol scope.
`review_batch_001.json` identifies the first deterministic review slice. Edit
the matching rows in the canonical protocol and entity files; the batch file is
selection metadata, not a second copy of the annotations.

## Field evidence dependency labels

Review three labels independently. Do not collapse them into a single trust
score.

### Origin

- `author_reported_primary_experiment`: the paper presents the field as part of
  its own experiment or computation. This label does not identify which author
  performed the work.
- `cited_method`: the paper explicitly imports or follows another published
  method.
- `secondary_summary`: a review, perspective, or workflow paper summarizes an
  experiment reported elsewhere.
- `unknown`: the text does not establish origin.

### Support

- `exact`: the field surface value occurs literally in a direct evidence span.
- `deterministically_aligned`: only deterministic presentation normalization is
  needed, such as whitespace, Unicode dash, superscript, `℃`/`°C`, or unit
  spacing.
- `explicitly_derived`: the field follows from cited input fields through a
  recorded expression. A derivation must include a rule ID, expression, input
  dependency IDs, and assumptions.
- `unsupported`: the available source spans and declared derivation do not
  support the field.

### Modification

- `none`: the paper presents a primary procedure and does not import a cited
  method.
- `explicitly_modified`: the text says that a cited or prior method was adapted
  or modified.
- `unspecified`: the procedure is cited or secondary, but the modification
  relationship is not explicit.

`proposed_labels` are deterministic review aids. They never become gold by
themselves. A reviewer copies or corrects them into `reviewed_labels`, records a
reviewer ID, and changes `review_status` to `reviewed`. A protocol cannot be
marked annotation-complete while any dependency row in its scope is pending.

For derived fields, `depends_on_dependency_ids` forms the field-level dependency
graph. Do not encode an unreported scientific assumption as a direct evidence
span. Put it in `derivation.assumptions`, and reject the field when that
assumption is not allowed by the benchmark policy.

## Protocol review

For each Protocol Unit:

1. Read every referenced source chunk.
2. Correct the protocol boundary if unrelated procedures were merged or one
   procedure was split incorrectly.
3. Review all candidate fields and add any explicitly reported fields the
   extractor missed.
4. Set `review_status` to `reviewed`.
5. Set `annotation_complete` to `true` only after the entire source scope has
   been checked for both false positives and false negatives.

Leave `annotation_complete` false when only candidate validity was checked.
Recall cannot be calculated from candidate-only review.

## Entity review

Use these entity types only: `material`, `instrument`, `software`, `step`,
`characterization`, `result`, and `caveat`. Institutions are excluded. Supplier
and instrument-manufacturer fields are allowed when the experimental text states
them.

For each field:

- Set `review_status` to `reviewed` when the field is a positive gold fact.
- Set it to `rejected` when the candidate is unsupported; rejected rows remain
  in the file for audit but do not become positive gold facts.
- Keep `source_value` as the paper's surface form.
- Use `normalized_value` only for deterministic equivalence such as Unicode
  dashes, superscripts, temperature symbols, unit spacing, or an approved
  controlled synonym. Do not place inferred values there.
- Set `evidence_chunk_id`, `evidence_quote`, `char_start`, and `char_end` to the
  exact original Markdown span.
- Add a new reviewed row for every missed positive field found during complete
  review.

One continuous span is preferred. Two adjacent sentences may be represented as
one continuous span. Do not join non-adjacent statements or combine a value from
one section with a citation from another.

## Decision examples

- `500 ℃` in the source and `500 °C` in a candidate: positive after
  normalization; preserve `500 ℃` as the source value.
- A purity appears elsewhere in the paper but not in the cited protocol span:
  reject the candidate unless the protocol evidence is deliberately expanded to
  the supporting adjacent source.
- A model name is known from the instrument family but absent from the paper:
  reject it.
- A software version is not reported: do not infer the current version.
- An author warns that a parameter is critical: annotate a caveat only when the
  warning is explicit.

## Quality control

Use a second reviewer for ambiguous protocol boundaries and a small overlap
sample. Resolve disagreements before freezing the evaluation set. Keep training
and evaluation papers disjoint, and do not tune extraction prompts against the
frozen evaluation annotations.

## Multi-model comparison boundary

The package-local queue is useful for reviewing one teacher, but it is expanded
from that teacher's retained Protocol Units. It must not be reused as the sole
recall reference for Kimi-versus-Opus-versus-Sol comparisons: candidate-driven
review can anchor protocol boundaries, and model-specific `protocol_id` values
are not shared identities.

The cross-model benchmark therefore requires a separate source-first gold set.
Annotators receive frozen paper/chunk scopes without a candidate-model identity,
record all supported fields and spans, and mark the scope complete only after
checking omissions. Every model is scored against that same artifact by paper,
chunk, field, normalized value, and evidence span. The benchmark report keeps
scientific ranking disabled until this shared artifact is complete.
