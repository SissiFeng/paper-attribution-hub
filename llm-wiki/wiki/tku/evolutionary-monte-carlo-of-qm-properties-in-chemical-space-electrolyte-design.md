---
type: tku
paper_id: acgold_1e9ddd3dc480
source_domain: battery
task_type: optimization
generated: '2026-06-11'
---

# Evolutionary Monte Carlo of QM properties in chemical space: Electrolyte design

- Source domain: battery
- Paper: acgold_1e9ddd3dc480 (2023)

## Problem signature

- task_type: optimization
- evaluation_cost: high
- search_space: discrete
- objectives: multi
- budget_evaluations: None
- batch_size: None
- noise: low

## Method core

- workflow: evolutionary Monte Carlo search over a graph-defined design space with tunable explore/exploit
- acquisition: Metropolis acceptance with adjustable temperature
- loop: propose mutation, evaluate objective, accept/reject, iterate
  - component: genetic-algorithm-style mutation operators on graph representations
  - component: Metropolis sampling to balance exploration and exploitation
  - component: hard constraints enforced during search (lower bound on a secondary property)
  - component: objective evaluated by a property predictor or simulator

## Assumptions

- the design space can be expressed as mutable graphs
- the objective is cheap enough to evaluate many times during sampling
- constraints can be enforced as bounds during proposal acceptance

## Lessons

- (positive) Casting the search as evolutionary Monte Carlo lets you tune exploration vs exploitation with a single temperature knob while keeping GA-style diversity.
- (positive) Encoding secondary requirements as hard lower-bound constraints keeps optimized candidates physically admissible.
- (neutral) The approach inherits the vastness of the combinatorial space, so results depend heavily on the seed library and mutation operators chosen.

## Domain bindings

- battery electrolyte molecules
- solvation energy / dipole moment / HOMO-LUMO gap
- QM9 / EGP molecular graphs

## Source labs

- [[wiki/labs/lilienfeld-lab|lilienfeld-lab]]
