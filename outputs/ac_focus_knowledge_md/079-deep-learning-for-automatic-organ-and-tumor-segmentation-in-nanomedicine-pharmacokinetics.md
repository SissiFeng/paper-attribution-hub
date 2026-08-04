# Deep learning for automatic organ and tumor segmentation in nanomedicine pharmacokinetics

## Metadata
- Paper ID: `acfocus_d36b6d084012`
- Cross-SDL ID: `not matched`
- DOI: 10.7150/thno.90246
- URL: https://pmc.ncbi.nlm.nih.gov/articles/PMC10797295/
- Year: 2024
- Authors: Dhaliwal A, Ma J, Zheng M, Lyu Q, Rajora MA, Ma S, Oliva L, Ku A, Valic M, Wang B, Zheng G
- Venue: Theranostics
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Bo Wang
- AC programs: Not specified
- AC membership status: AC Full Member
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=checked

## Validation
- Score: 0.48
- Missing: hardware, evidence, materials, measurements, mechanisms, outcomes, cross_sdl_match
- Notes: No cross-SDL extraction matched this paper; fields are derived from CSV only.; Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
NanoMASK is a publicly available, deep learning-based tool that enables rapid, accurate, and automatic 3D organ segmentation and pharmacokinetic analysis from multimodal imaging data in nanomedicine research, significantly improving throughput and generalizability across various nanoparticle types.

## Abstract
Rationale: Multimodal imaging provides important pharmacokinetic and dosimetry information during nanomedicine development and optimization. However, accurate quantitation is time-consuming, resource intensive, and requires anatomical expertise. Methods: We present NanoMASK: a 3D U-Net adapted deep learning tool capable of rapid, automatic organ segmentation of multimodal imaging data that can output key clinical dosimetry metrics without manual intervention. This model was trained on 355 manually-contoured PET/CT data volumes of mice injected with a variety of nanomaterials and imaged over 48 hours. Results: NanoMASK produced 3-dimensional contours of the heart, lungs, liver, spleen, kidneys, and tumor with high volumetric accuracy (pan-organ average %DSC of 92.5). Pharmacokinetic metrics including %ID/cc, %ID, and SUVmax achieved correlation coefficients exceeding R = 0.987 and relative mean errors below 0.2%. NanoMASK was applied to novel datasets of lipid nanoparticles and antibody-drug conjugates with a minimal drop in accuracy, illustrating its generalizability to different classes of nanomedicines. Furthermore, 20 additional auto-segmentation models were developed using training data subsets based on image modality, experimental imaging timepoint, and tumor status. These were used to explore the fundamental biases and dependencies of auto-segmentation models built on a 3D U-Net architecture, revealing significant differential impacts on organ segmentation accuracy. Conclusions: NanoMASK is an easy-to-use, adaptable tool for improving accuracy and throughput in imaging-based pharmacokinetic studies of nanomedicine. It has been made publicly available to all readers for automatic segmentation and pharmacokinetic analysis across a diverse array of nanoparticles, expediting agent development.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- NanoMASK is a publicly available, deep learning-based tool that enables rapid, accurate, and automatic 3D organ segmentation and pharmacokinetic analysis from multimodal imaging data in nanomedicine research, significantly improving throughput and generalizability across various nanoparticle types.

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
- Results: NanoMASK produced 3-dimensional contours of the heart, lungs, liver, spleen, kidneys, and tumor with high volumetric accuracy (pan-organ average %DSC of 92.5).
- NanoMASK was applied to novel datasets of lipid nanoparticles and antibody-drug conjugates with a minimal drop in accuracy, illustrating its generalizability to different classes of nanomedicines.
- These were used to explore the fundamental biases and dependencies of auto-segmentation models built on a 3D U-Net architecture, revealing significant differential impacts on organ segmentation accuracy.
- Conclusions: NanoMASK is an easy-to-use, adaptable tool for improving accuracy and throughput in imaging-based pharmacokinetic studies of nanomedicine.

### Measurements
- Not specified.

### Conditions
- However, accurate quantitation is time-consuming, resource intensive, and requires anatomical expertise.

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
