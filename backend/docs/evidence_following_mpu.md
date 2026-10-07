# Evidence-following MPU

## Claim under test

The minimum publishable unit tests whether evidence-following is a measurable,
cross-domain-stable model property that is separable from closed-book domain
knowledge. It uses OER electrocatalysis and organic synthesis, with 100 primary
experimental papers and at least 100 exact counterfactual tasks per domain.

The MPU does not train a domain adapter. P2-proc and any procedural-weight
injection are reserved for a later study.

## Five paired conditions

Every exact numeric-replacement task is evaluated on the same model under five
conditions:

1. `closed_book_blind`: domain context without paper identity;
2. `closed_book_identified`: title/DOI without paper text;
3. `fact_injected_probe`: the original fact is supplied as controlled prior
   context;
4. `counterfactual`: only the currently authoritative replacement evidence;
5. `counterfactual_fact_injected`: original fact memory conflicts with the
   currently authoritative replacement evidence.

The exposure probe is `identified_correct - blind_correct`. Evidence-following
requires extracting the replacement and not returning the original value.
Generated prompts keep trusted system instructions separate from the typed,
untrusted scientific payload. Observations are accepted only when their study
ID, prompt ID, and prompt-content hash match the frozen design.

## Confirmatory outputs

- Cross-domain trait: rank correlation of model evidence-following rates across
  the two domains, plus the within-model absolute domain gap.
- Knowledge dissociation: correlations of evidence-following with closed-book
  knowledge and with the exposure probe. A non-significant correlation is not
  accepted as dissociation; both clustered-bootstrap intervals must fall inside
  the preregistered equivalence bound.
- Fact-injection trade-off: paired knowledge gain and evidence-following loss.
A Pareto trade-off is reported only when the knowledge interval is entirely
positive and the evidence-following interval entirely negative. Because this
MPU does not train adapters, this is an inference-time contextual intervention;
it does not establish a penalty caused by parameter updates.

All intervals resample papers within domain, so multiple fields from one paper
are not treated as independent evidence.

## Current state and readiness

The checked-in current cohort contains seven OER primary papers and zero
organic-synthesis papers. It deliberately contains no placeholder tasks. The
existing step-atomic OER perturbation artifact contains 28 numeric replacement
cases. Occurrence-identifiability filtering removes ambiguous repeated fields
and deterministic duplicates, leaving 14 MPU tasks; it does not fill the
missing organic-synthesis cohort. The generated readiness report therefore
fails closed rather than presenting a pilot as a cross-domain result.

Compile the current OER cases, then build the readiness artifact:

```bash
cd backend
.venv/bin/python -m app.scripts.prepare_evidence_following_mpu \
  --input ../data/domain_adapters/evidence_following_mpu_current.json \
  --cases ../outputs/domain-adapters/oer-electrocatalysis/teacher-benchmark-2026-09/consensus-v0.7-step-atomic-migrated/consensus/perturbation_cases.jsonl \
  --output ../outputs/domain-adapters/evidence-following-mpu/current-compiled-study-v0.5.json

.venv/bin/python -m app.scripts.build_evidence_following_mpu \
  --input ../outputs/domain-adapters/evidence-following-mpu/current-compiled-study-v0.5.json \
  --output-dir ../outputs/domain-adapters/evidence-following-mpu/current-compiled-readiness-v0.5
```

After model observations are collected as JSONL, add:

```bash
  --observations /path/to/observations.jsonl
```

Existing `numeric_replacement` cases can be converted with
`compile_mpu_tasks`; evidence-deletion cases are excluded from the primary MPU
endpoint. Every build writes schemas, prompt and score JSONL, a report, and a
content-addressed manifest, and refuses to overwrite an existing artifact.
