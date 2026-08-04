---
type: tku
paper_id: acgold_45436743f63f
source_domain: polymer
task_type: prediction
generated: '2026-06-11'
---

# A formulation dataset of poly(lactide-co-glycolide) nanoparticles for small molecule delivery

- Source domain: polymer
- Paper: acgold_45436743f63f (2025)

## Problem signature

- task_type: prediction
- evaluation_cost: high
- search_space: mixed
- objectives: multi
- budget_evaluations: 433
- batch_size: None
- noise: medium

## Method core

- workflow: literature-curated dataset assembly to enable data-driven property prediction over a formulation design space
- surrogate_model: machine learning regressors trained on tabular formulation features
  - component: manual literature curation into a structured open dataset
  - component: formulation composition + process parameters as features
  - component: measured physical characteristics as prediction targets

## Assumptions

- published formulations are comparable enough to pool into one dataset
- tabular composition/process features capture the drivers of the target properties
- 433 records suffice to learn useful structure-property relationships

## Lessons

- (positive) A shared, literature-curated open dataset is the prerequisite that unblocks ML-accelerated formulation design in a field that lacked one.
- (neutral) Designing and optimizing these formulations is an iterative trial-and-error process that data-driven models aim to shortcut.
- (negative) Comprehensive open datasets remain scarce despite decades of research, which is itself the bottleneck.

## Domain bindings

- PLGA nanoparticle
- small-molecule drug delivery
- encapsulation efficiency / particle size

## Source labs

- [[wiki/labs/allen-lab|allen-lab]]
- [[wiki/labs/bao-lab|bao-lab]]
