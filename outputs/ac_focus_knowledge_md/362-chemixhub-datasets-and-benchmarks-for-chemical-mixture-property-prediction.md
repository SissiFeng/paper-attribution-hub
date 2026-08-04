# CheMixHub: Datasets and Benchmarks for Chemical Mixture Property Prediction

## Metadata
- Paper ID: `acfocus_18f51cffd4a7`
- Cross-SDL ID: `acgold_f337928a7b03`
- DOI: 10.48550/arxiv.2506.12231
- URL: https://arxiv.org/html/2506.12231v1
- Year: 2025
- Authors: Ella Miray Rajaonson1,2
Mahyar Rajabi Kochi1
Luis Martin Mejía Mendoza3
Seyed Mohamad Moosavi1,2
Benjamin Sanchez-Lengeling1,2
- Venue: arxiv
- Category: Preprint
- Peer reviewed: Non Peer Reviewed
- AC members: Mohamad Moosavi, Benjamin Sanchez
- AC programs: Collaborative Funding Opportunity_Mohamad Moosavi_2024-25
- AC membership status: AC Full Member, AC Full Member
- Flags: acknowledges_ac=checked, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.78
- Missing: source_summary, hardware, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
Not specified in CSV.

## Abstract
CheMixHub: Datasets and Benchmarks for Chemical
Mixture Property Prediction
Ella Miray Rajaonson1,2
Mahyar Rajabi Kochi1
Luis Martin Mejía Mendoza3
Seyed Mohamad Moosavi1,2
Benjamin Sanchez-Lengeling1,2
ben.sanchez@utoronto.ca
1 University of Toronto, Canada
2 Vector Institute for Artificial Intelligence, Canada
3 Clean Energy Innovation Research Center, National Research Council, Canada
Abstract
Developing improved predictive models for multi-molecular systems is crucial, as
nearly every chemical product used results from a mixture of chemicals. While
being a vital part of the industry pipeline, the chemical mixture space remains
relatively unexplored by the Machine Learning (ML) community. In this paper,
we introduce CheMixHub, a holistic benchmark for molecular mixtures spanning
a corpus of 11 chemical mixtures property prediction tasks. With applications
ranging from drug delivery formulations to battery electrolytes, CheMixHub cur-
rently totals approximately 500k data points gathered and curated from 7 publicly
available datasets. We devise various data splitting techniques to assess context-
specific generalization and model robustness, providing a foundation for the de-
velopment of predictive models for chemical mixture properties. Furthermore,
we map out the modelling space of deep learning models for chemical mixtures,
establishing initial benchmarks for the community. This dataset has the potential
to accelerate chemical mixture development, encompassing reformulation, opti-
mization, and discovery. The dataset and code for the benchmarks can be found at:
https://github.com/chemcognition-lab/chemixhub
1
Introduction
Mixtures of molecules are integral to our daily experiences: from the perfumes we smell [59] to
the remedies we take [3, 75]. Understanding the interactions and behaviors of molecular mixtures
is therefore essential for advancements in biochemistry [17], drug discovery [3] and environmental
science [24]. Mixtures are particularly appealing be

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Introduced CheMixHub, a benchmark for molecular mixtures spanning 11 chemical mixtures property prediction tasks, using various data splitting techniques to assess context-specific generalization and model robustness.

### Problem
- Developing improved predictive models for multi-molecular systems, which is crucial for various chemical industries but remains relatively unexplored in the Machine Learning (ML) community.

### Hypothesis
- A holistic benchmark for molecular mixtures can facilitate the development of predictive models for chemical mixture properties.

### Evidence
- CheMixHub provides approximately 500k data points gathered from 7 publicly available datasets, with applications ranging from drug delivery formulations to battery electrolytes.

### Conclusion
- CheMixHub has the potential to accelerate chemical mixture development, encompassing reformulation, optimization, and discovery.

## Scientific Objects And Mechanisms
### Entities
- Chemical mixtures
- Molecular representations
- Deep learning models

### Materials / Systems
- CheMixHub provides approximately 500k data points gathered from 7 publicly available datasets, with applications ranging from drug delivery formulations to battery electrolytes.

### Properties
- CheMixHub: Datasets and Benchmarks for Chemical Mixture Property Prediction Introduced CheMixHub, a benchmark for molecular mixtures spanning 11 chemical mixtures property prediction tasks, using various data splitting techniques to assess context-specific generalization and model robustness.

### Measurements
- CheMixHub: Datasets and Benchmarks for Chemical Mixture Property Prediction Introduced CheMixHub, a benchmark for molecular mixtures spanning 11 chemical mixtures property prediction tasks, using various data splitting techniques to assess context-specific generalization and model robustness.

### Conditions
- Not specified.

### Mechanisms
- Data curation and standardization
- Permutation invariant set functions
- Predictive modeling using ML

### Outcomes
- Enabling systematic exploration of research questions
- Establishing initial benchmarks for the community
- Accelerating chemical mixture development

## Cross-SDL Transfer
### SDL / Domain Tags
- Chemistry
- Artificial Intelligence & Data Science

### Reasoning Motifs
- Data aggregation → Property prediction
- Model robustness → Generalization capability
- Permutation invariance → Accurate mixture representation

### General Principles
- Multi-scale coupling
- Emergent order
- Control through constraints

## Failure Paths / Caveats
- success: Incorporating physics-based constraints into ML models for property prediction. Evidence: Incorporating known physical or chemical constraints into ML models can improve accuracy and generalizability of model predictions.
- partial: Exploring transfer learning capabilities of models within and across datasets. Evidence: Models initially trained to predict highly non-linear properties perform well when fine-tuned to predict less complex properties, but not vice versa.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_f337928a7b03.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper provides a structured approach to introducing a new benchmark for chemical mixture property prediction. However, some details on the underlying mechanisms and principles could be further elaborated.
