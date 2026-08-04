# Beyond benchmarking and towards predictive models of dataset-specific single-cell RNA-seq pipeline performance

## Metadata
- Paper ID: `acfocus_3ed5101d581e`
- Cross-SDL ID: `not matched`
- DOI: 10.1186/s13059-024-03304-9
- URL: https://link.springer.com/article/10.1186/s13059-024-03304-9
- Year: 2024
- Authors: Fang C, Selega A, Campbell KR
- Venue: Genome Biology
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Kieran Campbell
- AC programs: Not specified
- AC membership status: AC Full Member
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=checked

## Validation
- Score: 0.43
- Missing: hardware, evidence, materials, properties, conditions, mechanisms, outcomes, cross_sdl_match
- Notes: No cross-SDL extraction matched this paper; fields are derived from CSV only.; Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
Supervised machine learning models can effectively predict optimal single-cell RNA-seq analysis pipelines for specific datasets, outperforming random selection and offering guidance to users by leveraging dataset and pipeline characteristics.

## Abstract
Background: The advent of single-cell RNA-sequencing (scRNA-seq) has driven significant computational methods development for all steps in the scRNA-seq data analysis pipeline, including filtering, normalization, and clustering. The large number of methods and their resulting parameter combinations has created a combinatorial set of possible pipelines to analyze scRNA-seq data, which leads to the obvious question: which is best? Several benchmarking studies compare methods but frequently find variable performance depending on dataset and pipeline characteristics. Alternatively, the large number of scRNA-seq datasets along with advances in supervised machine learning raise a tantalizing possibility: could the optimal pipeline be predicted for a given dataset? Results: Here, we begin to answer this question by applying 288 scRNA-seq analysis pipelines to 86 datasets and quantifying pipeline success via a range of measures evaluating cluster purity and biological plausibility. We build supervised machine learning models to predict pipeline success given a range of dataset and pipeline characteristics. We find that prediction performance is significantly better than random and that in many cases pipelines predicted to perform well provide clustering outputs similar to expert-annotated cell type labels. We identify characteristics of datasets that correlate with strong prediction performance that could guide when such prediction models may be useful. Conclusions: Supervised machine learning models have utility for recommending analysis pipelines and therefore the potential to alleviate the burden of choosing from the near-infinite number of possibilities. Different aspects of datasets influence the predictive performance of such models which will further guide users.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Supervised machine learning models can effectively predict optimal single-cell RNA-seq analysis pipelines for specific datasets, outperforming random selection and offering guidance to users by leveraging dataset and pipeline characteristics.

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
- Not specified.

### Measurements
- Beyond benchmarking and towards predictive models of dataset-specific single-cell RNA-seq pipeline performance Supervised machine learning models can effectively predict optimal single-cell RNA-seq analysis pipelines for specific datasets, outperforming random selection and offering guidance to users by leveraging dataset and pipeline characteristics.
- Several benchmarking studies compare methods but frequently find variable performance depending on dataset and pipeline characteristics.

### Conditions
- Not specified.

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
