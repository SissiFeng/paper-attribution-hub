# Ranking over Regression for Bayesian Optimization and Molecule Selection

## Metadata
- Paper ID: `acfocus_0104b2455fa6`
- Cross-SDL ID: `acgold_aa6fc8d0e4a3`
- DOI: 10.48550/arxiv.2410.09290
- URL: https://arxiv.org/abs/2410.09290
- Year: 2024
- Authors: Tom G, Lo S, Corapi S, Aspuru-Guzik A, Sanchez-Lengeling B
- Venue: arxiv
- Category: Preprint
- Peer reviewed: Non Peer Reviewed
- AC members: Alán Aspuru-Guzik
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.72
- Missing: source_summary, hardware, measurements, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
Not specified in CSV.

## Abstract
Ranking over Regression for Bayesian Optimization
and Molecule Selection
Gary Tom
University of Toronto
Vector Institute for Artificial Intelligence
Toronto, ON, Canada
gtom@cs.utoronto.ca
Stanley Lo
University of Toronto
Vector Institute for Artificial Intelligence
Toronto, ON, Canada
Samantha Corapi
University of Toronto
Vector Institute for Artificial Intelligence
Toronto, ON, Canada
Alán Aspuru-Guzik∗
University of Toronto
Vector Institute for Artificial Intelligence
Toronto, ON, Canada
alan@aspuru.com
Benjamin Sanchez-Lengeling
University of Toronto
Vector Institute for Artificial Intelligence
Toronto, ON, Canada
ben.sanchez@utoronto.ca
Abstract
Bayesian optimization (BO) has become an indispensable tool for autonomous
decision-making across diverse applications from autonomous vehicle control to
accelerated drug and materials discovery. With the growing interest in self-driving
laboratories, BO of chemical systems is crucial for machine learning (ML) guided
experimental planning. Typically, BO employs a regression surrogate model to pre-
dict the distribution of unseen parts of the search space. However, for the selection
of molecules, picking the top candidates with respect to a distribution, the relative
ordering of their properties may be more important than their exact values. In
this paper, we introduce Rank-based Bayesian Optimization (RBO), which utilizes
a ranking model as the surrogate. We present a comprehensive investigation of
RBO’s optimization performance compared to conventional BO on various chemi-
cal datasets. Our results demonstrate similar or improved optimization performance
using ranking models, particularly for datasets with rough structure-property land-
scapes and activity cliffs. Furthermore, we observe a high correlation between the
surrogate ranking ability and BO performance, and this ability is maintained even
at early iterations of BO optimization when using ranking surrogate models. We
conclude that RBO is an effective alternati

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Comparative analysis of RBO and conventional BO on various chemical datasets, utilizing deep learning ranking models and traditional regression models as surrogates

### Problem
- Bayesian optimization (BO) of chemical systems for molecular discovery, where the relative ordering of molecular properties may be more important than their exact values

### Hypothesis
- Rank-based Bayesian Optimization (RBO) using a ranking model as the surrogate will demonstrate similar or improved optimization performance compared to conventional regression-based BO

### Evidence
- Results demonstrate higher BO-AUC scores for RBO, indicating faster and better optimization performance, especially on datasets with rough structure-property landscapes and activity cliffs

### Conclusion
- RBO is an effective alternative to regression-based BO, particularly for optimizing novel chemical compounds

## Scientific Objects And Mechanisms
### Entities
- Molecular properties
- Ranking models
- Regression models

### Materials / Systems
- Ranking over Regression for Bayesian Optimization and Molecule Selection Comparative analysis of RBO and conventional BO on various chemical datasets, utilizing deep learning ranking models and traditional regression models as surrogates Results demonstrate higher BO-AUC scores for RBO, indicating faster and better optimization performance, especially on datasets with rough structure-property landscapes and activity cliffs Molecular properties Ranking models Regression models Ranking models enable faster identification of top-performing molecules Regression models struggle with rough datasets and activity cliffs

### Properties
- Ranking over Regression for Bayesian Optimization and Molecule Selection Comparative analysis of RBO and conventional BO on various chemical datasets, utilizing deep learning ranking models and traditional regression models as surrogates Results demonstrate higher BO-AUC scores for RBO, indicating faster and better optimization performance, especially on datasets with rough structure-property landscapes and activity cliffs Molecular properties Ranking models Regression models Ranking models enable faster identification of top-performing molecules Regression models struggle with rough datasets and activity cliffs

### Measurements
- Not specified.

### Conditions
- Not specified.

### Mechanisms
- Ranking model training to learn relative ordering of molecules
- Regression model training to predict exact target values of molecules

### Outcomes
- Ranking models enable faster identification of top-performing molecules
- Regression models struggle with rough datasets and activity cliffs

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Chemistry

### Reasoning Motifs
- Robustness to noise → Improved optimization performance
- Roughness in data → Decreased predictive accuracy

### General Principles
- Optimization performance is enhanced by models that are robust to data noise and variability

## Failure Paths / Caveats
- success: Applying RBO to chemical datasets with varying degrees of roughness Evidence: RBO demonstrated similar or improved optimization performance compared to conventional BO
- success: Using ranking models on datasets with activity cliffs Evidence: Ranking models showed superior performance on datasets with activity cliffs

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_aa6fc8d0e4a3.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper presents a clear hypothesis and method, with a structured comparison of RBO and conventional BO. However, the extraction of layer3_motifs and layer4_principles required some inference based on the paper's findings and the general principles of optimization in noisy or variable datasets.
