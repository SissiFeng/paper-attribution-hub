# Kernel based quantum machine learning at record rate : Many-body distribution functionals as compact representations

## Metadata
- Paper ID: `acfocus_7e3bbab8a2cd`
- Cross-SDL ID: `acgold_387df941d51a`
- DOI: 10.48550/arxiv.2303.16312
- URL: https://arxiv.org/abs/2303.16312
- Year: 2023
- Authors: Khan, Danish; Heinen, Stefan; von Lilienfeld, O. Anatole
- Venue: arxiv
- Category: Preprint
- Peer reviewed: Non Peer Reviewed
- AC members: Anatole von Lilienfeld
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.9
- Missing: hardware
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
The study introduces compact, linear-scaling quantum machine learning representations based on atomic Gaussian many-body distribution functionals, achieving competitive predictive performance and data efficiency for chemical property prediction while significantly reducing computational costs compared to high-dimensional feature mappings.

## Abstract
The feature vector mapping used to represent chemical systems is a key factor governing the superior data-efficiency of kernel based quantum machine learning (QML) models applicable throughout chemical compound space. Unfortunately, the most accurate representations require a high dimensional feature mapping, thereby imposing a considerable computational burden on model training and use. We introduce compact yet accurate, linear scaling QML representations based on atomic Gaussian many-body distribution functionals (MBDF), and their derivatives. Weighted density functions (DF) of MBDF values are used as global representations which are constant in size, i.e.~invariant with respect to the number of atoms. We report predictive performance and training data efficiency that is competitive with state of the art for two diverse datasets of organic molecules, QM9 and QMugs. Generalization capability has been investigated for atomization energies, HOMO-LUMO eigenvalues and gap, internal energies at 0 K, zero point vibrational energies, dipole moment norm, static isotropic polarizability, and heat capacity as encoded in QM9. MBDF based QM9 performance lowers the optimal Pareto front spanned between sampling and training cost to compute node minutes,~effectively sampling chemical compound space with chemical accuracy at a sampling rate of $\sim 48$ molecules per core second.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Introduced MBDF and density of functionals (DF) representations, tested on QM9 and QMugs datasets using kernel ridge regression (KRR).

### Problem
- The high dimensional feature mapping required for accurate quantum machine learning (QML) models imposes a significant computational burden.

### Hypothesis
- Compact yet accurate linear scaling QML representations based on atomic Gaussian many-body distribution functionals (MBDF) can achieve competitive predictive performance and training data efficiency.

### Evidence
- MBDF/DF representations demonstrated predictive performance competitive with state-of-the-art, with significantly reduced computational cost and time complexity.

### Conclusion
- MBDF/DF representations can accurately describe any atom/molecule using a minimal number of discrete elements, thereby reducing QML training and prediction times by multiple orders of magnitude for small and large molecules.

## Scientific Objects And Mechanisms
### Entities
- Atomic Gaussian many-body distribution functionals (MBDF)
- Density of functionals (DF)

### Materials / Systems
- We report predictive performance and training data efficiency that is competitive with state of the art for two diverse datasets of organic molecules, QM9 and QMugs.
- MBDF based QM9 performance lowers the optimal Pareto front spanned between sampling and training cost to compute node minutes,~effectively sampling chemical compound space with chemical accuracy at a sampling rate of $\sim 48$ molecules per core second.

### Properties
- Kernel based quantum machine learning at record rate : Many-body distribution functionals as compact representations The study introduces compact, linear-scaling quantum machine learning representations based on atomic Gaussian many-body distribution functionals, achieving competitive predictive performance and data efficiency for chemical property prediction while significantly reducing computational costs compared to high-dimensional feature mappings.
- MBDF based QM9 performance lowers the optimal Pareto front spanned between sampling and training cost to compute node minutes,~effectively sampling chemical compound space with chemical accuracy at a sampling rate of $\sim 48$ molecules per core second.

### Measurements
- Introduced MBDF and density of functionals (DF) representations, tested on QM9 and QMugs datasets using kernel ridge regression (KRR).

### Conditions
- Kernel based quantum machine learning at record rate : Many-body distribution functionals as compact representations The study introduces compact, linear-scaling quantum machine learning representations based on atomic Gaussian many-body distribution functionals, achieving competitive predictive performance and data efficiency for chemical property prediction while significantly reducing computational costs compared to high-dimensional feature mappings.
- MBDF based QM9 performance lowers the optimal Pareto front spanned between sampling and training cost to compute node minutes,~effectively sampling chemical compound space with chemical accuracy at a sampling rate of $\sim 48$ molecules per core second.
- MBDF/DF representations demonstrated predictive performance competitive with state-of-the-art, with significantly reduced computational cost and time complexity.

### Mechanisms
- Compact representation of chemical systems through functionals of analytical weighted many-body distributions in interatomic distances and angles
- Global molecular fingerprint generation through weighted density estimations of MBDF

### Outcomes
- Reduced computational burden and increased data efficiency in QML models
- Achieved competitive predictive performance with significantly reduced representation size

## Cross-SDL Transfer
### SDL / Domain Tags
- Quantum
- Artificial Intelligence & Data Science
- Chemistry

### Reasoning Motifs
- Compactness → Efficiency
- Globality → Scalability

### General Principles
- Maximizing Information Content with Minimal Complexity
- Scalability Through Global Representations

## Failure Paths / Caveats
- success: Optimization of hyperparameters for MBDF and DF representations on QM7 subset Evidence: Optimized hyperparameters led to improved predictive performance on QM9 and QMugs datasets.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_387df941d51a.json`
- Cross-SDL extraction quality: 0.9
- Notes: The paper presents a structured approach to developing and validating compact QML representations, with clear hypotheses, methods, and results. The reasoning is explicit and well-documented, allowing for high-confidence extraction.
