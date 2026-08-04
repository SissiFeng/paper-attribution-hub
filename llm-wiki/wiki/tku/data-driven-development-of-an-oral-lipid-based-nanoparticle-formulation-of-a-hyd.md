---
type: tku
paper_id: acgold_69fd03b3ab15
source_domain: polymer
task_type: optimization
generated: '2026-06-11'
---

# Data-driven development of an oral lipid-based nanoparticle formulation of a hydrophobic drug

- Source domain: polymer
- Paper: acgold_69fd03b3ab15 (2024)

## Problem signature

- task_type: optimization
- evaluation_cost: high
- search_space: mixed
- objectives: multi
- budget_evaluations: None
- batch_size: None
- noise: medium

## Method core

- workflow: closed-loop design combining experimental automation with ML over a constrained formulation space
- surrogate_model: machine learning model mapping formulation parameters to performance
- acquisition: model-guided selection of next formulations to test
- loop: propose formulation, run automated experiment, measure, update model, repeat
  - component: experimental automation for reproducible sample preparation/measurement
  - component: ML surrogate trained on a small initial subset
  - component: iterative model-in-the-loop selection
  - component: narrow but well-characterized design space

## Assumptions

- a small initial subset of experiments is enough to seed a useful surrogate
- automated experiments are reproducible enough to train on
- the relevant design space can be bounded a priori

## Lessons

- (positive) Pairing experimental automation with ML lets you accelerate design even when starting from only a small subset of experiments.
- (negative) Traditional design methods are restricted to a narrow design space, which the data-driven loop is meant to widen.
- (neutral) Complex multi-component formulations make design intricate, so constraining the space up front is necessary.

## Domain bindings

- solid lipid nanoparticle / nanostructured lipid carrier
- cannabidiol (hydrophobic drug)
- oral bioavailability

## Source labs

- [[wiki/labs/allen-lab|allen-lab]]
- [[wiki/labs/aspuru-guzik-lab|aspuru-guzik-lab]]
- [[wiki/labs/bao-lab|bao-lab]]
