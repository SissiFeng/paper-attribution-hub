# Towards equilibrium molecular conformation generation with GFlowNets

## Metadata
- Paper ID: `acfocus_924cc15ea5fd`
- Cross-SDL ID: `acgold_c0b1ddb2e676`
- DOI: 10.1039/d4dd00023d
- URL: https://pubs.rsc.org/en/content/articlelanding/2024/dd/d4dd00023d
- Year: 2024
- Authors: Volokhova A, Koziarski M, Hernández-García A, Liu CH, Miret S, Lemos P, Thiede L, Yan Z, Aspuru-Guzik A, Bengio Y
- Venue: Digital Discovery
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Alán Aspuru-Guzik
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.8
- Missing: hardware, measurements, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
This paper proposes using GFlowNets to sample diverse, low-energy molecular conformations from the Boltzmann distribution, enabling accurate reproduction of molecular potential energy surfaces and compatibility with various energy estimation methods.

## Abstract
Sampling diverse, thermodynamically feasible molecular conformations plays a crucial role in predicting properties of a molecule. In this paper we propose to use GFlowNets for sampling conformations of small molecules from the Boltzmann distribution, as determined by the molecule's energy. The proposed approach can be used in combination with energy estimation methods of different fidelity and discovers a diverse set of low-energy conformations for drug-like molecules. We demonstrate that GFlowNets can reproduce molecular potential energy surfaces by sampling proportionally to the Boltzmann distribution.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Use of GFlowNet for sampling molecular equilibrium conformations from the Boltzmann distribution, focusing on torsion angles of a molecule

### Problem
- Sampling diverse, thermodynamically feasible molecular conformations to predict properties of a molecule

### Hypothesis
- GFlowNet can sample conformations of small molecules from the Boltzmann distribution as determined by the molecule’s energy

### Evidence
- The proposed approach can sample molecular conformations from the Boltzmann distribution, producing diverse, low-energy conformations for a wide range of drug-like molecules with varying numbers of torsion angles

### Conclusion
- GFlowNet can reproduce molecular potential energy surfaces by sampling proportionally to the Boltzmann distribution

## Scientific Objects And Mechanisms
### Entities
- Molecular conformations
- Torsion angles
- Boltzmann distribution
- GFlowNet

### Materials / Systems
- Sampling diverse, thermodynamically feasible molecular conformations plays a crucial role in predicting properties of a molecule.
- In this paper we propose to use GFlowNets for sampling conformations of small molecules from the Boltzmann distribution, as determined by the molecule's energy.
- The proposed approach can be used in combination with energy estimation methods of different fidelity and discovers a diverse set of low-energy conformations for drug-like molecules.

### Properties
- Towards equilibrium molecular conformation generation with GFlowNets This paper proposes using GFlowNets to sample diverse, low-energy molecular conformations from the Boltzmann distribution, enabling accurate reproduction of molecular potential energy surfaces and compatibility with various energy estimation methods.
- Sampling diverse, thermodynamically feasible molecular conformations plays a crucial role in predicting properties of a molecule.
- In this paper we propose to use GFlowNets for sampling conformations of small molecules from the Boltzmann distribution, as determined by the molecule's energy.
- The proposed approach can be used in combination with energy estimation methods of different fidelity and discovers a diverse set of low-energy conformations for drug-like molecules.
- We demonstrate that GFlowNets can reproduce molecular potential energy surfaces by sampling proportionally to the Boltzmann distribution.

### Measurements
- Not specified.

### Conditions
- Not specified.

### Mechanisms
- Sampling from an unnormalized probability density represented as a reward function over the sample space
- Parameterization of forward and backward policies with a multilayer perceptron (MLP) for mixture of von Mises distribution
- Training GFlowNets with the Trajectory Balance objective

### Outcomes
- Diverse, low-energy conformations for highly flexible drug-like molecules
- Reproduction of molecular potential energy surfaces
- Combination with energy estimation methods of different fidelity

## Cross-SDL Transfer
### SDL / Domain Tags
- Chemistry
- Artificial Intelligence & Data Science

### Reasoning Motifs
- Information Integration → Diverse Sampling
- Model Complexity → Sampling Accuracy

### General Principles
- Emergent Order

## Failure Paths / Caveats
- No explicit failure path available in CSV/cross-SDL extraction.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_c0b1ddb2e676.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper presents a novel approach for sampling molecular conformations using GFlowNet, with a clear problem statement, hypothesis, and methodology. However, the reasoning structure is not explicitly broken down into phases, requiring some inference to extract the underlying mechanisms and outcomes.
