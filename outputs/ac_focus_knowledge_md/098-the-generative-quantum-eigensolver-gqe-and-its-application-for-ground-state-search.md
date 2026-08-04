# The generative quantum eigensolver (GQE) and its application for ground state search

## Metadata
- Paper ID: `acfocus_9a1b75082acf`
- Cross-SDL ID: `acgold_1837509052d6`
- DOI: 10.48550/arxiv.2401.09253
- URL: https://arxiv.org/abs/2401.09253
- Year: 2024
- Authors: Nakaji K, Kristensen LB, Campos-Gonzalez-Angulo JA, Vakili MG, Huang H, Bagherimehrab M, Gorgulla C, Wong F, McCaskey A, Kim J-S, Nguyen T, Rao P, Aspuru-Guzik A
- Venue: arxiv
- Category: Preprint
- Peer reviewed: Non Peer Reviewed
- AC members: Alán Aspuru-Guzik
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.78
- Missing: source_summary, hardware, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
Not specified in CSV.

## Abstract
The generative quantum eigensolver (GQE) and its
application for ground state search
Kouhei Nakaji1,2,3,9, Lasse Bjørn Kristensen1,4, Ryota Kemmoku3, Jorge A.
Campos-Gonzalez-Angulo ∗1, Mohammad Ghazi Vakili ∗1,4, Haozhe Huang ∗4,5, Mohsen
Bagherimehrab †1,4, Christoph Gorgulla †6,7, FuTe Wong4,8, Alex McCaskey9, Jin-Sung Kim9,
Thien Nguyen9, Pooja Rao9, Qi Gao3, 13, Michihiko Sugawara3, Naoki Yamamoto3, and Alan
Aspuru-Guzik1,4,5,10,11,12,9
1 Chemical Physics Theory Group, Department of Chemistry, University of Toronto, Toronto, Ontario, Canada
2Research Center for Emerging Computing Technologies, National Institute of Advanced Industrial Science and
Technology (AIST), 1-1-1 Umezono, Tsukuba, Ibaraki, Japan
3Quantum Computing Center, Keio University, 3-14-1 Hiyoshi, Kohoku-ku, Yokohama, Kanagawa, Japan
4Department of Computer Science, University of Toronto, Toronto, Ontario, Canada
5Vector Institute for Artificial Intelligence, Toronto, Ontario, Canada
6Department of Physics, Faculty of Arts and Sciences, Harvard University, Cambridge, Massachusetts, USA
7Department of Structural Biology, St. Jude Children’s Research Hospital, Memphis, Tennessee, USA
8Institute of Medical Science, University of Toronto, Toronto, Ontario, Canada
9NVIDIA, Santa Clara, California, USA
10Department of Chemical Engineering & Applied Chemistry, University of Toronto, Toronto, Ontario, Canada
11Department of Materials Science & Engineering, University of Toronto, Toronto, Ontario, Canada
12Lebovic Fellow, Canadian Institute for Advanced Research, Toronto, Ontario, Canada
13Mitsubishi Chemical Corporation, Science & Innovation Center, 1000, Kamoshida-cho, Aoba-ku, Yokohama
227-8502, Japan
Abstract
We introduce the generative quantum eigensolver
(GQE), a new quantum computational framework
that operates outside the variational quantum al-
gorithm paradigm by applying classical genera-
tive models to quantum simulation.
The GQE
algorithm optimizes a classical generative model
to produce quan

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
- Chemistry
- Physics

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
