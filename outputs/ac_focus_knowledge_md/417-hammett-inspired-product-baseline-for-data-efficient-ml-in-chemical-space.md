# Hammett-Inspired Product Baseline for Data-Efficient Δ-ML in Chemical Space

## Metadata
- Paper ID: `acfocus_8580deac58a1`
- Cross-SDL ID: `acgold_b83a0eb8f82f`
- DOI: 10.1021/acs.jctc.5c00848
- URL: https://pubs.acs.org/doi/abs/10.1021/acs.jctc.5c00848
- Year: 2025
- Authors: V. D. Rakotonirina; M. Bragato; G. Falk von Rudorff; O. A. von Lilienfeld
- Venue: Journal of Chemical Theory and Computation
- Category: Journal Article
- Peer reviewed: Peer Reviewed
- AC members: Anatole von Lilienfeld
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=checked, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.8
- Missing: hardware, measurements, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
A generic coarse-graining Hammett-inspired product (HIP) model is introduced as an effective, data-efficient baseline for machine learning in molecular and materials design, generalizing the Hammett equation to diverse systems and properties and outperforming specialized models in data efficiency after calibration.

## Abstract
Data-hungry machine learning methods have become a new standard to efficiently navigate chemical compound space for molecular and materials design and discovery. Due to the severe scarcity and cost of high-quality experimental or synthetic simulated training data, however, data-acquisition costs can be considerable. Relying on reasonably accurate approximate legacy baseline labels with low computational complexity represents one of the most effective strategies to curb data-needs, e.g. through Δ-, transfer-, or multifidelity learning. A surprisingly effective and data-efficient baseline model is presented in the form of a generic coarse-graining Hammett-inspired product (HIP) Ansatz, generalizing the empirical Hammett equation toward arbitrary systems and properties. Numerical evidence for the applicability of HIP includes solvation free energies of molecules, formation energies of quaternary elpasolite crystals, carbon adsorption energies on heterogeneous catalytic surfaces, HOMO–LUMO gaps of metallorganic complexes, activation energies for S<inf>N</inf>2 reactions, and catalyst–substrate binding energies in cross-coupling reactions. After calibration on the same training sets, HIP yields an effective baseline for improved Δ-machine learning models with superior data-efficiency when compared to previously introduced specialized domain-specific models. © 2025 American Chemical Society

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
- Hammett-Inspired Product Baseline for Data-Efficient Δ-ML in Chemical Space A generic coarse-graining Hammett-inspired product (HIP) model is introduced as an effective, data-efficient baseline for machine learning in molecular and materials design, generalizing the Hammett equation to diverse systems and properties and outperforming specialized models in data efficiency after calibration.
- Data-hungry machine learning methods have become a new standard to efficiently navigate chemical compound space for molecular and materials design and discovery.
- Numerical evidence for the applicability of HIP includes solvation free energies of molecules, formation energies of quaternary elpasolite crystals, carbon adsorption energies on heterogeneous catalytic surfaces, HOMO–LUMO gaps of metallorganic complexes, activation energies for S<inf>N</inf>2 reactions, and catalyst–substrate binding energies in cross-coupling reactions.

### Properties
- Hammett-Inspired Product Baseline for Data-Efficient Δ-ML in Chemical Space A generic coarse-graining Hammett-inspired product (HIP) model is introduced as an effective, data-efficient baseline for machine learning in molecular and materials design, generalizing the Hammett equation to diverse systems and properties and outperforming specialized models in data efficiency after calibration.
- A surprisingly effective and data-efficient baseline model is presented in the form of a generic coarse-graining Hammett-inspired product (HIP) Ansatz, generalizing the empirical Hammett equation toward arbitrary systems and properties.
- © 2025 American Chemical Society The HIP model generalizes the empirical Hammett equation towards arbitrary systems and properties, using a product of two scalars to predict chemical properties.
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
- Materials Science

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
