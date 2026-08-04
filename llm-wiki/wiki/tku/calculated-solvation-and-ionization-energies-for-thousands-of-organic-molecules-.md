---
type: tku
paper_id: acgold_11f7152e6b04
source_domain: battery
task_type: characterization
generated: '2026-06-11'
---

# Calculated solvation and ionization energies for thousands of organic molecules relevant to battery design

- Source domain: battery
- Paper: acgold_11f7152e6b04 (2025)

## Problem signature

- task_type: characterization
- evaluation_cost: high
- search_space: discrete
- objectives: multi
- budget_evaluations: 18361
- batch_size: None
- noise: low

## Method core

- workflow: high-accuracy quantum-chemistry reference dataset generation over a fixed molecular library
  - component: hierarchy of ab-initio methods (HF, MP2-F12, CCSD(T)-F12) as accuracy tiers
  - component: large curated molecular library as the enumeration space
  - component: implicit-solvent models swept across many solvents
  - component: logging of compute cost (CPU time, disk) alongside each property

## Assumptions

- the property of interest can be computed accurately from molecular structure alone
- a finite enumerated library adequately covers the design space
- higher levels of theory give trustworthy reference values

## Lessons

- (positive) A tiered set of theory levels lets you trade compute cost against accuracy and produce calibrated reference labels.
- (positive) Recording CPU time and storage per calculation makes the cost of high-fidelity labels explicit for downstream budgeting.
- (negative) Coverage is bounded by the chosen library; properties outside the enumerated chemical space are not represented.

## Domain bindings

- lithium battery electrolyte
- ionization potential / electron affinity
- solvation energy
- QM9 / Electrolyte Genome Project molecules

## Source labs

- [[wiki/labs/lilienfeld-lab|lilienfeld-lab]]
