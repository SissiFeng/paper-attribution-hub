# Doob's Lagrangian: A Sample-Efficient Variational Approach to Transition Path Sampling

## Metadata
- Paper ID: `acfocus_8a68f03f6891`
- Cross-SDL ID: `not matched`
- DOI: 10.52202/079017-2103
- URL: https://proceedings.neurips.cc/paper_files/paper/2024/hash/78fa1d5646bc285940281cfc1386efae-Abstract-Conference.html
- Year: 2024
- Authors: Du Y, Plainer M, Brekelmans R, Duan C, Noé F, Gomes CP, Aspuru-Guzik A, Neklyudov K
- Venue: Advances in Neural Information Processing Systems
- Category: Conference
- Peer reviewed: Peer Reviewed
- AC members: Alán Aspuru-Guzik
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=checked

## Validation
- Score: 0.41
- Missing: hardware, evidence, materials, properties, measurements, mechanisms, outcomes, cross_sdl_match
- Notes: No cross-SDL extraction matched this paper; fields are derived from CSV only.; Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
This work introduces a variational, simulation-free approach to Doob's h-transform for rare event sampling in dynamical systems, enabling efficient trajectory optimization between specified endpoints and demonstrating success on molecular simulation and protein folding tasks.

## Abstract
Rare event sampling in dynamical systems is a fundamental problem arising in the natural sciences, which poses significant computational challenges due to an exponentially large space of trajectories. For settings where the dynamical system of interest follows a Brownian motion with known drift, the question of conditioning the process to reach a given endpoint or desired rare event is definitively answered by Doob's h-transform. However, the naive estimation of this transform is infeasible, as it requires simulating sufficiently many forward trajectories to estimate rare event probabilities. In this work, we propose a variational formulation of Doob's h-transform as an optimization problem over trajectories between a given initial point and the desired ending point. To solve this optimization, we propose a simulation-free training objective with a model parameterization that imposes the desired boundary conditions by design. Our approach significantly reduces the search space over trajectories and avoids expensive trajectory simulation and inefficient importance sampling estimators which are required in existing methods. We demonstrate the ability of our method to find feasible transition paths on real-world molecular simulation and protein folding tasks.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- This work introduces a variational, simulation-free approach to Doob's h-transform for rare event sampling in dynamical systems, enabling efficient trajectory optimization between specified endpoints and demonstrating success on molecular simulation and protein folding tasks.

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
- Artificial Intelligence & Data Science
- Biology
- Chemistry

### Materials / Systems
- Not specified.

### Properties
- Not specified.

### Measurements
- Not specified.

### Conditions
- To solve this optimization, we propose a simulation-free training objective with a model parameterization that imposes the desired boundary conditions by design.

### Mechanisms
- Not specified.

### Outcomes
- Not specified.

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Biology
- Chemistry

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
