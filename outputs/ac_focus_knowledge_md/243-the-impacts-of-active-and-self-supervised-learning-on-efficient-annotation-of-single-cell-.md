# The impacts of active and self-supervised learning on efficient annotation of single-cell expression data

## Metadata
- Paper ID: `acfocus_05f49a380850`
- Cross-SDL ID: `not matched`
- DOI: 10.1038/s41467-024-45198-y
- URL: https://www.nature.com/articles/s41467-024-45198-y
- Year: 2024
- Authors: Geuenich MJ, Gong DW, Campbell KR
- Venue: Nature Communications
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Kieran Campbell
- AC programs: Not specified
- AC membership status: AC Full Member
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=checked

## Validation
- Score: 0.54
- Missing: hardware, evidence, materials, mechanisms, outcomes, cross_sdl_match
- Notes: No cross-SDL extraction matched this paper; fields are derived from CSV only.; Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
This study benchmarks active and self-supervised learning strategies for single-cell data annotation, introduces adaptive reweighting methods, demonstrates the value of prior marker knowledge, and provides practical recommendations, with tools available at https://github.com/camlab-bioml/leader.

## Abstract
A crucial step in the analysis of single-cell data is annotating cells to cell types and states. While a myriad of approaches has been proposed, manual labeling of cells to create training datasets remains tedious and time-consuming. In the field of machine learning, active and self-supervised learning methods have been proposed to improve the performance of a classifier while reducing both annotation time and label budget. However, the benefits of such strategies for single-cell annotation have yet to be evaluated in realistic settings. Here, we perform a comprehensive benchmarking of active and self-supervised labeling strategies across a range of single-cell technologies and cell type annotation algorithms. We quantify the benefits of active learning and self-supervised strategies in the presence of cell type imbalance and variable similarity. We introduce adaptive reweighting, a heuristic procedure tailored to single-cell data—including a marker-aware version—that shows competitive performance with existing approaches. In addition, we demonstrate that having prior knowledge of cell type markers improves annotation accuracy. Finally, we summarize our findings into a set of recommendations for those implementing cell type annotation procedures or platforms. An R package implementing the heuristic approaches introduced in this work may be found at https://github.com/camlab-bioml/leader.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- This study benchmarks active and self-supervised learning strategies for single-cell data annotation, introduces adaptive reweighting methods, demonstrates the value of prior marker knowledge, and provides practical recommendations, with tools available at https://github.com/camlab-bioml/leader.

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
- Biology
- Artificial Intelligence & Data Science

### Materials / Systems
- Not specified.

### Properties
- In addition, we demonstrate that having prior knowledge of cell type markers improves annotation accuracy.

### Measurements
- Here, we perform a comprehensive benchmarking of active and self-supervised labeling strategies across a range of single-cell technologies and cell type annotation algorithms.

### Conditions
- While a myriad of approaches has been proposed, manual labeling of cells to create training datasets remains tedious and time-consuming.
- In the field of machine learning, active and self-supervised learning methods have been proposed to improve the performance of a classifier while reducing both annotation time and label budget.

### Mechanisms
- Not specified.

### Outcomes
- Not specified.

## Cross-SDL Transfer
### SDL / Domain Tags
- Biology
- Artificial Intelligence & Data Science

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
