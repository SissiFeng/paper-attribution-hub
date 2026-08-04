# Occam's razor for AI: Coarse-graining Hammett Inspired Product Ansatz in Chemical Space

## Metadata
- Paper ID: `acfocus_bdd44a54ff55`
- Cross-SDL ID: `acgold_b83a0eb8f82f`
- DOI: 10.48550/arxiv.2305.07010
- URL: https://arxiv.org/abs/2305.07010
- Year: 2023
- Authors: Bragato, Marco; von Rudorff, Guido Falk; von Lilienfeld, O. Anatole
- Venue: arxiv
- Category: Preprint
- Peer reviewed: Non Peer Reviewed
- AC members: Anatole von Lilienfeld
- AC programs: Core Development Grants_Anatole von Lilienfeld_2023-24
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.8
- Missing: hardware, measurements, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
The text introduces the Hammett Inspired Product (HIP) Ansatz as a generic, computationally efficient baseline label that generalizes the Hammett equation for diverse chemical systems and properties, enabling more data-efficient machine learning models for molecular and materials discovery by reducing reliance on costly high-quality training data.

## Abstract
Data-hungry machine learning methods have become a new standard to efficiently navigate chemical compound space for molecular and materials design and discovery. Due to the severe scarcity and cost of high-quality experimental or synthetic simulated training data, however, data-acquisition costs can be considerable. Relying on reasonably accurate approximate baseline labels with low computational complexity represents one of the most effective strategies to curb data-needs, e.g.~through $Δ$-, transfer-, or multi-fidelity learning. We introduce baseline labels in the form of a generic coarse-graining Hammett Inspired Product (HIP) {\em Ansatz} which generalizes the empirical Hammett equation towards arbitrary systems and properties. Numerical evidence for the applicability of HIP includes solvation free energies of molecules, formation energies of quaternary elpasolite crystals, carbon adsorption energies on heterogeneous catalytic surfaces, HOMO-LUMO gaps of metallorganic complexes, and activation energies for S$_\text{N}$2 reactions. After calibration on the same training sets, HIP yields an effective baseline for improved $Δ$-quantum machine learning models with superior data-efficiency when compared to previously introduced specialised domain-specific models.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- The HIP model generalizes the empirical Hammett equation towards arbitrary systems and properties, using a product of two scalars to predict chemical properties.

### Problem
- Data-hungry machine learning methods have limitations due to the scarcity and cost of high-quality experimental or synthetic simulated training data in chemical compound space exploration.

### Hypothesis
- A Hammett-Inspired Product (HIP) model can serve as a reasonably accurate and data-efficient baseline for ∆-machine learning models to curb data-needs.

### Evidence
- Numerical evidence includes solvation free energies, formation energies of crystals, carbon adsorption energies, HOMO-LUMO gaps, activation energies for reactions, and catalyst-substrate binding energies.

### Conclusion
- The HIP model demonstrates broad applicability and data-efficiency across chemically diverse systems, providing a fast and interpretable baseline for exploring chemical compound space.

## Scientific Objects And Mechanisms
### Entities
- Hammett-Inspired Product (HIP) model
- Chemical properties across different systems

### Materials / Systems
- Occam's razor for AI: Coarse-graining Hammett Inspired Product Ansatz in Chemical Space The text introduces the Hammett Inspired Product (HIP) Ansatz as a generic, computationally efficient baseline label that generalizes the Hammett equation for diverse chemical systems and properties, enabling more data-efficient machine learning models for molecular and materials discovery by reducing reliance on costly high-quality training data.
- Data-hungry machine learning methods have become a new standard to efficiently navigate chemical compound space for molecular and materials design and discovery.
- Numerical evidence for the applicability of HIP includes solvation free energies of molecules, formation energies of quaternary elpasolite crystals, carbon adsorption energies on heterogeneous catalytic surfaces, HOMO-LUMO gaps of metallorganic complexes, and activation energies for S$_\text{N}$2 reactions.

### Properties
- Occam's razor for AI: Coarse-graining Hammett Inspired Product Ansatz in Chemical Space The text introduces the Hammett Inspired Product (HIP) Ansatz as a generic, computationally efficient baseline label that generalizes the Hammett equation for diverse chemical systems and properties, enabling more data-efficient machine learning models for molecular and materials discovery by reducing reliance on costly high-quality training data.
- We introduce baseline labels in the form of a generic coarse-graining Hammett Inspired Product (HIP) {\em Ansatz} which generalizes the empirical Hammett equation towards arbitrary systems and properties.
- The HIP model generalizes the empirical Hammett equation towards arbitrary systems and properties, using a product of two scalars to predict chemical properties.
- Hammett-Inspired Product (HIP) model Chemical properties across different systems Improved data-efficiency in machine learning models Effective baseline for ∆-machine learning applications

### Measurements
- Not specified.

### Conditions
- Not specified.

### Mechanisms
- Generalization of Hammett equation for arbitrary systems
- Use of two scalars to predict properties

### Outcomes
- Improved data-efficiency in machine learning models
- Effective baseline for ∆-machine learning applications

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Chemistry

### Reasoning Motifs
- Simplicity → Transferability
- Coarse-graining → Data-efficiency

### General Principles
- parsimony in modeling

## Failure Paths / Caveats
- No explicit failure path available in CSV/cross-SDL extraction.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_b83a0eb8f82f.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper presents a clear hypothesis, method, and conclusion. However, the exploration narrative is inferred from the paper's structure rather than explicitly stated.
