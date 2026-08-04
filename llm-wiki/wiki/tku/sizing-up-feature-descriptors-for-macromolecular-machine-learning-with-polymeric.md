---
type: tku
paper_id: acgold_5e6d32360cf7
source_domain: polymer
task_type: prediction
generated: '2026-06-11'
---

# Sizing up feature descriptors for macromolecular machine learning with polymeric biomaterials

- Source domain: polymer
- Paper: acgold_5e6d32360cf7 (2023)

## Problem signature

- task_type: prediction
- evaluation_cost: medium
- search_space: mixed
- objectives: single
- budget_evaluations: None
- batch_size: None
- noise: medium

## Method core

- workflow: comparative survey of feature-representation choices for ML on macromolecular systems
- surrogate_model: machine learning models over alternative molecular feature descriptors
  - component: multiple competing descriptor families compared on the same task
  - component: explicit discussion of merits/limitations per representation
  - component: emphasis on feature engineering as the lever for accuracy

## Assumptions

- choice of feature representation materially changes predictive performance
- no single representation is universally best

## Lessons

- (negative) There is no consensus universal representation for macromolecules; the right descriptor is sensitive to the property being predicted.
- (positive) Making feature-engineering knowledge accessible is itself a lever for accelerating discovery.
- (neutral) Representation choice should be treated as a tunable design decision, not a fixed preprocessing step.

## Domain bindings

- polymeric biomaterials
- biomaterial interaction prediction
- macromolecular descriptors

## Source labs

- [[wiki/labs/gu-lab|gu-lab]]
- [[wiki/labs/watchorn-lab|watchorn-lab]]
