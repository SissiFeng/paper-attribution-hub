# Beyond Molecular Structure: Critically Assessing Machine Learning for Designing Organic Photovoltaic Materials and Devices

## Metadata
- Paper ID: `acfocus_7f55aad17df0`
- Cross-SDL ID: `acgold_77651ccbaa92`
- DOI: 10.26434/chemrxiv-2024-d20px-v2
- URL: https://chemrxiv.org/doi/full/10.26434/chemrxiv-2024-d20px-v2
- Year: 2024
- Authors: Seifrid M, Lo S, Choi DG, Tom G, Le ML, Li K, Sankar R, Vuong H-T, Wakidi H, Yi A, Zhu Z, Schopp N, Peng A, Luginbuhl B, Nguyen T-Q, Aspuru-Guzik A
- Venue: ChemRxiv
- Category: Preprint
- Peer reviewed: Non Peer Reviewed
- AC members: Alán Aspuru-Guzik
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.71
- Missing: source_summary, hardware, properties, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
Not specified in CSV.

## Abstract
Beyond molecular structure: critically assessing
machine learning for designing organic
photovoltaic materials and devices†
Martin Seifrid,
‡*ab Stanley Lo,
‡b Dylan G. Choi,c Gary Tom,bde My Linh Le,f
Kunyu Li,§c Rahul Sankar,§c Hoai-Thanh Vuong,§c Hiba Wakidi,§c Ahra Yi,§c
Ziyue Zhu,§c Nora Schopp,c Aaron Peng,c Benjamin R. Luginbuhl,c
Thuc-Quyen Nguyen
*c and Al´an Aspuru-Guzik*bdeghij
Our study explores the current state of machine learning (ML) as applied to predicting and designing organic
photovoltaic (OPV) devices. We outline key considerations for selecting the method of encoding
a molecular structure and selecting the algorithm while also emphasizing important aspects of training
and rigorously evaluating ML models. This work presents the ﬁrst comprehensive dataset of OPV device
fabrication data mined from the literature. The top models achieve state-of-the-art predictive
performance. In particular, we identify an algorithm that is used less frequently, but may be particularly
well suited to similar datasets. However, predictive performance remains modest (R2 y 0.6) overall. An
in-depth analysis of the dataset attributes this limitation to challenges relating to the size of the dataset,
as well as data quality and sparsity. These aspects are directly tied to diﬃculties imposed by current
reporting and publication practices. Advocating for standardized reporting of OPV device fabrication data
reporting in publications emerges as crucial to streamline literature mining and foster ML adoption. This
Martin Seifrid
Martin Seifrid received his PhD from the University of California, Santa Barbara in 2019, where he
worked in the Center for Polymers and Organic Solids with Prof. Guillermo C. Bazan. He used
computational and experimental methods to study molecular design and structure–processing–property
relationships in molecular and polymeric organic semiconductors. He carried out his postdoctoral
research at the University of Toronto with Prof. Al´an Aspuru-Guzik

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Curating a comprehensive dataset of OPV device fabrication data and evaluating various structural representations and ML algorithms.

### Problem
- The challenge of accurately predicting the power conversion efficiency (PCE) of organic photovoltaic (OPV) devices using machine learning (ML) models.

### Hypothesis
- The encoding method of molecular structures and the choice of ML algorithm significantly affect the predictive performance for PCE of OPV devices.

### Evidence
- The histogram gradient boosting (HGB) model using Mordred descriptors for molecular structure achieved the best predictive performance with an R2 score of 0.61.

### Conclusion
- Data quality and standardized reporting are critical for improving ML model performance in predicting OPV device efficiency.

## Scientific Objects And Mechanisms
### Entities
- Organic photovoltaic (OPV) devices
- Molecular structures of donor and acceptor materials
- Machine learning (ML) models
- Power conversion efficiency (PCE)

### Materials / Systems
- Molecular structures of donor and acceptor materials
- Beyond Molecular Structure: Critically Assessing Machine Learning for Designing Organic Photovoltaic Materials and Devices Curating a comprehensive dataset of OPV device fabrication data and evaluating various structural representations and ML algorithms.
- Organic photovoltaic (OPV) devices Molecular structures of donor and acceptor materials Machine learning (ML) models Power conversion efficiency (PCE) Identification of the most effective molecular structure encoding and ML algorithm combinations for predicting PCE Benchmarking of ML model performance against existing methods and datasets Recommendations for data reporting standards to enhance ML model development and adoption in OPV research

### Properties
- Not specified.

### Measurements
- Organic photovoltaic (OPV) devices Molecular structures of donor and acceptor materials Machine learning (ML) models Power conversion efficiency (PCE) Identification of the most effective molecular structure encoding and ML algorithm combinations for predicting PCE Benchmarking of ML model performance against existing methods and datasets Recommendations for data reporting standards to enhance ML model development and adoption in OPV research

### Conditions
- Not specified.

### Mechanisms
- Molecular structure encoding methods (e.g., one-hot encoding, SMILES, ECFP, Mordred descriptors)
- ML algorithms (e.g., linear regression, kernel ridge regression, support vector regression, random forest, gradient boosting, neural networks)
- Model evaluation metrics (e.g., R2 score, RMSE, MAE)

### Outcomes
- Identification of the most effective molecular structure encoding and ML algorithm combinations for predicting PCE
- Benchmarking of ML model performance against existing methods and datasets
- Recommendations for data reporting standards to enhance ML model development and adoption in OPV research

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Chemistry
- Clean energy

### Reasoning Motifs
- Representation Quality → Prediction Accuracy
- Algorithm Complexity → Model Generalizability
- Data Sparsity → Model Overfitting

### General Principles
- Signal Representation and Transformation
- Complexity-Accuracy Trade-off
- Information Theory in Pattern Recognition

## Failure Paths / Caveats
- partial: Incorporating device fabrication parameters into ML models Evidence: While including these features did not significantly improve model performance, suggesting limitations in data quality and sparsity.
- partial: Using graph neural networks (GNN) for molecular structure encoding Evidence: GNN regressor struggled due to the size of the dataset, but graph embeddings extracted from GNN combined with tree-based models outperformed direct PCE prediction from the graph.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_77651ccbaa92.json`
- Cross-SDL extraction quality: 0.7
- Notes: The paper provides a structured approach to evaluating ML models for predicting OPV device efficiency, but the reasoning structure is implicit in some parts, requiring inference. The paper focuses on the impact of data quality and reporting standards, which are critical for ML model development.
