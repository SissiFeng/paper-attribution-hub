# The generative quantum eigensolver (GQE) and its application for ground state search

## Metadata
- Paper ID: `acfocus_9a1b75082acf`
- Cross-SDL ID: `acgold_1837509052d6`
- DOI: 10.48550/arxiv.2401.09253
- URL: https://arxiv.org/abs/2401.09253
- Year: 2024
- Authors: Nakaji, Kouhei; Kristensen, Lasse Bjørn; Campos-Gonzalez-Angulo, Jorge A.; Vakili, Mohammad Ghazi; Huang, Haozhe; Bagherimehrab, Mohsen; Gorgulla, Christoph; Wong, FuTe; McCaskey, Alex; Kim, Jin-Sung; Nguyen, Thien; Rao, Pooja; Aspuru-Guzik, Alan
- Venue: arxiv
- Category: Preprint
- Peer reviewed: Non Peer Reviewed
- AC members: Alán Aspuru-Guzik
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.86
- Missing: hardware, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
The generative quantum eigensolver (GQE) is a new approach that uses classical generative models, specifically a transformer-based GPT quantum eigensolver (GPT-QE), to optimize quantum circuits for simulating ground states of electronic structure Hamiltonians, with potential applications in broader areas of quantum computing.

## Abstract
We introduce the generative quantum eigensolver (GQE), a novel method for applying classical generative models for quantum simulation. The GQE algorithm optimizes a classical generative model to produce quantum circuits with desired properties. Here, we develop a transformer-based implementation, which we name the generative pre-trained transformer-based (GPT) quantum eigensolver (GPT-QE), leveraging both pre-training on existing datasets and training without any prior knowledge. We demonstrate the effectiveness of training and pre-training GPT-QE in the search for ground states of electronic structure Hamiltonians. GQE strategies can extend beyond the problem of Hamiltonian simulation into other application areas of quantum computing.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- The authors propose a transformer-based implementation of GQE, named GPT-QE, and demonstrate its training and pretraining on electronic structure Hamiltonians, comparing its performance to coupled cluster singles and doubles (CCSD) methods.

### Problem
- Developing a quantum computational framework that operates outside the variational quantum algorithm paradigm by applying classical generative models to quantum simulation for ground state search.

### Hypothesis
- A generative quantum eigensolver (GQE) can optimize a classical generative model to produce quantum circuits with desired properties, potentially overcoming limitations of variational quantum algorithms.

### Evidence
- GPT-QE outperforms CCSD in the strong bond dissociation regime of the nitrogen molecule and approaches chemical accuracy, as shown in Figures 4, 5, and 6.

### Conclusion
- GPT-QE demonstrates the ability to find a quantum state with energy close to that of the ground state, offering a new approach to quantum circuit generation that leverages classical generative models.

## Scientific Objects And Mechanisms
### Entities
- GPT-QE model
- Quantum circuits
- Electronic structure Hamiltonians
- Pauli operators
- Unitary operators

### Materials / Systems
- GPT-QE outperforms CCSD in the strong bond dissociation regime of the nitrogen molecule and approaches chemical accuracy, as shown in Figures 4, 5, and 6.

### Properties
- The GQE algorithm optimizes a classical generative model to produce quantum circuits with desired properties.
- GPT-QE outperforms CCSD in the strong bond dissociation regime of the nitrogen molecule and approaches chemical accuracy, as shown in Figures 4, 5, and 6.

### Measurements
- GPT-QE model Quantum circuits Electronic structure Hamiltonians Pauli operators Unitary operators Improved trainability for large problem instances Approximation of ground state energies Reduction in measurement cost Potential for incorporating domain knowledge into circuit generation

### Conditions
- Not specified.

### Mechanisms
- Transformer-based generative model optimization
- Quantum circuit generation via sequence sampling
- Energy estimation using Pauli expectation values
- Operator pool construction from unitary coupled-cluster single and double excitations

### Outcomes
- Improved trainability for large problem instances
- Approximation of ground state energies
- Reduction in measurement cost
- Potential for incorporating domain knowledge into circuit generation

## Cross-SDL Transfer
### SDL / Domain Tags
- Quantum
- Artificial Intelligence & Data Science

### Reasoning Motifs
- Model Optimization → Performance Improvement
- Circuit Generation → Energy Approximation
- Data Reuse → Computational Efficiency
- Knowledge Incorporation → Problem-specific Solutions

### General Principles
- Optimization Leads to Improvement
- Representation Reuse Enhances Efficiency
- Adaptation to Constraints Enables Specificity

## Failure Paths / Caveats
- success: Comparing GRPO and Logit Matching loss functions for N2 at bond length 1.5 ˚A. Evidence: GRPO consistently outperforms Logit Matching across all gate counts, achieving lower energy values and demonstrating better convergence properties.
- success: Investigating the effect of pre-training data ratio on energy evaluation count for N2 at bond length 1.05 ˚A. Evidence: Using pre-constructed data significantly reduces the number of energy evaluations needed to achieve chemical accuracy.
- success: Validating the practical applicability of GPT-QE on the IBM 127-qubit backend for the H2 molecule. Evidence: Calculations performed on ibm kawasaki closely reproduce the exact energy values, demonstrating successful training on the quantum device.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_1837509052d6.json`
- Cross-SDL extraction quality: 0.9
- Notes: The paper presents a structured approach to developing and testing GPT-QE, with clear hypotheses, methods, and results. The reasoning is explicit, and the conclusions are well-supported by the data presented.
