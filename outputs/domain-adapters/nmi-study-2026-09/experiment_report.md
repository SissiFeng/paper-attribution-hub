# Cross-Domain Paper Knowledge Adapter: Current NMI Evidence Report

## Claim boundary

This report describes compiler behavior, source-grounded model agreement, and
counterfactual evidence dependence. It does not report scientific precision or
recall because no independent external truth suite has been scored. Consensus
silver is not used as ground truth.

## Domains and real model execution

| Domain | Paper scope | Real teacher execution | Main package result |
| --- | ---: | --- | --- |
| OER electrocatalysis | 20 papers | Kimi K2.5 full package; Kimi, Claude Opus 4.6, and DeepSeek 3.2 on a frozen 4-paper slice | 45 protocols, 227 evidence spans, 51 tasks |
| Battery electrolyte optimization | 10 papers | Kimi K2.5 full package; the same three model families on a frozen 3-paper slice | 37 protocols, 205 evidence spans, 34 tasks after the chunk-coverage ablation |

All teacher calls used Amazon Bedrock in `us-east-1`. Source Markdown was read
from the project S3 bucket in `ca-central-1` through content-addressed document
manifests.

## Chunk-selection ablation

The battery package held the 10 papers, Kimi model, prompt v0.3, inference
configuration, and domain terms constant. Only the minimum deterministic chunk
score changed.

| Metric | Minimum score 4 | Minimum score 2 |
| --- | ---: | ---: |
| Primary-paper coverage | 5 / 6 | 6 / 6 |
| Primary protocols | 12 | 12 |
| Secondary protocols | 29 | 25 |
| Evidence spans | 186 | 205 |
| Tasks | 33 | 34 |
| Proposed fields | 729 | 750 |
| Accepted fields | 203 | 197 |
| Field acceptance rate | 27.85% | 26.27% |
| Input tokens | 38,130 | 40,557 |
| Bedrock latency | 827,407 ms | 848,207 ms |

The lower threshold recovered the previously missed FINALES primary paper, but
did not increase the total primary protocol count and reduced field acceptance.
This is a coverage-cost result, not evidence that the lower threshold is more
scientifically accurate.

## Evidence-scope prompt ablation and model competition

Prompt v0.4 explicitly marks `primary_report` versus `secondary_report`. A
secondary paper must contain at least two ordered actions, or one action with an
explicit quantitative condition, before the teacher may emit a protocol. The
same 3-paper evaluation slice contains two primary papers and one review.

| Model | Protocols | Primary | Secondary | Evidence spans | Proposed fields | Accepted fields | Rejected fields |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Kimi K2.5 | 6 | 6 | 0 | 63 | 219 | 69 | 150 |
| Claude Opus 4.6 | 3 | 3 | 0 | 48 | 148 | 52 | 96 |
| DeepSeek 3.2 | 3 | 3 | 0 | 28 | 94 | 26 | 68 |

For Kimi on the identical slice and chunk threshold, prompt v0.3 produced five
primary and five secondary protocols. Prompt v0.4 produced six primary and zero
secondary protocols. The review abstention behavior replicated across all three
model families, but the slice contains only one secondary paper.

Pairwise exact-claim Jaccard values were 0.242 for Opus–DeepSeek, 0.297 for
Opus–Kimi, and 0.165 for DeepSeek–Kimi. These are overlap metrics, not accuracy.

## Consensus and counterfactual evidence dependence

The comparable battery matrix produced 246 evidence-valid model proposals over
167 occurrence slots. Before perturbation, 55 slots had support from at least
two independent model families, 110 had insufficient family support, and two
contained valid value contradictions.

The 55 multi-family slots generated 78 evidence-deletion or numeric-replacement
cases and 181 targeted model observations. Of these, 147 passed, 31 failed, and
three were invalid. Recompilation yielded:

- 34 Tier A silver fields;
- 21 perturbation-failed disputes;
- 110 insufficient-family disputes;
- 2 valid-value contradictions.

All 34 Tier A fields came from the two primary papers: 22 material fields, seven
step fields, and five instrument fields. No review field entered Tier A.

## Reproducibility and remaining NMI gaps

The three model-specific scope-aware packages were rebuilt from frozen metadata
and cached raw model responses. After the selection schema v0.2 migration, a
second rebuild produced `changed_files = 0` for every package.

The current fail-closed readiness report remains negative. The remaining gates
are dominated by full-paper multi-model coverage, more primary papers,
additional perturbation and negative controls, externally grounded scientific
utility, deterministic rebuild of each full domain package, and both directed
cross-domain transfer/interference tests. Passing the engineering policy would
not itself imply publication acceptance.
