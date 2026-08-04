# A composite measurement scheme for efficient quantum observable estimation

## Metadata
- Paper ID: `acfocus_108bfdf82890`
- Cross-SDL ID: `acgold_8e5ff347de93`
- DOI: 10.48550/arxiv.2305.02439
- URL: https://arxiv.org/abs/2305.02439
- Year: 2023
- Authors: Zhang, Zi-Jian; Nakaji, Kouhei; Choi, Matthew; Aspuru-Guzik, Alán
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
The paper introduces a composite measurement scheme called Composite-LBCS (C-LBCS) that optimally distributes measurement shots among multiple schemes, demonstrating improved efficiency and performance in observable estimation for large quantum systems compared to previous methods.

## Abstract
Estimation of the expectation value of observables is a key subroutine in quantum computing and is also the bottleneck of the performance of many near-term quantum algorithms. Many works have been proposed to reduce the number of measurements needed for this task and they provide different measurement schemes for generating the measurements to perform. In this paper, we propose a new approach, composite measurement scheme, which composes multiple measurement schemes by distributing shots to them with a trainable ratio. As an example of our method, we study the case where only Pauli measurements are allowed and propose Composite-LBCS (C-LBCS), a composite measurement scheme made by composing locally-biased classical shadows. We numerically demonstrate C-LBCS on molecular systems up to $\mathrm{CO}_2$ (30 qubits) and show that C-LBCS outperforms the previous state-of-the-art methods despite its simplicity. We also show that C-LBCS can be efficiently optimized by stochastic gradient descent and is trainable even when the observable contains a large number of terms. We believe our method opens up a reliable way toward efficient observable estimation on large quantum systems.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- The authors propose a composite measurement scheme, Composite-LBCS (C-LBCS), which combines multiple locally-biased classical shadows by distributing shots to them with trainable probabilities. They use stochastic gradient descent and a two-time-scale update rule for optimization.

### Problem
- Estimation of the expectation value of observables is a key subroutine in quantum computing and is also the bottleneck of the performance of many near-term quantum algorithms.

### Hypothesis
- A composite measurement scheme that composes multiple measurement schemes by distributing shots to them with a trainable ratio can improve the efficiency of observable estimation.

### Evidence
- Numerical demonstrations on molecular systems up to CO2 (30 qubits) show that C-LBCS outperforms previous state-of-the-art methods despite its simplicity.

### Conclusion
- The composite measurement scheme opens up a reliable way toward efficient observable estimation on large quantum systems.

## Scientific Objects And Mechanisms
### Entities
- Quantum observables
- Quantum measurements
- Pauli operators
- Locally-biased classical shadows (LBCS)
- Composite measurement scheme (CMS)

### Materials / Systems
- Not specified.

### Properties
- Not specified.

### Measurements
- A composite measurement scheme for efficient quantum observable estimation The paper introduces a composite measurement scheme called Composite-LBCS (C-LBCS) that optimally distributes measurement shots among multiple schemes, demonstrating improved efficiency and performance in observable estimation for large quantum systems compared to previous methods.
- Many works have been proposed to reduce the number of measurements needed for this task and they provide different measurement schemes for generating the measurements to perform.
- In this paper, we propose a new approach, composite measurement scheme, which composes multiple measurement schemes by distributing shots to them with a trainable ratio.
- As an example of our method, we study the case where only Pauli measurements are allowed and propose Composite-LBCS (C-LBCS), a composite measurement scheme made by composing locally-biased classical shadows.
- The authors propose a composite measurement scheme, Composite-LBCS (C-LBCS), which combines multiple locally-biased classical shadows by distributing shots to them with trainable probabilities.

### Conditions
- They use stochastic gradient descent and a two-time-scale update rule for optimization.

### Mechanisms
- Estimation of expectation values from quantum measurements
- Combination of multiple measurement schemes into a composite scheme
- Optimization of the composite scheme using stochastic gradient descent
- Reduction of variance in observable estimation

### Outcomes
- Improved efficiency in estimating quantum observables
- Scalability of the measurement scheme to large quantum systems
- State-of-the-art measurement efficiency despite simplicity

## Cross-SDL Transfer
### SDL / Domain Tags
- Quantum
- Chemistry
- Artificial Intelligence & Data Science

### Reasoning Motifs
- Combination → Enhanced Representation Power
- Optimization → Performance Improvement
- Variance Reduction → Estimation Efficiency

### General Principles
- Control Through Combinations
- Optimization Leads to Efficiency
- Precision Through Variance Minimization

## Failure Paths / Caveats
- success: Applying the Rescale and TTUR strategies in training C-LBCS Evidence: Applying both strategies provides the best result in most cases.
- success: Training C-LBCS with different batch sizes Evidence: The cost function converges to similar values, indicating training is not sensitive to batch size.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_8e5ff347de93.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper presents a clear hypothesis, method, and results, but some details of the exploration narrative had to be inferred from the discussion of results and methods. The reasoning structure is well-defined, but the paper does not explicitly state some of the higher-level motifs and principles, which required interpretation.
