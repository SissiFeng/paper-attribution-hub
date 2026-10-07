# Domain Adaptation Context

## Purpose

This bounded context turns selected scientific full text into versioned domain
packages for continued pretraining, grounded retrieval, supervised fine-tuning,
and evaluation. It shares source documents with the paper-attribution system but
does not consume attribution labels, propositions, reviews, authors, or
institution records.

## Canonical Terms

- **Domain Adaptation Package**: A versioned directory containing a Cleaned
  Corpus, Structured Knowledge, a Task Suite, source selection, and quality
  evidence. It is data, not a trained model weight.
- **Source Paper**: A deliberately narrow projection of bibliographic identity
  and Markdown-derived chunks. Attribution and affiliation fields are absent.
- **Scientific Semantic Chunk**: A structure-first retrieval and corpus unit
  built from one or more adjacent source blocks. It has a stable ID, section
  parent, one or more scientific roles, and exact source-segment offsets and
  hashes. A character limit is only an oversized-block safety fallback.
- **Protocol Unit**: The principal knowledge and RAG object. It represents one
  experimental or computational procedure and its materials, instruments,
  software, steps, characterization, results, caveats, relations, and evidence.
- **Atomic Protocol Step**: A step represented as a short evidence-surface
  `verb`, one or more evidence-surface `targets`, and atomic `params`. Its
  consensus identity is normalized `(verb, primary target)`. A complete source
  sentence is evidence, never a step value or identity.
- **Evidence Span**: An exact quote with paper ID, chunk ID, character offsets,
  and source hash. Unsupported spans fail closed.
- **Evidence-Bound Field**: A structured field whose `evidence_ids` resolve to
  exact Evidence Spans in the same Protocol Unit.
- **Field Evidence Dependency**: The auditable connection from one field to
  direct spans or explicit derivation inputs. Origin, support, and modification
  are orthogonal labels; deterministic proposals remain pending until reviewed.
- **Evidence Scope**: `primary_report` means the protocol is extracted from a
  primary research paper in the selected domain. `secondary_report` means it
  comes from a review or workflow case and must not be treated as the original
  experimental report.
- **Teacher Extraction**: Structured extraction performed through an explicit
  model adapter. The package records provider, model, and prompt version.
- **Model Field Proposal**: One teacher's evidence-valid structured field,
  preserved with model identity, source occurrence, field path, value, and
  exact Evidence Span. Proposal counts measure extraction coverage, not truth.
- **Source-Grounded Consensus Silver**: A field value proposed by at least two
  independent model families for overlapping evidence occurrences. It remains
  silver rather than human gold and cannot establish scientific recall.
- **Claim Perturbation**: A claim-level counterfactual that deletes a proposed
  value or changes its numeric surface form in the source quote, then asks each
  supporting teacher to re-read only the mutated evidence. Batch responses are
  persisted and can be replayed without another model call. Perturbations
  require a unique quote-relative value span; ambiguous repeated values abstain.
- **Memory-Evidence Experiment**: A pre-registered comparison of numeric
  substitution-following before and after a documented model knowledge cutoff,
  stratified by citation count. Publication date is an exposure proxy, not proof
  of training-set membership.
- **Tier A Silver**: Source-Grounded Consensus Silver for which every supporting
  model passed all applicable Claim Perturbations. It is eligible for a silver
  training queue, not automatically equivalent to reviewed knowledge.
- **Tier B Dispute**: A proposal slot with a supported contradiction,
  insufficient independent families, non-overlapping evidence, an unverified
  perturbation, or a failed perturbation. Majority vote never overrides a
  supported contradiction.
- **Tier C Abstention**: A slot without deterministically valid source evidence.
- **Heuristic Baseline**: Deterministic high-precision extraction used for
  regression comparison. It must never be presented as teacher output.
- **Model Adapter Artifact**: A separately trained LoRA or other model weight.
  Model Adapter Artifacts are not assumed to be safely composable merely because
  their source Domain Adaptation Packages are composable.
- **Experimental Evidence Package**: An immutable, content-addressed release of
  completed, failed, or invalid experiment runs. It preserves measurements,
  conditions, uncertainty, and source provenance without interpreting causality.
- **Claim Update Candidate**: A proposed `supports`, `refutes`, `refines`, or
  `invalidates` relation between experimental evidence and an existing claim.
  It is an interpretation awaiting validation, not a measurement or promotion.
- **Belief Update Utility**: Observable agreement between an expected and actual
  `revise`, `retain`, or `abstain` action after new experimental evidence. It
  does not represent access to a model's hidden chain of thought.
- **RAG Question Candidate**: A deterministic review aid generated from a
  Protocol Unit. Proposed answers never count as human gold.
- **RAG Gold Question**: A source-first question whose answer items, Evidence
  Spans, Scientific Semantic Chunks, and answer/abstain behavior have been
  explicitly reviewed and marked annotation-complete.
- **Package DAG**: The exact-version dependency graph among `scientific_core`,
  `domain`, reusable `capability`, and immutable `evidence` packages. Resolution
  fails on missing nodes, dependency-kind mismatches, duplicate coordinates, or
  cycles.
- **Promotion Candidate**: An auditable proposal to move reviewed records into
  shared knowledge, scientific-core tasks, or a new scientific-base weight
  release. Eligibility never applies or approves a promotion automatically.
- **Scientific Utility Observation**: One answer scored against a
  content-addressed external source such as structured supplementary data, a
  curated database, or an experimental measurement. Model consensus is not an
  allowed truth-source type.
- **Cross-Domain Transfer Comparison**: A paired target-domain evaluation of a
  general baseline and the same system with another domain adapter. Both
  directed domain pairs are required so positive transfer cannot hide
  asymmetric interference.
- **NMI Readiness Report**: A fail-closed engineering gap report over declared
  publication-evidence thresholds. Passing it does not establish scientific
  validity or publication acceptance.

## Boundaries

- Institution entities are out of scope. Material suppliers and instrument
  manufacturers remain valid protocol attributes.
- Reference lists, acknowledgements, author contributions, and publisher
  boilerplate are excluded from package layers.
- Task Suite outputs are extractive. Experimental recommendations require a
  separate reviewed task policy and are not generated by this pilot.
- Model competition is a precision-first silver-label mechanism, not a
  replacement for external truth. It can promote stable supported claims and
  explain rejection, but it cannot measure omissions shared by all teachers.
- Independent agreement is counted by model family, not by repeated runs or
  aliases from one provider family.
- Repeated entities in one chunk are separate source occurrences unless their
  evidence intervals overlap. A result for one occurrence cannot promote a
  different occurrence with the same normalized value.
- Counterfactual evaluation never sends the original or expected answer value
  to the model. Returned values must be verbatim substrings of the mutated
  source, and missing, malformed, or unsupported outputs fail closed.
- Numeric replacement for steps is restricted to `param:*`. `verb`, `target`,
  `notes`, and legacy whole-sentence `action` fields are never numeric targets.
- Legacy packages whose steps lack `verb`, `targets`, and `params` are excluded
  from step consensus, task generation, gold queues, and protocol-step RAG.
  Their non-step fields may be recompiled, but legacy step results are retained
  only as a contamination audit.
- Scientific teacher ranking remains blocked without a shared external truth
  source. Field acceptance rate, pairwise agreement, and perturbation pass rate
  are reported separately and must not be relabeled as accuracy.
- Only `primary_report` Protocol Units are eligible for automatic Task Suite
  generation. Secondary reports remain available for retrieval and comparison.
- The first pilot domain is `oer-electrocatalysis`; the second bounded pilot is
  `battery-electrolyte-optimization`. Each package declares its own evidence
  scope and teacher context terms while sharing the same source-provenance,
  protocol, task, and evaluation contracts.
- `author_reported_primary_experiment` describes evidence origin. It does not
  identify which author physically performed an experiment.
- Scientific Semantic Chunks are domain-neutral shared infrastructure. Domain
  packages may tune their policy and add reviewed domain labels, but they must
  not replace exact source provenance with model-generated summaries.
- Domain packages may eventually depend on multiple shared scientific or
  capability packages. Package composition does not imply that model weight
  adapters can be merged without cross-domain and forgetting evaluation.
- RAG reports score answer item precision/recall/F1, citation validity,
  evidence precision/recall, retrieval recall, reciprocal rank, and abstention
  separately. Metrics remain null while all questions are pending review.
- RAG review sampling covers primary and secondary reports with an explicit
  evidence-scope filter. It prioritizes paper coverage before balancing question
  types. Semantic chunk roles are retrieval preferences, not hard exclusions;
  evidence scope remains a hard structured filter.
- Shared-knowledge promotion requires reviewed provenance and measured RAG
  utility. Scientific-skill promotion additionally requires support from at
  least two domains. Weight consolidation additionally requires a hashed
  adapter artifact, replay evaluation, general-capability retention, and no
  domain regression beyond the policy tolerance.

## Review Workflow

After building a package with Scientific Semantic Chunks:

```bash
python -m app.scripts.prepare_domain_rag_eval --package <package> --limit 50
python -m app.scripts.evaluate_domain_rag --package <package>
```

The preparation command writes candidate proposals, a separate empty human-gold
queue, and deterministic BM25 plus structured-KB baseline predictions. The
evaluation command uses only reviewed, annotation-complete gold questions.
Reviewers must follow `app/domain_adaptation/GOLD_ANNOTATION_GUIDE.md`.

## Multi-Teacher Silver Workflow

Build model-specific packages from the same frozen paper selection, prompt, and
inference configuration. Then compile source-grounded consensus and bounded
counterfactual cases without overwriting an earlier version:

```bash
python -m app.scripts.build_teacher_consensus \
  --package <alias>=<teacher-package> \
  --package <alias>=<teacher-package> \
  --output <new-consensus-directory>

python -m app.scripts.run_teacher_perturbations \
  --cases <new-consensus-directory>/consensus/perturbation_cases.jsonl \
  --model <alias> \
  --model <alias> \
  --output <new-perturbation-directory>

python -m app.scripts.build_teacher_consensus \
  --package <alias>=<teacher-package> \
  --package <alias>=<teacher-package> \
  --perturbation-results \
    <new-perturbation-directory>/model_results.jsonl \
  --output <new-verified-consensus-directory>
```

`accepted_silver.jsonl` contains Tier A only. Disputed and abstained records
remain first-class artifacts, raw batch responses are retained for audit and
offline replay, and `scientific_ranking` stays ineligible until an independent
truth source is supplied.

## Cross-Domain NMI Evidence Workflow

Build every domain and model condition as an immutable package coordinate. Use
the same externally scored task IDs for each paired ablation and directed
cross-domain transfer comparison. Then build the current gap report:

```bash
python -m app.scripts.build_nmi_study_report \
  --input data/domain_adapters/nmi_study_current.json \
  --output outputs/domain-adapters/nmi-study/readiness.json
```

The input records current evidence rather than intended future work. Missing
utility, perturbation, prompt-robustness, deterministic-rebuild, or transfer
results remain explicit failed gates. Silver consensus cannot populate external
accuracy fields.

## Memory-Evidence Experiment A

Freeze the paper metadata and model cutoff registry before generating the
strata. The cutoff registry fails closed while a model-version cutoff is
unknown; family-level guesses are not accepted.

```bash
python -m app.scripts.prepare_memory_evidence_experiment \
  --experiment-id oer-memory-evidence-v0.1 \
  --domain oer-electrocatalysis \
  --selection-manifest <package>/source/selection_manifest.json \
  --database backend/paper_attribution.db \
  --cutoff-registry data/domain_adapters/oer_experiment_a_model_cutoffs.v0.1.json \
  --output <new-experiment-directory>/input.json

python -m app.scripts.build_memory_evidence_experiment \
  --input <new-experiment-directory>/input.json \
  --output-dir <new-experiment-directory>/design-artifact
```

The default design requires 150–200 primary experimental papers, at least 50
pre-cutoff and 50 post-cutoff papers per model, and a 180-day exclusion buffer.
Year-precision publication dates are treated as intervals. The primary endpoint
is numeric substitution-following on unique atomic value spans; evidence
deletion is the negative-control endpoint.
