# Characterizing the impacts of dataset imbalance on single-cell data integration

## Metadata
- Paper ID: `acfocus_e485728aec89`
- Cross-SDL ID: `not matched`
- DOI: 10.1038/s41587-023-02097-9
- URL: https://www.nature.com/articles/s41587-023-02097-9
- Year: 2024
- Authors: Maan H, Zhang L, Yu C, Geuenich MJ, Campbell KR, Wang B
- Venue: Nature Biotechnology
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Kieran Campbell, Bo Wang
- AC programs: Not specified
- AC membership status: AC Full Member, AC Full Member
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=checked

## Validation
- Score: 0.54
- Missing: hardware, evidence, materials, mechanisms, outcomes, cross_sdl_match
- Notes: No cross-SDL extraction matched this paper; fields are derived from CSV only.; Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
This study demonstrates that imbalances in cell type representation across single-cell transcriptomic datasets significantly affect integration outcomes, and introduces the Iniquitate pipeline, new evaluation metrics, and practical guidelines to assess and mitigate these impacts.

## Abstract
Computational methods for integrating single-cell transcriptomic data from multiple samples and conditions do not generally account for imbalances in the cell types measured in different datasets. In this study, we examined how differences in the cell types present, the number of cells per cell type and the cell type proportions across samples affect downstream analyses after integration. The Iniquitate pipeline assesses the robustness of integration results after perturbing the degree of imbalance between datasets. Benchmarking of five state-of-the-art single-cell RNA sequencing integration techniques in 2,600 integration experiments indicates that sample imbalance has substantial impacts on downstream analyses and the biological interpretation of integration results. Imbalance perturbation led to statistically significant variation in unsupervised clustering, cell type classification, differential expression and marker gene annotation, query-to-reference mapping and trajectory inference. We quantified the impacts of imbalance through newly introduced properties—aggregate cell type support and minimum cell type center distance. To better characterize and mitigate impacts of imbalance, we introduce balanced clustering metrics and imbalanced integration guidelines for integration method users.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- This study demonstrates that imbalances in cell type representation across single-cell transcriptomic datasets significantly affect integration outcomes, and introduces the Iniquitate pipeline, new evaluation metrics, and practical guidelines to assess and mitigate these impacts.

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
- Biology

### Materials / Systems
- Not specified.

### Properties
- We quantified the impacts of imbalance through newly introduced properties—aggregate cell type support and minimum cell type center distance.

### Measurements
- Benchmarking of five state-of-the-art single-cell RNA sequencing integration techniques in 2,600 integration experiments indicates that sample imbalance has substantial impacts on downstream analyses and the biological interpretation of integration results.

### Conditions
- Computational methods for integrating single-cell transcriptomic data from multiple samples and conditions do not generally account for imbalances in the cell types measured in different datasets.

### Mechanisms
- Not specified.

### Outcomes
- Not specified.

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Biology

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
