# Tandem mass spectrum prediction for small molecules using graph transformers

## Metadata
- Paper ID: `acfocus_49eeaffedcf6`
- Cross-SDL ID: `not matched`
- DOI: 10.1038/s42256-024-00816-8
- URL: https://www.nature.com/articles/s42256-024-00816-8
- Year: 2024
- Authors: Young A, Röst H, Wang B
- Venue: Nature Machine Intelligence
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Bo Wang
- AC programs: Not specified
- AC membership status: AC Full Member
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=checked

## Validation
- Score: 0.51
- Missing: hardware, evidence, measurements, conditions, mechanisms, outcomes, cross_sdl_match
- Notes: No cross-SDL extraction matched this paper; fields are derived from CSV only.; Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
MassFormer, a graph transformer-based model pre-trained on chemical tasks and fine-tuned on spectral data, accurately predicts tandem mass spectra by modeling long-distance atomic relationships, outperforming existing methods and effectively generalizing to new molecules.

## Abstract
Tandem mass spectra capture fragmentation patterns that provide key structural information about molecules. Although mass spectrometry is applied in many areas, the vast majority of small molecules lack experimental reference spectra. For over 70 years, spectrum prediction has remained a key challenge in the field. Existing deep learning methods do not leverage global structure in the molecule, potentially resulting in difficulties when generalizing to new data. In this work we propose the MassFormer model for accurately predicting tandem mass spectra. MassFormer uses a graph transformer architecture to model long-distance relationships between atoms in the molecule. The transformer module is initialized with parameters obtained through a chemical pretraining task, then fine-tuned on spectral data. MassFormer outperforms competing approaches for spectrum prediction on multiple datasets and accurately models the effects of collision energy. Gradient-based attribution methods reveal that MassFormer can identify compositional relationships between peaks in the spectrum. When applied to spectrum identification problems, MassFormer generally surpasses the performance of existing prediction-based methods.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- MassFormer, a graph transformer-based model pre-trained on chemical tasks and fine-tuned on spectral data, accurately predicts tandem mass spectra by modeling long-distance atomic relationships, outperforming existing methods and effectively generalizing to new molecules.

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
- Biology

### Materials / Systems
- Tandem mass spectrum prediction for small molecules using graph transformers MassFormer, a graph transformer-based model pre-trained on chemical tasks and fine-tuned on spectral data, accurately predicts tandem mass spectra by modeling long-distance atomic relationships, outperforming existing methods and effectively generalizing to new molecules.
- Tandem mass spectra capture fragmentation patterns that provide key structural information about molecules.
- Although mass spectrometry is applied in many areas, the vast majority of small molecules lack experimental reference spectra.

### Properties
- MassFormer outperforms competing approaches for spectrum prediction on multiple datasets and accurately models the effects of collision energy.

### Measurements
- Not specified.

### Conditions
- Not specified.

### Mechanisms
- Not specified.

### Outcomes
- Not specified.

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Chemistry
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
