# Chemically Motivated Simulation Problems are Efficiently Solvable by a Quantum Computer

## Metadata
- Paper ID: `acfocus_5798b54f009f`
- Cross-SDL ID: `acgold_3cf8ce0004ba`
- DOI: 10.48550/arxiv.2401.09268
- URL: https://arxiv.org/abs/2401.09268
- Year: 2024
- Authors: Schleich P, Kristensen LB, Angulo JACG, Avagliano D, Bagherimehrab M, Aldossary A, Gorgulla C, Fitzsimons J, Aspuru-Guzik A
- Venue: arxiv
- Category: Preprint
- Peer reviewed: Non Peer Reviewed
- AC members: Alán Aspuru-Guzik
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.68
- Missing: source_summary, hardware, materials, properties
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
Not specified in CSV.

## Abstract
Chemically Motivated Simulation Problems are Efficiently Solvable by a Quantum Computer
Philipp Schleich,1, 2, ∗Lasse Bjørn Kristensen,1, 3, 4, † Jorge A. Campos-Gonzalez-Angulo,3, 2
Abdulrahman Aldossary,3 Davide Avagliano,3, 5 Mohsen Bagherimehrab,1
Christoph Gorgulla,6, 7 Joe Fitzsimons,8 and Alán Aspuru-Guzik1, 2, 3, 9, 10, 11, 12, 13, ‡
1Department of Computer Science, University of Toronto, Toronto, ON M5S 3G4, Canada.
2Vector Institute of Artificial Intelligence, Toronto, ON M5G 1M1, Canada.
3Department of Chemistry, University of Toronto, Toronto, ON M5S 3H6, Canada.
4Department of Computer Science, University of Copenhagen, Copenhagen, DK-2100, Denmark.
5Chimie ParisTech, PSL University, CNRS, Institute for Life and Health Sciences (iCLeHS UMR 8060), 75005 Paris, France.
6Department of Structural Biology, St. Jude Children’s Research Hospital, Memphis, TN 38105, USA.
7Department of Physics, Harvard University, Cambridge, MA 02138, USA.
8Horizon Quantum Computing, Singapore 138565.
9Department of Chemical Engineering & Applied Chemistry, University of Toronto, Toronto, ON M5S 3E5, Canada.
10Department of Materials Science & Engineering, University of Toronto, Toronto, ON M5S 3E4, Canada.
11Acceleration Consortium, Toronto, ON M5S 3H6, Canada.
12Canadian Institute for Advanced Research, Toronto, ON M5G 1Z8, Canada.
13Lebovic Fellow, Canadian Institute for Advanced Research, Toronto, ON M5S 1M1, Canada.
Simulating chemical systems is highly sought after and computationally challenging, as the number of degrees
of freedom increases exponentially with the size of the system. Quantum computers have been proposed as
a computational means to overcome this bottleneck , thanks to their capability of representing this amount of
information efficiently. Most efforts so far have been centered around determining the ground states of chemical
systems. However, hardness results and the lack of theoretical guarantees for efficient heuristics for initial-state
generation she

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- The proposed framework employs a limited set of attainable atomic initial states and dynamically prepares input states for a reaction of interest through a scattering process, specifically by hierarchically combining atomic states through scattering.

### Problem
- Simulating chemical systems is highly sought after and computationally challenging due to the exponential increase in degrees of freedom with system size.

### Hypothesis
- A heuristically guided approach based on efficient routines can solve chemical simulation problems requiring quantum circuits of size scaling polynomially in relevant system parameters.

### Evidence
- The approach finds good initial states for dynamics simulation by assembling them in a scattering tree, and it discusses a variety of quantities of chemical interest that can be measured after the quantum simulation of a process.

### Conclusion
- The paper demonstrates a new approach to quantum chemical simulations that avoids the hardness of ground state problems and enables the simulation of a wide range of chemically relevant phenomena.

## Scientific Objects And Mechanisms
### Entities
- Quantum circuits
- Chemical Hamiltonians
- Atomic initial states
- Molecular reactants
- Scattering process

### Materials / Systems
- Not specified.

### Properties
- Not specified.

### Measurements
- Quantum circuits Chemical Hamiltonians Atomic initial states Molecular reactants Scattering process Efficient simulation of chemical systems Production of molecular input states for subsequent dynamical simulation Measurement of reaction rates and time correlation functions

### Conditions
- Quantum circuits Chemical Hamiltonians Atomic initial states Molecular reactants Scattering process Efficient simulation of chemical systems Production of molecular input states for subsequent dynamical simulation Measurement of reaction rates and time correlation functions

### Mechanisms
- Polynomial-size quantum circuit simulation
- Hamiltonian simulation with local Hamiltonians
- State preparation through scattering
- Measurement of dynamical quantities

### Outcomes
- Efficient simulation of chemical systems
- Production of molecular input states for subsequent dynamical simulation
- Measurement of reaction rates and time correlation functions

## Cross-SDL Transfer
### SDL / Domain Tags
- Quantum
- Chemistry
- Physics

### Reasoning Motifs
- Information Representation → State Preparation
- Local Interactions → System Evolution
- Feedback Control → Adaptation

### General Principles
- Control Through Constraints
- Multi-scale Coupling

## Failure Paths / Caveats
- No explicit failure path available in CSV/cross-SDL extraction.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_3cf8ce0004ba.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper is highly structured and presents a clear hypothesis, method, and conclusion. However, the reasoning is complex and involves multiple layers of abstraction, which might require domain expertise for full understanding. The lack of reported failures makes the exploration narrative incomplete.
