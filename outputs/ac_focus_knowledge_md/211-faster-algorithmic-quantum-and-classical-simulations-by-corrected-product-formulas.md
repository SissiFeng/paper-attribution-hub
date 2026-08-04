# Faster Algorithmic Quantum and Classical Simulations by Corrected Product Formulas

## Metadata
- Paper ID: `acfocus_9867fe114e69`
- Cross-SDL ID: `acgold_30d14094bc1c`
- DOI: 10.48550/arxiv.2409.08265
- URL: https://arxiv.org/abs/2409.08265
- Year: 2024
- Authors: Bagherimehrab M, Calderon LM, Berry DW, Schleich P, Vakili MG, Aldossary A, Angulo JACG, Gorgulla C, Aspuru-Guzik A
- Venue: arxiv
- Category: Preprint
- Peer reviewed: Non Peer Reviewed
- AC members: Alán Aspuru-Guzik
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.65
- Missing: source_summary, hardware, materials, measurements, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
Not specified in CSV.

## Abstract
Faster Algorithmic Quantum and Classical Simulations
by Corrected Product Formulas
Mohsen Bagherimehrab∗†1,2, Luis Mantilla Calder´on†2,4, Dominic W. Berry3, Philipp
Schleich2,4, Mohammad Ghazi Vakili1,2, Abdulrahman Aldossary1, Jorge A. Campos
Gonzalez Angulo1,4, Christoph Gorgulla5,6, and Al´an Aspuru-Guzik1,2,4,7,8,9
1Chemical Physics Theory Group, Department of Chemistry, University of Toronto, Toronto, Ontario, Canada
2Department of Computer Science, University of Toronto, Toronto, Ontario, Canada
3School of Mathematical and Physical Sciences, Macquarie University, Sydney, NSW 2109, Australia
4Vector Institute for Artificial Intelligence, Toronto, Ontario, Canada
5Department of Physics, Harvard University, Cambridge, MA, USA
6Department of Structural Biology, St. Jude Children’s Research Hospital, Memphis, TN, USA
7Department of Chemical Engineering & Applied Chemistry, University of Toronto, Toronto, Ontario, Canada
8Department of Materials Science & Engineering, University of Toronto, Toronto, Ontario, Canada
9Lebovic Fellow, Canadian Institute for Advanced Research, Toronto, Ontario, Canada
March 19, 2025
Abstract
Hamiltonian simulation using product formulas is arguably the most straightforward and practical
approach for algorithmic simulation of a quantum system’s dynamics on a quantum computer. Here we
present corrected product formulas (CPFs), a variation of product formulas achieved by injecting auxiliary
terms called correctors into standard product formulas. We establish several correctors that greatly improve
the accuracy of standard product formulas for simulating Hamiltonians comprised of two partitions that
can be exactly simulated, a common feature of lattice Hamiltonians, while only adding a small additive
or multiplicative factor to the simulation cost. We show that correctors are particularly advantageous for
perturbed systems, where one partition has a relatively small norm compared to the other, as they allow the
small norm to be utilized as

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Injecting auxiliary terms called correctors into standard product formulas to create CPFs, establishing several correctors that greatly improve the accuracy of standard product formulas while only adding a small additive or multiplicative factor to the simulation cost.

### Problem
- Developing efficient methods for simulating Hamiltonian evolution on quantum computers, particularly for systems with a Hamiltonian of the form H = A + αB where A and B have comparable norms and can be exactly simulated.

### Hypothesis
- Corrected product formulas (CPFs) can significantly improve the accuracy of standard product formulas for simulating Hamiltonians comprised of two partitions that can be exactly simulated.

### Evidence
- Numerical simulations for various lattice Hamiltonians demonstrate that the theoretical performance of CPFs matches or exceeds the empirical performance of standard product formulas.

### Conclusion
- CPFs are a valuable algorithmic tool for early fault-tolerant quantum computers with limited computing resources, offering significant improvements in simulation accuracy and efficiency.

## Scientific Objects And Mechanisms
### Entities
- Hamiltonian H
- Partitions A and B
- Correctors

### Materials / Systems
- Not specified.

### Properties
- Faster Algorithmic Quantum and Classical Simulations by Corrected Product Formulas Injecting auxiliary terms called correctors into standard product formulas to create CPFs, establishing several correctors that greatly improve the accuracy of standard product formulas while only adding a small additive or multiplicative factor to the simulation cost.
- Hamiltonian H Partitions A and B Correctors Improved accuracy of Hamiltonian simulation Reduction in simulation cost Efficient synthesis of complicated unitaries on a quantum simulator

### Measurements
- Not specified.

### Conditions
- Not specified.

### Mechanisms
- Hamiltonian simulation using product formulas
- Error reduction through corrector injection
- Compilation of correctors into a product of exponentials of Hamiltonian terms

### Outcomes
- Improved accuracy of Hamiltonian simulation
- Reduction in simulation cost
- Efficient synthesis of complicated unitaries on a quantum simulator

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Chemistry
- Quantum

### Reasoning Motifs
- Refinement → Accuracy
- Compilation → Efficiency

### General Principles
- Optimization of computational resources
- Enhancement of algorithmic precision

## Failure Paths / Caveats
- No explicit failure path available in CSV/cross-SDL extraction.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_30d14094bc1c.json`
- Cross-SDL extraction quality: 0.9
- Notes: The paper presents a structured approach to developing CPFs, with clear hypotheses, methods, and results. The reasoning is explicit, and the conclusions are well-supported by the evidence provided.
