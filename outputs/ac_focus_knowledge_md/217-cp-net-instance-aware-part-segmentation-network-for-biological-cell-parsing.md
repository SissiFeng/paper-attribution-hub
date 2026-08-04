# CP-Net: Instance-aware part segmentation network for biological cell parsing

## Metadata
- Paper ID: `acfocus_054be2e68a86`
- Cross-SDL ID: `not matched`
- DOI: 10.1016/j.media.2024.103243
- URL: https://www.sciencedirect.com/science/article/pii/S1361841524001683
- Year: 2024
- Authors: Chen W, Song H, Dai C, Huang Z, Wu A, Shan G, Liu H, Jiang A, Liu X, Ru C, Abdalla K, Dhanani SN, Moosavi KF, Pathak S, Librach C, Zhang Z, Sun Y
- Venue: Medical Image Analysis
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Yu Sun
- AC programs: Not specified
- AC membership status: AC Full Member
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.43
- Missing: hardware, evidence, materials, properties, conditions, mechanisms, outcomes, cross_sdl_match
- Notes: No cross-SDL extraction matched this paper; fields are derived from CSV only.; Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
The study introduces CP-Net, a novel instance-aware part segmentation network with attention-based feature fusion and coarse-to-fine modules, which accurately segments individual cells and their subcellular structures—demonstrated on a new sperm cell dataset—outperforming existing methods in cell parsing and subcellular analysis.

## Abstract
Instance segmentation of biological cells is important in medical image analysis for identifying and segmenting individual cells, and quantitative measurement of subcellular structures requires further cell-level subcellular part segmentation. Subcellular structure measurements are critical for cell phenotyping and quality analysis. For these purposes, instance-aware part segmentation network is first introduced to distinguish individual cells and segment subcellular structures for each detected cell. This approach is demonstrated on human sperm cells since the World Health Organization has established quantitative standards for sperm quality assessment. Specifically, a novel Cell Parsing Net (CP-Net) is proposed for accurate instance-level cell parsing. An attention-based feature fusion module is designed to alleviate contour misalignments for cells with an irregular shape by using instance masks as spatial cues instead of as strict constraints to differentiate various instances. A coarse-to-fine segmentation module is developed to effectively segment tiny subcellular structures within a cell through hierarchical segmentation from whole to part instead of directly segmenting each cell part. Moreover, a sperm parsing dataset is built including 320 annotated sperm images with five semantic subcellular part labels. Extensive experiments on the collected dataset demonstrate that the proposed CP-Net outperforms state-of-the-art instance-aware part segmentation networks.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- The study introduces CP-Net, a novel instance-aware part segmentation network with attention-based feature fusion and coarse-to-fine modules, which accurately segments individual cells and their subcellular structures—demonstrated on a new sperm cell dataset—outperforming existing methods in cell parsing and subcellular analysis.

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
- Instance segmentation of biological cells is important in medical image analysis for identifying and segmenting individual cells, and quantitative measurement of subcellular structures requires further cell-level subcellular part segmentation.
- Subcellular structure measurements are critical for cell phenotyping and quality analysis.

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
