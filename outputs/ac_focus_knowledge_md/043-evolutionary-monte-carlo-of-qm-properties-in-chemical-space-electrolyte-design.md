# Evolutionary Monte Carlo of QM properties in chemical space: Electrolyte design

## Metadata
- Paper ID: `acfocus_a436e35efb8e`
- Cross-SDL ID: `acgold_1e9ddd3dc480`
- DOI: 10.48550/arxiv.2307.15563
- URL: https://arxiv.org/abs/2307.15563
- Year: 2023
- Authors: Karandashev, Konstantin; Weinreich, Jan; Heinen, Stefan; Arrieta, Daniel Jose Arismendi; von Rudorff, Guido Falk; Hermansson, Kersti; von Lilienfeld, O. Anatole
- Venue: arxiv
- Category: Preprint
- Peer reviewed: Non Peer Reviewed
- AC members: Anatole von Lilienfeld
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=checked, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.86
- Missing: hardware, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
The paper introduces MOSAiCS, an Evolutionary Monte Carlo algorithm that efficiently optimizes molecular properties by balancing exploration and exploitation, outperforming existing datasets in tasks like minimizing solvation energy and maximizing dipole moment, and discusses future acceleration using machine learning.

## Abstract
Optimizing a target function over the space of organic molecules is an important problem appearing in many fields of applied science, but also a very difficult one due to the vast number of possible molecular systems. We propose an Evolutionary Monte Carlo algorithm for solving such problems which is capable of straightforwardly tuning both exploration and exploitation characteristics of an optimization procedure while retaining favourable properties of genetic algorithms. The method, dubbed MOSAiCS (Metropolis Optimization by Sampling Adaptively in Chemical Space), is tested on problems related to optimizing components of battery electrolytes, namely minimizing solvation energy in water or maximizing dipole moment while enforcing a lower bound on the HOMO-LUMO gap; optimization was done over sets of molecular graphs inspired by QM9 and Electrolyte Genome Project (EGP) datasets. MOSAiCS reliably generated molecular candidates with good target quantity values, which were in most cases better than the ones found in QM9 or EGP. While the optimization results presented in this work sometimes required up to $10^{6}$ QM calculations and were thus only feasible thanks to computationally efficient ab initio approximations of properties of interest, we discuss possible strategies for accelerating MOSAiCS using machine learning approaches.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Implementing an Evolutionary Monte Carlo algorithm named MOSAiCS to optimize components of battery electrolytes by minimizing solvation energy in water or maximizing dipole moment while enforcing a lower bound on the HOMO-LUMO gap

### Problem
- Optimizing target functions over chemical space for applications such as lithium battery electrolyte design

### Hypothesis
- An Evolutionary Monte Carlo algorithm can effectively optimize molecular properties within chemical space

### Evidence
- MOSAiCS reliably generated molecular candidates with good target quantity values, which were in most cases better than the ones found in QM9 or EGP

### Conclusion
- MOSAiCS is an effective algorithm for optimization in chemical space with potential applications in battery electrolyte design and other molecular optimization problems

## Scientific Objects And Mechanisms
### Entities
- Molecular graphs
- HOMO-LUMO gap
- Dipole moment
- Solvation energy

### Materials / Systems
- Evolutionary Monte Carlo of QM properties in chemical space: Electrolyte design The paper introduces MOSAiCS, an Evolutionary Monte Carlo algorithm that efficiently optimizes molecular properties by balancing exploration and exploitation, outperforming existing datasets in tasks like minimizing solvation energy and maximizing dipole moment, and discusses future acceleration using machine learning.
- Optimizing a target function over the space of organic molecules is an important problem appearing in many fields of applied science, but also a very difficult one due to the vast number of possible molecular systems.
- The method, dubbed MOSAiCS (Metropolis Optimization by Sampling Adaptively in Chemical Space), is tested on problems related to optimizing components of battery electrolytes, namely minimizing solvation energy in water or maximizing dipole moment while enforcing a lower bound on the HOMO-LUMO gap; optimization was done over sets of molecular graphs inspired by QM9 and Electrolyte Genome Project (EGP) datasets.

### Properties
- Evolutionary Monte Carlo of QM properties in chemical space: Electrolyte design The paper introduces MOSAiCS, an Evolutionary Monte Carlo algorithm that efficiently optimizes molecular properties by balancing exploration and exploitation, outperforming existing datasets in tasks like minimizing solvation energy and maximizing dipole moment, and discusses future acceleration using machine learning.
- We propose an Evolutionary Monte Carlo algorithm for solving such problems which is capable of straightforwardly tuning both exploration and exploitation characteristics of an optimization procedure while retaining favourable properties of genetic algorithms.
- The method, dubbed MOSAiCS (Metropolis Optimization by Sampling Adaptively in Chemical Space), is tested on problems related to optimizing components of battery electrolytes, namely minimizing solvation energy in water or maximizing dipole moment while enforcing a lower bound on the HOMO-LUMO gap; optimization was done over sets of molecular graphs inspired by QM9 and Electrolyte Genome Project (EGP) datasets.
- While the optimization results presented in this work sometimes required up to $10^{6}$ QM calculations and were thus only feasible thanks to computationally efficient ab initio approximations of properties of interest, we discuss possible strategies for accelerating MOSAiCS using machine learning approaches.
- Implementing an Evolutionary Monte Carlo algorithm named MOSAiCS to optimize components of battery electrolytes by minimizing solvation energy in water or maximizing dipole moment while enforcing a lower bound on the HOMO-LUMO gap MOSAiCS reliably generated molecular candidates with good target quantity values, which were in most cases better than the ones found in QM9 or EGP Molecular graphs HOMO-LUMO gap Dipole moment Solvation energy Optimized molecular candidates with improved target property values

### Measurements
- The method, dubbed MOSAiCS (Metropolis Optimization by Sampling Adaptively in Chemical Space), is tested on problems related to optimizing components of battery electrolytes, namely minimizing solvation energy in water or maximizing dipole moment while enforcing a lower bound on the HOMO-LUMO gap; optimization was done over sets of molecular graphs inspired by QM9 and Electrolyte Genome Project (EGP) datasets.

### Conditions
- Not specified.

### Mechanisms
- Metropolis Optimization by Sampling Adaptively in Chemical Space (MOSAiCS)
- Markov chain Monte Carlo simulations
- Elementary mutations and crossover moves to propose new molecular configurations

### Outcomes
- Optimized molecular candidates with improved target property values

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Chemistry
- Energy Storage

### Reasoning Motifs
- Diversity → Robustness
- Constraint → Stability
- Feedback → Adaptation

### General Principles
- Multi-scale Coupling
- Control Through Constraints

## Failure Paths / Caveats
- partial: Optimizing dipole moment under strong HOMO-LUMO gap constraint in QM9* Evidence: Simulations agreed less frequently on candidate molecules compared to other optimization problems
- success: Using non-zero αb to increase diversity of molecules encountered during simulations Evidence: Increasing αb tended to increase diversity of molecules encountered during the simulations, but this was mainly done by considering more molecules in regions of chemical space with larger values of solvation energy

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_1e9ddd3dc480.json`
- Cross-SDL extraction quality: 0.7
- Notes: The paper presents a structured approach to optimizing molecular properties using an Evolutionary Monte Carlo algorithm, but some details of the reasoning structure had to be inferred from the experimental setup and results discussion
