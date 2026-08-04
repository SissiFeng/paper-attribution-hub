# Towards the prediction of drug solubility in binary solvent mixtures at various temperatures using machine learning

## Metadata
- Paper ID: `acfocus_23445dadadcf`
- Cross-SDL ID: `not matched`
- DOI: 10.1186/s13321-024-00911-3
- URL: https://link.springer.com/article/10.1186/s13321-024-00911-3
- Year: 2024
- Authors: Bao Z, Tom G, Cheng A, Watchorn J, Aspuru-Guzik A, Allen C
- Venue: Journal of Cheminformatics
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Christine Allen, Alán Aspuru-Guzik, Zeqing Bao, Jeff Watchorn
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance, AC Full Member, AC Governance, AC Staff, AC Staff
- Flags: acknowledges_ac=checked, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.54
- Missing: hardware, evidence, properties, measurements, mechanisms, cross_sdl_match
- Notes: No cross-SDL extraction matched this paper; fields are derived from CSV only.; Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
This study presents machine learning models trained on a large, diverse dataset of small molecule solubility in binary solvent mixtures across various temperatures, achieving accurate predictions and providing open access to the dataset and code to advance drug development and formulation.

## Abstract
Abstract: Drug solubility is an important parameter in the drug development process, yet it is often tedious and challenging to measure, especially for expensive drugs or those available in small quantities. To alleviate these challenges, machine learning (ML) has been applied to predict drug solubility as an alternative approach. However, the majority of existing ML research has focused on the predictions of aqueous solubility and/or solubility at specific temperatures, which restricts the model applicability in pharmaceutical development. To bridge this gap, we compiled a dataset of 27,000 solubility datapoints, including solubility of small molecules measured in a range of binary solvent mixtures under various temperatures. Next, a panel of ML models were trained on this dataset with their hyperparameters tuned using Bayesian optimization. The resulting top-performing models, both gradient boosted decision trees (light gradient boosting machine and extreme gradient boosting), achieved mean absolute errors (MAE) of 0.33 for LogS (S in g/100 g) on the holdout set. These models were further validated through a prospective study, wherein the solubility of four drug molecules were predicted by the models and then validated with in-house solubility experiments. This prospective study demonstrated that the models accurately predicted the solubility of solutes in specific binary solvent mixtures under different temperatures, especially for drugs whose features closely align within the solutes in the dataset (MAE < 0.5 for LogS). To support future research and facilitate advancements in the field, we have made the dataset and code openly available. Scientific contribution Our research advances the state-of-the-art in predicting solubility for small molecules by leveraging ML and a uniquely comprehensive dataset. Unlike existing ML studies that predominantly focus on solubility in aqueous solvents at fixed temperatures, our work enables prediction of drug solubility in a variety of binary solvent mixtures over a broad temperature range, providing practical insights on the modeling of solubility for realistic pharmaceutical applications. These advancements along with the open access dataset and code support significant steps in the drug development process including new molecule discovery, drug analysis and formulation. Graphical Abstract: (Figure presented.)

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- This study presents machine learning models trained on a large, diverse dataset of small molecule solubility in binary solvent mixtures across various temperatures, achieving accurate predictions and providing open access to the dataset and code to advance drug development and formulation.

### Problem
- Not specified by cross-SDL extraction.

### Hypothesis
- Not specified by cross-SDL extraction.

### Evidence
- Not specified by cross-SDL extraction.

### Conclusion
- Not specified by cross-SDL extraction.

## Scientific Objects And Mechanisms
### Entities
- Artificial Intelligence & Data Science
- Chemistry

### Materials / Systems
- Towards the prediction of drug solubility in binary solvent mixtures at various temperatures using machine learning This study presents machine learning models trained on a large, diverse dataset of small molecule solubility in binary solvent mixtures across various temperatures, achieving accurate predictions and providing open access to the dataset and code to advance drug development and formulation.
- To bridge this gap, we compiled a dataset of 27,000 solubility datapoints, including solubility of small molecules measured in a range of binary solvent mixtures under various temperatures.
- These models were further validated through a prospective study, wherein the solubility of four drug molecules were predicted by the models and then validated with in-house solubility experiments.

### Properties
- Not specified.

### Measurements
- Not specified.

### Conditions
- Unlike existing ML studies that predominantly focus on solubility in aqueous solvents at fixed temperatures, our work enables prediction of drug solubility in a variety of binary solvent mixtures over a broad temperature range, providing practical insights on the modeling of solubility for realistic pharmaceutical applications.

### Mechanisms
- Not specified.

### Outcomes
- Therapeutics
- Formulations

## Cross-SDL Transfer
### SDL / Domain Tags
- SDL 5 - Formulations
- Artificial Intelligence & Data Science
- Chemistry
- Therapeutics
- Formulations

### Reasoning Motifs
- Not specified by cross-SDL extraction.

### General Principles
- Not specified by cross-SDL extraction.

## Failure Paths / Caveats
- No explicit failure path available in CSV/cross-SDL extraction.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `not available`
- Cross-SDL extraction quality: not available
- Notes: No additional notes.
