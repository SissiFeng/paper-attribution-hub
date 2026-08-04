---
type: tku
paper_id: acgold_092a5c2d81d2
source_domain: robotics
task_type: automation
generated: '2026-06-11'
---

# Large language models for chemistry robotics

- Source domain: robotics
- Paper: acgold_092a5c2d81d2 (2023)

## Problem signature

- task_type: automation
- evaluation_cost: high
- search_space: discrete
- objectives: single
- budget_evaluations: None
- batch_size: None
- noise: high

## Method core

- workflow: translate natural-language instructions into executable plans via LLM plus task-and-motion planning
- surrogate_model: large language model as the instruction-to-plan translator
- loop: perceive workspace, plan multi-step actions, execute, re-plan
  - component: LLM front-end converting NL instructions to structured plans
  - component: task and motion planning to ground plans in feasible actions
  - component: perception of the physical workspace
  - component: embodied execution with multi-step action sequencing

## Assumptions

- user intent can be expressed adequately in natural language
- an LLM can map NL to valid high-level plans
- the environment is perceivable and actions are physically executable

## Lessons

- (positive) A natural-language interface lowers the barrier so non-expert users can drive complex autonomous-experiment hardware.
- (negative) Reliably executing LLM-generated plans in the real world by an embodied agent remains challenging.
- (neutral) Coupling the LLM planner with task-and-motion planning is what bridges high-level intent and low-level robot commands.

## Domain bindings

- chemistry experiment robots
- robot-executable / low-level robotics languages
- autonomous chemistry experiment systems

## Source labs

- [[wiki/labs/aspuru-guzik-lab|aspuru-guzik-lab]]
- [[wiki/labs/darvish-lab|darvish-lab]]
- [[wiki/labs/garg-lab|garg-lab]]
- [[wiki/labs/shkurti-lab|shkurti-lab]]
