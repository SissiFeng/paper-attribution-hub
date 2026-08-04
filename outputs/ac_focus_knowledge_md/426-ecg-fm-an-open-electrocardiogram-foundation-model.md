# ECG-FM: An open electrocardiogram foundation model

## Metadata
- Paper ID: `acfocus_e31ef4d57791`
- Cross-SDL ID: `not matched`
- DOI: 10.1093/jamiaopen/ooaf122
- URL: https://pubmed.ncbi.nlm.nih.gov/41113504/
- Year: 2025
- Authors: K. McKeen; S. Masood; A. Toma; B. C. Rubin; B. Wang
- Venue: JAMIA Open
- Category: Journal Article
- Peer reviewed: Peer Reviewed
- AC members: Bo Wang
- AC programs: Not specified
- AC membership status: AC Full Member
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.56
- Missing: hardware, evidence, properties, conditions, mechanisms, cross_sdl_match
- Notes: No cross-SDL extraction matched this paper; fields are derived from CSV only.; Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
ECG-FM is an open, transformer-based foundation model for ECG analysis, pretrained on 1.5 million ECGs with hybrid self-supervision, that outperforms task-specific baselines in clinically relevant tasks, demonstrates strong generalizability and label efficiency, and is released with code, weights, and a public benchmark to advance reproducible ECG research.

## Abstract
Objectives To develop ECG-FM, an open-weight foundation model for electrocardiogram (ECG) analysis, rigorously evaluate its performance on clinically salient tasks, and openly release it alongside a public benchmark. Materials and Methods In a study using 1.5 million 12-lead ECGs, we present ECG-FM, a transformer-based foundation model pretrained with hybrid self-supervision that combines masked reconstruction and contrastive learning with ECG-specific augmentation. Downstream, we evaluate multi-label ECG interpretation and prediction of reduced left ventricular ejection fraction (LVEF), introducing an openly available benchmark on the MIMIC-IV-ECG dataset. We assess ECG-FM's capabilities through data scaling experiments, latent-space structure analysis, and attention-based saliency. Results Finetuned ECG-FM models outperform task-specific baselines in the small-to-medium-scale data regime, exhibit strong label efficiency and cross-dataset generalizability, and achieve high AUROC on salient labels, including atrial fibrillation (0.996) and LVEF ≤40% (0.929). The pretrained encoder showcases competitive linear probing performance, with functionally discriminative embeddings. Discussion Findings indicate that ECG-FM is generalizable, label-efficient, and discriminative for screening, risk stratification, and monitoring. Its representations capture low-level morphology and high-order cardiac semantics, and the pretrained encoder serves as a robust feature-set generator. This work mitigates reliance on large labeled datasets, reduces compute and data requirements, and lowers barriers to reproducibility and cross-study comparison. Conclusion ECG-FM is an open, rigorously validated ECG foundation model intended to accelerate transparent, comparable research in the ECG analysis subfield. It is designed for rapid integration and evaluation, especially for delivering practical gains in low-label settings. We release our code, model weights, tutorials, and benchmark at https://github.com/bowang-lab/ECG-FM/. © 2025 The Author(s). Published by Oxford University Press on behalf of the American Medical Informatics Association.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- ECG-FM is an open, transformer-based foundation model for ECG analysis, pretrained on 1.5 million ECGs with hybrid self-supervision, that outperforms task-specific baselines in clinically relevant tasks, demonstrates strong generalizability and label efficiency, and is released with code, weights, and a public benchmark to advance reproducible ECG research.

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
- Materials and Methods In a study using 1.5 million 12-lead ECGs, we present ECG-FM, a transformer-based foundation model pretrained with hybrid self-supervision that combines masked reconstruction and contrastive learning with ECG-specific augmentation.

### Properties
- Not specified.

### Measurements
- ECG-FM: An open electrocardiogram foundation model ECG-FM is an open, transformer-based foundation model for ECG analysis, pretrained on 1.5 million ECGs with hybrid self-supervision, that outperforms task-specific baselines in clinically relevant tasks, demonstrates strong generalizability and label efficiency, and is released with code, weights, and a public benchmark to advance reproducible ECG research.
- Objectives To develop ECG-FM, an open-weight foundation model for electrocardiogram (ECG) analysis, rigorously evaluate its performance on clinically salient tasks, and openly release it alongside a public benchmark.
- Downstream, we evaluate multi-label ECG interpretation and prediction of reduced left ventricular ejection fraction (LVEF), introducing an openly available benchmark on the MIMIC-IV-ECG dataset.
- We release our code, model weights, tutorials, and benchmark at https://github.com/bowang-lab/ECG-FM/.

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
