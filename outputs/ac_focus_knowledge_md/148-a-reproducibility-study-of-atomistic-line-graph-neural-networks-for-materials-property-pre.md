# A reproducibility study of atomistic line graph neural networks for materials property prediction

## Metadata
- Paper ID: `acfocus_0c8bdc6e6fee`
- Cross-SDL ID: `acgold_7dcc1c51257d`
- DOI: 10.1039/d4dd00064a
- URL: https://pubs.rsc.org/en/content/articlelanding/2024/dd/d4dd00064a
- Year: 2024
- Authors: Li K, DeCost B, Choudhary K, Hattrick-Simpers J
- Venue: Digital Discovery
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Jason Hattrick-Simpers
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=checked, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.8
- Missing: hardware, measurements, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
This study analyzes the reproducibility of a graph neural network model for atomistic prediction tasks in materials science, finding good agreement with the original results and highlighting the benefits of open data and code practices, while suggesting further improvements for reproducibility.

## Abstract
Use of machine learning has been increasingly popular in materials science as data-driven materials discovery is becoming the new paradigm. Reproducibility of findings is paramount for promoting transparency and accountability in research and building trust in the scientific community. Here we conduct a reproducibility analysis of the work by K. Choudhary and B. Brian [npj Comput. Mater., 7, 2021, 185], in which a new graph neural network architecture was developed with improved performance on multiple atomistic prediction tasks. We examine the reproducibility for the model performance on 29 regression tasks and for an ablation analysis of the graph neural network layers. We find that the reproduced results generally exhibit a good quantitative agreement with the initial study, despite minor disparities in model performance and training efficiency that may be resulting from factors such as hardware difference and stochasticity involved in model training and data splits. The ease of conducting these reproducibility experiments confirms the great benefits of open data and code practices to which the initial work adhered. We also discuss some further enhancements in reproducible practices such as code and data archiving and providing data identifiers used in dataset splits.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Conducting a reproducibility analysis of the ALIGNN model performance on 29 regression tasks and an ablation analysis of the graph neural network layers, using the same datasets and model training procedures as the original study.

### Problem
- Assessing the reproducibility of findings in machine learning for materials property prediction, specifically focusing on the Atomistic Line Graph Neural Network (ALIGNN) model.

### Hypothesis
- The ALIGNN model performance on multiple atomistic prediction tasks can be reliably reproduced.

### Evidence
- The reproduced results generally exhibit good quantitative agreement with the initial study, with minor disparities in model performance and training efficiency.

### Conclusion
- The ALIGNN model performance and ablation analysis are largely reproducible, confirming the benefits of open data and code practices in facilitating reproducibility in computational materials science.

## Scientific Objects And Mechanisms
### Entities
- ALIGNN model
- Graph Neural Networks (GNNs)
- JARVIS-DFT dataset
- Python environment
- Deep Graph Library (DGL)

### Materials / Systems
- A reproducibility study of atomistic line graph neural networks for materials property prediction This study analyzes the reproducibility of a graph neural network model for atomistic prediction tasks in materials science, finding good agreement with the original results and highlighting the benefits of open data and code practices, while suggesting further improvements for reproducibility.
- Use of machine learning has been increasingly popular in materials science as data-driven materials discovery is becoming the new paradigm.

### Properties
- A reproducibility study of atomistic line graph neural networks for materials property prediction This study analyzes the reproducibility of a graph neural network model for atomistic prediction tasks in materials science, finding good agreement with the original results and highlighting the benefits of open data and code practices, while suggesting further improvements for reproducibility.

### Measurements
- Not specified.

### Conditions
- Not specified.

### Mechanisms
- Data-driven materials discovery
- Graph neural network architecture development
- Model training and evaluation
- Ablation analysis of neural network layers

### Outcomes
- Improved performance on multiple atomistic prediction tasks
- Reproducibility of model performance
- Insights into the contributions of individual model components

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Materials Science

### Reasoning Motifs
- Open data and code practices → Enhanced reproducibility
- Model performance variation → Training efficiency and hardware configuration sensitivity

### General Principles
- Transparency and accountability in research
- Adaptation to hardware and software environment variations

## Failure Paths / Caveats
- success: Reproducing the ALIGNN model performance on 29 regression tasks from the JARVIS-DFT dataset. Evidence: The reproduced results generally exhibit a good quantitative agreement with the initial study.
- partial: Reproducing the ablation analysis of the ALIGNN model layers. Evidence: Similar effects of the layers on the model performance are reproduced, but with a maximum deviation of 6% from the original value.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_7dcc1c51257d.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper provides a clear structure for reproducibility analysis, but some details on the specific challenges encountered during the reproduction process could be more explicit.
