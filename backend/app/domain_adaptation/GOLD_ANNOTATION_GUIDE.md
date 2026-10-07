# Domain Adaptation Human-Gold Annotation Guide

## Purpose

This guide defines the first human-gold review process for evidence-bound
scientific domain packages. The reviewer decides only what the cited source
supports. The reviewer must not add scientific common sense, infer missing
conditions, or copy a model proposal without checking the original source span.

The initial OER package is a pilot for this process. The same rules apply to
later domain and capability packages.

## Files and Trust Boundaries

| File | Role | Gold status |
| --- | --- | --- |
| `gold/candidate_claims.jsonl` | Extractor-proposed field values | Never gold |
| `gold/evidence_dependencies.jsonl` | Deterministic dependency-label proposals | Gold only after review |
| `gold/gold_entities.jsonl` | Human field annotation queue | Gold only when reviewed |
| `gold/gold_protocols.jsonl` | Protocol-scope completion ledger | Controls scoring scope |
| `rag/candidate_questions.jsonl` | Proposed RAG questions and answers | Never gold |
| `gold/rag_questions.jsonl` | Human RAG annotation queue | Gold only when reviewed and complete |
| `rag/baseline_predictions.jsonl` | Deterministic system output | Never gold |

Proposed values may accelerate review, but they are not evidence. The source
Markdown and exact Evidence Spans are authoritative.

## General Rules

1. Review only the cited sentence or an explicitly recorded contiguous
   two-sentence span.
2. Accept a field only when the source directly supports the complete value.
3. Do not add an institution entity. Material suppliers and instrument
   manufacturers remain valid scientific attributes.
4. Do not fill a missing purity, model, version, temperature, time, unit, or
   experimental role from common knowledge.
5. Do not combine values from unrelated sentences unless the field is recorded
   as a derived dependency with explicit input Evidence Spans and a derivation
   rule.
6. Preserve the source surface form. Put normalization in the normalized field,
   never in the source field.
7. A review or case-study description is secondary evidence even when it
   describes a primary experiment in detail.
8. "Following a reported method" is cited-method evidence. It is not evidence
   that the current paper executed every condition in the cited method.

## Allowed Normalization

Normalization may correct presentation without adding information:

- Unicode and ASCII dash variants;
- collapsed whitespace and line wrapping;
- soft hyphen removal;
- equivalent spacing around units, such as `10 mV s−1` and `10 mV s-1`;
- case folding for comparison;
- an explicitly documented unit conversion whose inputs and formula are stored
  as evidence dependencies.

Normalization may not:

- infer an unstated unit;
- replace a trade name with an assumed chemical composition;
- resolve an ambiguous acronym without nearby source support;
- infer a reference-electrode conversion condition;
- turn a qualitative statement into a numeric threshold.

## Entity and Field Review

For each `gold_entities.jsonl` row:

1. Open the source paper and locate `evidence_chunk_id`.
2. Confirm that `evidence_quote` is present at `char_start:char_end`.
3. Decide whether the quote directly supports `source_value` for the specified
   `entity_type` and `field_name`.
4. Set:
   - `review_status: reviewed` when the field is supported;
   - `review_status: rejected` when it is unsupported or assigned to the wrong
     field;
   - leave `pending` when adjudication is required.
5. Correct `normalized_value` only within the allowed normalization rules.
6. Record a short note for rejections, ambiguity, or non-trivial normalization.

Do not mark a protocol `annotation_complete: true` while any entity or evidence
dependency in that protocol remains pending.

## Evidence Dependency Review

Review the three labels independently:

### Origin

- `author_reported_primary_experiment`: the current primary paper directly
  reports its experiment or computation;
- `cited_method`: the text delegates a method to another source;
- `secondary_summary`: a review or workflow paper summarizes another study;
- `unclear`: the origin cannot be established from the available text.

This label does not identify which individual author performed the work.

### Support

- `exact`: the field value is a literal substring of the Evidence Span;
- `deterministically_aligned`: only allowed presentation normalization was
  needed;
- `derived`: the value follows from recorded inputs and an explicit rule;
- `unsupported`: the available spans do not support the value.

### Modification

- `none`: the current paper reports the method without a modification cue;
- `explicitly_modified`: the paper states that it modified a cited method;
- `unspecified`: the text does not establish whether a modification occurred.

## RAG Question Review

For each `gold/rag_questions.jsonl` row:

1. Read the question without looking at the proposed answer first.
2. Decide whether the scoped paper or papers contain enough evidence to answer.
3. If answerable:
   - set `expected_behavior: answer`;
   - enter the minimum complete `accepted_answer_items`;
   - enter the exact `accepted_evidence_ids`;
   - enter every Scientific Semantic Chunk required to retrieve the answer;
   - set `review_status: reviewed` and `annotation_complete: true` only after all
     three lists are complete.
4. If the requested detail is absent or cannot be resolved:
   - set `expected_behavior: abstain`;
   - leave answer and evidence lists empty;
   - explain the missing information in `notes`;
   - set reviewed and complete.
5. Reject a generated question when it is malformed, leaks its answer, depends
   on unstated common knowledge, or has an invalid scientific scope.

The proposed answer may be copied only after independent source verification.

## Minimum Pilot Review

The first OER review should include:

- 20 complete Protocol Units across different experiment types;
- at least 100 field claims, including materials, instruments, software,
  atomic step verbs, targets, parameters, characterization, results, and caveats;
- 30–50 RAG questions;
- at least five answerable questions per major available question type;
- at least five genuine abstention questions;
- primary and secondary evidence controls.

Do not promote the package to reviewed status until the selected protocol
scopes contain no pending field or dependency annotations.

## Adjudication

Use a second reviewer for:

- derived values;
- primary versus cited-method disagreements;
- protocol boundaries spanning multiple sections;
- reference-electrode or unit conversions;
- cross-paper comparison questions;
- any item marked ambiguous by the first reviewer.

Record the final reviewer identity and a short adjudication note. Do not erase
the original disagreement outside the versioned review history.

## Evaluation

Run:

```bash
python -m app.scripts.evaluate_domain_gold_set --package <package>
python -m app.scripts.evaluate_domain_rag --package <package>
```

Field metrics include precision, recall, and span alignment. RAG metrics keep
answer correctness, citation validity, evidence recovery, retrieval coverage,
reciprocal rank, and abstention accuracy separate.

No metric may include pending, rejected, or annotation-incomplete questions.
No model-training or promotion decision may treat proposal counts as gold-set
performance.
