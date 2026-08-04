# A Machine Learning Approach for Predicting Particle Spatial, Velocity, and Temperature Distributions in Cold Spray Additive Manufacturing

## Metadata
- Paper ID: `acfocus_6cd4126bb59a`
- Cross-SDL ID: `not matched`
- DOI: 10.3390/app15126418
- URL: https://www.mdpi.com/2076-3417/15/12/6418
- Year: 2025
- Authors: L. Wang; M. Jadidi; A. Dolatabadi
- Venue: Applied Sciences Switzerland
- Category: Journal Article
- Peer reviewed: Peer Reviewed
- AC members: Ali Dolatabadi
- AC programs: Not specified
- AC membership status: AC Full Member
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.47
- Missing: hardware, evidence, materials, properties, measurements, mechanisms, cross_sdl_match
- Notes: No cross-SDL extraction matched this paper; fields are derived from CSV only.; Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
A two-stage machine learning framework, trained on high-fidelity CFD simulations, accurately predicts particle behavior in masked cold spray additive manufacturing of nickel-based electrodes, significantly accelerating process design and generalizing to unmasked setups.

## Abstract
Masked cold spray additive manufacturing (CSAM) is investigated for fabricating nickel-based electrodes with pyramidal pin-fins that enlarge the active area for the hydrogen-evolution reaction (HER). To bypass the high cost of purely CFD-driven optimization, we construct a two-stage machine learning (ML) framework trained on 48 high-fidelity CFD simulations. Stage 1 applies sampling and a K-nearest-neighbor kernel-density-estimation algorithm that predicts the spatial distribution of impacting particles and re-allocates weights in regions of under-estimation. Stage 2 combines sampling, interpolation and symbolic regression to extract key features, then uses a weighted random forest model to forecast particle velocity and temperature upon impact. The ML predictions closely match CFD outputs while reducing computation time by orders of magnitude, demonstrating that ML-CFD integration can accelerate CSAM process design. Although developed for a masked setup, the framework generalizes readily to unmasked cold spray configurations.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- A two-stage machine learning framework, trained on high-fidelity CFD simulations, accurately predicts particle behavior in masked cold spray additive manufacturing of nickel-based electrodes, significantly accelerating process design and generalizing to unmasked setups.

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
- Chemical Engineering

### Materials / Systems
- Not specified.

### Properties
- Not specified.

### Measurements
- Not specified.

### Conditions
- A Machine Learning Approach for Predicting Particle Spatial, Velocity, and Temperature Distributions in Cold Spray Additive Manufacturing A two-stage machine learning framework, trained on high-fidelity CFD simulations, accurately predicts particle behavior in masked cold spray additive manufacturing of nickel-based electrodes, significantly accelerating process design and generalizing to unmasked setups.
- Stage 2 combines sampling, interpolation and symbolic regression to extract key features, then uses a weighted random forest model to forecast particle velocity and temperature upon impact.
- The ML predictions closely match CFD outputs while reducing computation time by orders of magnitude, demonstrating that ML-CFD integration can accelerate CSAM process design.

### Mechanisms
- Not specified.

### Outcomes
- Electronics

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Chemistry
- Chemical Engineering
- Electronics

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
