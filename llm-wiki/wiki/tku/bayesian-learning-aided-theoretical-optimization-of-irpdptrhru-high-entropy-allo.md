---
type: tku
paper_id: acgold_65692bf39579
source_domain: catalysis
task_type: optimization
generated: '2026-06-11'
---

# Bayesian Learning Aided Theoretical Optimization of IrPdPtRhRu High Entropy Alloy Catalysts for the Hydrogen Evolution Reaction

- Source domain: catalysis
- Paper: acgold_65692bf39579 (2024)

## Problem signature

- task_type: optimization
- evaluation_cost: high
- search_space: mixed
- objectives: single
- budget_evaluations: None
- batch_size: None
- noise: medium

## Method core

- workflow: physics-grounded simulation feeding Bayesian optimization over a compositional space
- surrogate_model: Bayesian / Gaussian-process model over composition
- acquisition: Bayesian optimization with oversampling to handle imbalance
- loop: simulate candidate, score, update posterior, propose next composition
  - component: first-principles simulation as the expensive evaluator
  - component: Bayesian model for compositional optimization
  - component: oversampling strategy to address imbalanced/sparse regimes
  - component: mechanistic analysis to interpret why optima work

## Assumptions

- simulation fidelity is high enough to guide the search
- the compositional space is the dominant lever on performance
- a Bayesian surrogate can be trained from limited simulated data

## Lessons

- (positive) Coupling first-principles simulation with Bayesian optimization makes compositional search over a huge space tractable.
- (positive) An oversampling variant of Bayesian learning helps when the informative region is sparse or imbalanced.
- (neutral) Without mechanistic insight into the system, blind compositional modification is unfeasible, so interpretability is part of the method, not an add-on.

## Domain bindings

- IrPdPtRhRu high-entropy-alloy catalyst
- hydrogen evolution reaction
- d-band / underpotential-deposited hydrogen

## Source labs

- [[wiki/labs/cao-lab|cao-lab]]
- [[wiki/labs/singh-lab|singh-lab]]
