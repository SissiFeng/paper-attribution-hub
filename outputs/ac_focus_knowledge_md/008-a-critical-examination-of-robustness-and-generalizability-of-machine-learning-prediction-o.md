# A critical examination of robustness and generalizability of machine learning prediction of materials properties

## Metadata
- Paper ID: `acfocus_8cd0b22fa4d9`
- Cross-SDL ID: `acgold_e2d44cf2777c`
- DOI: 10.1038/s41524-023-01012-9
- URL: https://www.nature.com/articles/s41524-023-01012-9
- Year: 2023
- Authors: Li, Kangming; DeCost, Brian; Choudhary, Kamal; Greenwood, Michael; Hattrick-Simpers, Jason
- Venue: npj Computational Materials
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Jason Hattrick-Simpers
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.86
- Missing: hardware, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
Machine learning models trained on older materials databases may perform poorly on newer data due to distribution shifts, but using tools like UMAP and model disagreement can help identify and address these issues, significantly improving prediction accuracy with minimal new data.

## Abstract
Recent advances in machine learning (ML) have led to substantial performance improvement in material database benchmarks, but an excellent benchmark score may not imply good generalization performance. Here we show that ML models trained on Materials Project 2018 can have severely degraded performance on new compounds in Materials Project 2021 due to the distribution shift. We discuss how to foresee the issue with a few simple tools. Firstly, the uniform manifold approximation and projection (UMAP) can be used to investigate the relation between the training and test data within the feature space. Secondly, the disagreement between multiple ML models on the test data can illuminate out-of-distribution samples. We demonstrate that the UMAP-guided and query by committee acquisition strategies can greatly improve prediction accuracy by adding only 1% of the test data. We believe this work provides valuable insights for building databases and models that enable better robustness and generalizability.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- The authors used the ALIGNN model pretrained on Materials Project 2018 to predict formation energies of new structures in Materials Project 2021 and compared its performance with traditional ML models.

### Problem
- Machine learning models may not generalize well to new compounds in materials science due to distribution shift between training and test datasets.

### Hypothesis
- The performance of ML models trained on Materials Project 2018 will degrade on new compounds in Materials Project 2021.

### Evidence
- ALIGNN-MP18 predictions strongly underestimated the formation energies for a significant portion of the structures whose E_dft were above 0.5 eV/atom, with prediction errors ranging from 0.5 eV/atom to up to 3.5 eV/atom.

### Conclusion
- ML models, including state-of-the-art neural networks, can have severely degraded performance on new compounds due to distribution shift, which is a critical issue for assessing the maturity of a database and the robustness of ML predictions.

## Scientific Objects And Mechanisms
### Entities
- ALIGNN model
- Materials Project 2018 database
- Materials Project 2021 database
- Traditional ML models (XGB, RF, LF)

### Materials / Systems
- Materials Project 2018 database
- Materials Project 2021 database
- A critical examination of robustness and generalizability of machine learning prediction of materials properties Machine learning models trained on older materials databases may perform poorly on newer data due to distribution shifts, but using tools like UMAP and model disagreement can help identify and address these issues, significantly improving prediction accuracy with minimal new data.
- Recent advances in machine learning (ML) have led to substantial performance improvement in material database benchmarks, but an excellent benchmark score may not imply good generalization performance.
- Here we show that ML models trained on Materials Project 2018 can have severely degraded performance on new compounds in Materials Project 2021 due to the distribution shift.

### Properties
- A critical examination of robustness and generalizability of machine learning prediction of materials properties Machine learning models trained on older materials databases may perform poorly on newer data due to distribution shifts, but using tools like UMAP and model disagreement can help identify and address these issues, significantly improving prediction accuracy with minimal new data.
- We demonstrate that the UMAP-guided and query by committee acquisition strategies can greatly improve prediction accuracy by adding only 1% of the test data.
- ALIGNN model Materials Project 2018 database Materials Project 2021 database Traditional ML models (XGB, RF, LF) Degraded performance of ML models on new compounds Identification of out-of-distribution samples through UMAP clustering and model disagreement Improvement in prediction accuracy by adding a small amount of new data

### Measurements
- Recent advances in machine learning (ML) have led to substantial performance improvement in material database benchmarks, but an excellent benchmark score may not imply good generalization performance.

### Conditions
- Not specified.

### Mechanisms
- Distribution shift between training and test datasets
- Underestimation of formation energies for out-of-distribution samples
- Dimension reduction via UMAP to analyze feature space

### Outcomes
- Degraded performance of ML models on new compounds
- Identification of out-of-distribution samples through UMAP clustering and model disagreement
- Improvement in prediction accuracy by adding a small amount of new data

## Cross-SDL Transfer
### SDL / Domain Tags
- SDL 1 - Inorganic
- Artificial Intelligence & Data Science
- Materials Science

### Reasoning Motifs
- Distribution Shift → Performance Degradation
- Feature Space Analysis → Out-of-Distribution Identification
- Data Acquisition → Prediction Improvement

### General Principles
- Generalization is sensitive to distribution shift
- Robustness can be improved by identifying and acquiring out-of-distribution data

## Failure Paths / Caveats
- failure: Using RF model uncertainty quantification to identify out-of-distribution samples Evidence: RF uncertainty is only moderately correlated with the true prediction error for the test data.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_e2d44cf2777c.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper has a clear structure and logical flow in presenting the problem, analysis, and solutions. However, some details are omitted, such as the specific steps in the UMAP dimension reduction process. The reasoning链条 are mostly explicit, with some minor inferences needed.
