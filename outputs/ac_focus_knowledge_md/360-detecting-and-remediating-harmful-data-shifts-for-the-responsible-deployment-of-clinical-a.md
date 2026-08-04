# Detecting and Remediating Harmful Data Shifts for the Responsible Deployment of Clinical AI Models

## Metadata
- Paper ID: `acfocus_7ccb7981d790`
- Cross-SDL ID: `not matched`
- DOI: 10.1001/jamanetworkopen.2025.13685
- URL: https://jamanetwork.com/journals/jamanetworkopen/fullarticle/2834882#google_vignette202506
- Year: 2025
- Authors: V. Subasri; A. Krishnan; A. Kore; A. Dhalla; D. Pandya; B. Wang; D. Malkin; F. Razak; A. A. Verma; A. Goldenberg; E. Dolatabadi
- Venue: JAMA Network Open
- Category: Journal Article
- Peer reviewed: Peer Reviewed
- AC members: Ali Dolatabadi
- AC programs: Not specified
- AC membership status: AC Full Member
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.43
- Missing: hardware, evidence, materials, properties, measurements, conditions, mechanisms, cross_sdl_match
- Notes: No cross-SDL extraction matched this paper; fields are derived from CSV only.; Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
This study developed and evaluated a proactive, label-agnostic monitoring pipeline that successfully detected and mitigated harmful data shifts in clinical AI systems predicting in-hospital mortality, demonstrating that transfer learning and continual learning strategies can maintain model performance across diverse healthcare settings.

## Abstract
Importance: Clinical artificial intelligence (AI) systems are susceptible to performance degradation due to data shifts, which can lead to erroneous predictions and potential patient harm. Proactively detecting and mitigating these shifts is crucial for maintaining AI effectiveness and safety in clinical practice. Objectives: To develop and evaluate a proactive, label-agnostic monitoring pipeline to detect and mitigate harmful data shifts in clinical AI systems and to assess the use of transfer learning and continual learning strategies in maintaining model performance. Design, Setting, and Participants: This prognostic study was conducted using electronic health record data for admissions to general internal medicine wards of 7 large hospitals (5 academic and 2 community) in Toronto, Canada, between January 1, 2010, to August 31, 2020. Inpatients (aged ≥18 years) with a hospital stay of at least 24 hours were included. Data analysis was performed from January to August 2022. Exposures: Data shifts due to changes in hospital type, critical laboratory assays, patient demographics, admission type, and the COVID-19 pandemic. Main Outcomes and Measures: The primary outcome was predictive performance for all-cause in-hospital mortality within the next 2 weeks, evaluated using the area under the receiver operating characteristic curve (AUROC) and the area under the precision-recall curve (AUPRC). Data shifts were detected using a label-agnostic monitoring pipeline employing a black box shift estimator with maximum mean discrepancy testing. Results: Data were available for 143049 adult inpatients (mean [SD] age, 67.8 [19.6] years; 50.7% female). Significant data shifts were detected as a result of changes in younger age groups and admissions from nursing homes and acute care centers, transferring from community to academic hospitals, and changes in brain natriuretic peptide and D-dimer. Transfer learning improved model performance of community hospitals in a hospital type-dependent manner (Delta AUROC [SD], 0.05 [0.03]; Delta AUPRC [SD], 0.06 [0.04]). During the COVID-19 pandemic, drift-triggered continual learning improved overall model performance (Delta AUROC [SD], 0.44 [0.02]; P =.007, Mann-Whitney U test). Conclusions and Relevance: In this prognostic study, a proactive, label-agnostic monitoring pipeline detected harmful data shifts for a clinical AI system predicting in-hospital mortality. Transfer learning and drift-triggered continual learning strategies mitigated performance degradation, maintaining model performance across health care settings. These findings suggest that the approach used here may ensure the robust and equitable deployment of clinical AI models. Future research should explore the generalizability of this framework across diverse clinical domains, data modalities, and longer deployment periods to further validate its effectiveness. © 2025 American Medical Association. All rights reserved.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- This study developed and evaluated a proactive, label-agnostic monitoring pipeline that successfully detected and mitigated harmful data shifts in clinical AI systems predicting in-hospital mortality, demonstrating that transfer learning and continual learning strategies can maintain model performance across diverse healthcare settings.

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
- Not specified.

### Conditions
- Not specified.

### Mechanisms
- Not specified.

### Outcomes
- Therapeutics

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Biology
- Therapeutics

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
