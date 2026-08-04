---
type: tku
paper_id: acgold_320cac94a8b2
source_domain: catalysis
task_type: prediction
generated: '2026-06-11'
---

# Combining Hammett σ constants for Δ-machine learning and catalyst discovery

- Source domain: catalysis
- Paper: acgold_320cac94a8b2 (2024)

## Problem signature

- task_type: prediction
- evaluation_cost: high
- search_space: discrete
- objectives: single
- budget_evaluations: None
- batch_size: None
- noise: low

## Method core

- workflow: physics-informed additive baseline plus delta-machine-learning to correct residuals, screening via volcano plots
- surrogate_model: delta-ML model correcting a cheap analytic baseline
- acquisition: volcano-plot ranking to nominate top candidates
  - component: additive combination rule giving a cheap analytic baseline (HIP/cHIP)
  - component: delta-ML trained only on the baseline residuals for data efficiency
  - component: volcano plots to identify promising candidates

## Assumptions

- a domain-knowledge additive baseline captures most of the signal
- residuals are easier and cheaper to learn than the full target
- candidate quality is well summarized by a descriptor on a volcano plot

## Lessons

- (positive) Learning only the residual on top of a physics-based additive baseline sharply improves data efficiency.
- (positive) An additive combination rule lets you extend descriptors to unseen pairings without new measurements.
- (neutral) The baseline must actually be predictive for delta-ML to pay off; a poor baseline shifts the whole burden back to the ML model.

## Domain bindings

- homogeneous organometallic catalysis
- Hammett sigma constants / ligands and metals
- Suzuki-Miyaura cross-coupling

## Source labs

- [[wiki/labs/lilienfeld-lab|lilienfeld-lab]]
