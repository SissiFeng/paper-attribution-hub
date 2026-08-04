# One Set to Rule Them All: How to Obtain General Chemical Conditions via Bayesian Optimization over Curried Functions

## Metadata
- Paper ID: `acfocus_5d6bdb9c37d8`
- Cross-SDL ID: `acgold_f8f0839a0ffe`
- DOI: 10.48550/arxiv.2502.18966
- URL: https://arxiv.org/abs/2502.18966
- Year: 2025
- Authors: S. P. Schmid; E. M. Rajaonson; C. T. Ser; M. Haddadnia; S. X. Leong; A. Aspuru-Guzik; A. Kristiadi; K. Jorner; F. Strieth-Kalthoff
- Venue: arxiv
- Category: Preprint
- Peer reviewed: Non Peer Reviewed
- AC members: Alán Aspuru-Guzik
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.76
- Missing: hardware, materials, properties
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
This work demonstrates that generality-oriented Bayesian optimization, formulated as an optimization over curried functions and evaluated on real-world chemical reaction data, can efficiently identify general reaction conditions transferable to new tasks, with simple myopic strategies performing as well as more complex ones due to the importance of exploring both parameter and task spaces.

## Abstract
General parameters are highly desirable in the natural sciences - e.g., chemical reaction conditions that enable high yields across a range of related transformations. This has a significant practical impact since those general parameters can be transferred to related tasks without the need for laborious and time-intensive re-optimization. While Bayesian optimization (BO) is widely applied to find optimal parameter sets for specific tasks, it has remained underused in experiment planning towards such general optima. In this work, we consider the real-world problem of condition optimization for chemical reactions to study how performing generality-oriented BO can accelerate the identification of general optima, and whether these optima also translate to unseen examples. This is achieved through a careful formulation of the problem as an optimization over curried functions, as well as systematic evaluations of generality-oriented strategies for optimization tasks on real-world experimental data. We find that for generality-oriented optimization, simple myopic optimization strategies that decouple parameter and task selection perform comparably to more complex ones, and that effective optimization is merely determined by an effective exploration of both parameter and task space.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Systematic evaluations of generality-oriented optimization strategies using real-world chemical reaction optimization problems, formulating the problem as an optimization over curried functions.

### Problem
- Identifying general parameters for chemical reaction conditions that enable high yields across a range of related transformations.

### Hypothesis
- Generality-oriented Bayesian optimization can accelerate the identification of general optima for chemical reactions, which also translate to unseen examples.

### Evidence
- Benchmarking results showing that simple myopic optimization strategies perform comparably to more complex ones, and that effective optimization is determined by an effective exploration of both parameter and task space.

### Conclusion
- Generality-oriented optimization can yield more transferable optima, especially in scenarios with a low density of high-outcome experiments across the search space.

## Scientific Objects And Mechanisms
### Entities
- chemical reaction conditions (x)
- substrates (w)
- aggregation function (ϕ)

### Materials / Systems
- Not specified.

### Properties
- Not specified.

### Measurements
- Benchmarking results showing that simple myopic optimization strategies perform comparably to more complex ones, and that effective optimization is determined by an effective exploration of both parameter and task space.

### Conditions
- One Set to Rule Them All: How to Obtain General Chemical Conditions via Bayesian Optimization over Curried Functions This work demonstrates that generality-oriented Bayesian optimization, formulated as an optimization over curried functions and evaluated on real-world chemical reaction data, can efficiently identify general reaction conditions transferable to new tasks, with simple myopic strategies performing as well as more complex ones due to the importance of exploring both parameter and task spaces.
- General parameters are highly desirable in the natural sciences - e.g., chemical reaction conditions that enable high yields across a range of related transformations.
- This has a significant practical impact since those general parameters can be transferred to related tasks without the need for laborious and time-intensive re-optimization.
- In this work, we consider the real-world problem of condition optimization for chemical reactions to study how performing generality-oriented BO can accelerate the identification of general optima, and whether these optima also translate to unseen examples.
- chemical reaction conditions (x) substrates (w) aggregation function (ϕ) identification of general optima accelerated identification of transferable optima improved generality of identified conditions across substrates

### Mechanisms
- Bayesian optimization over curried functions
- exploration of parameter and task space
- partial monitoring of the generality objective

### Outcomes
- identification of general optima
- accelerated identification of transferable optima
- improved generality of identified conditions across substrates

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Chemistry
- Automation and Robotics

### Reasoning Motifs
- Optimization → Generality
- Exploration → Discovery

### General Principles
- Maximization of General Outcomes
- Efficient Exploration of Parameter Space

## Failure Paths / Caveats
- success: Benchmarking of different generality-oriented optimization strategies, including SEQ 1LA-UCB-PV, SEQ 2LA-UCB-PV, and JOINT 2LA-EI. Evidence: The SEQ 1LA-UCB-PV strategy showed faster optimization performance compared to other algorithms used in the chemical domain.
- partial: Comparison of sequential and joint two-step lookahead acquisition strategies. Evidence: Joint optimization did not lead to improved optimization performance over sequential strategies, suggesting the simpler sequential approach is well-suited for generality-oriented optimization.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_f8f0839a0ffe.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper provides a structured approach to evaluating generality-oriented optimization strategies, but some specific details on the reasoning behind choosing certain benchmarks or aggregation functions were not explicitly stated and had to be inferred.
