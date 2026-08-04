# STAMP: Differentiable Task and Motion Planning via Stein Variational Gradient Descent

## Metadata
- Paper ID: `acfocus_5801dba98ce9`
- Cross-SDL ID: `not matched`
- DOI: 10.1109/lra.2025.3561575
- URL: https://ieeexplore.ieee.org/document/10966056
- Year: 2025
- Authors: Y. Lee; A. Z. Li; P. Huang; E. Heiden; K. M. Jatavallabhula; F. Damken; K. Smith; D. Nowrouzezahrai; F. Ramos; F. Shkurti
- Venue: IEEE Robotics and Automation Letters
- Category: Journal Article
- Peer reviewed: Peer Reviewed
- AC members: Florian Shkurti
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.3
- Missing: hardware, evidence, entities, materials, properties, measurements, conditions, mechanisms, outcomes, cross_sdl_match
- Notes: No cross-SDL extraction matched this paper; fields are derived from CSV only.; Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
The authors introduce Stein Task and Motion Planning (STAMP), a novel approach to TAMP that uses gradient-based variational inference and differentiable physics simulation to efficiently optimize both discrete and continuous plan parameters, enabling the discovery of multiple diverse and feasible plans in a single, GPU-parallelized optimization run.

## Abstract
Planning for sequential robotics tasks often requires integrated symbolic and geometric reasoning. TAMP algorithms typically solve these problems by performing a tree search over high-level task sequences while checking for kinematic and dynamic feasibility. This can be inefficient because, typically, candidate task plans resulting from the tree search ignore geometric information. This often leads to motion planning failures that require expensive backtracking steps to find alternative task plans. We propose a novel approach to TAMP called Stein Task and Motion Planning (STAMP) that relaxes the hybrid optimization problem into a continuous domain. This allows us to leverage gradients from differentiable physics simulation to fully optimize discrete and continuous plan parameters for TAMP. In particular, we solve the optimization problem using a gradient-based variational inference algorithm called Stein Variational Gradient Descent. This allows us to find a distribution of solutions within a single optimization run. Furthermore, we use an off-the-shelf differentiable physics simulator that is parallelized on the GPU to run parallelized inference over diverse plan parameters. We demonstrate our method on a variety of problems and show that it can find multiple diverse plans in a single optimization run while also being significantly faster than existing approaches.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- The authors introduce Stein Task and Motion Planning (STAMP), a novel approach to TAMP that uses gradient-based variational inference and differentiable physics simulation to efficiently optimize both discrete and continuous plan parameters, enabling the discovery of multiple diverse and feasible plans in a single, GPU-parallelized optimization run.

### Problem
- Not specified by cross-SDL extraction.

### Hypothesis
- Not specified by cross-SDL extraction.

### Evidence
- Not specified by cross-SDL extraction.

### Conclusion
- Not specified by cross-SDL extraction.

## Scientific Objects And Mechanisms
### Entities
- Not specified.

### Materials / Systems
- Not specified.

### Properties
- Not specified.

### Measurements
- Not specified.

### Conditions
- Not specified.

### Mechanisms
- Not specified.

### Outcomes
- Not specified.

## Cross-SDL Transfer
### SDL / Domain Tags
- Not specified.

### Reasoning Motifs
- Not specified by cross-SDL extraction.

### General Principles
- Not specified by cross-SDL extraction.

## Failure Paths / Caveats
- No explicit failure path available in CSV/cross-SDL extraction.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `not available`
- Cross-SDL extraction quality: not available
- Notes: No additional notes.
