# Reproducibility in materials informatics: lessons from ‘A general-purpose machine learning framework for predicting properties of inorganic materials’

## Metadata
- Paper ID: `acfocus_de0ba599cb38`
- Cross-SDL ID: `acgold_fb37db823976`
- DOI: 10.1039/d3dd00199g
- URL: https://xlink.rsc.org/?DOI=D3DD00199G
- Year: 2024
- Authors: Persaud D, Ward L, Hattrick-Simpers J
- Venue: Digital Discovery
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Jason Hattrick-Simpers
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.8
- Missing: hardware, measurements, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
This study highlights the difficulty and failure in reproducing results from the foundational materials informatics tool MAGPIE, identifies key reproducibility challenges, and proposes actionable steps to improve the accessibility and trustworthiness of materials informatics tools for the research community.

## Abstract
Reproducing results from a foundational materials informatics tool (magpie) is difficult and in this study, a failure. This failure yields tangible suggestions to promote easy adoption and trust of materials informatics in the future.           ,              The integration of machine learning techniques in materials discovery has become prominent in materials science research and has been accompanied by an increasing trend towards open data and open-source tools to propel the field. Despite the increasing usefulness and capabilities of these tools, developers neglecting to follow reproducible practices presents a significant barrier for other researchers looking to use or build upon their work. In this study, we investigate the challenges encountered while attempting to reproduce a section of the results presented in “A general-purpose machine learning framework for predicting properties of inorganic materials.” Our analysis identifies four major categories of challenges: (1) reporting software dependencies, (2) recording and sharing version logs, (3) sequential code organization, and (4) clarifying code references within the manuscript. The result is a proposed set of tangible action items for those aiming to make material informatics tools accessible to, and useful for the community.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Attempt to replicate the original study's results by recreating the computational environment and scripts, and analyzing the challenges encountered.

### Problem
- Reproducibility in materials informatics, specifically the inability to reproduce results from a machine learning framework for predicting properties of inorganic materials.

### Hypothesis
- The original framework and its associated scripts are incomplete or have evolved, leading to irreproducibility.

### Evidence
- Inability to replicate the original predictions, sensitivity to pseudo-random seed variations, and the lack of original scripts and version logs.

### Conclusion
- Reproducibility in materials informatics requires deliberate efforts such as version control, clear code references, and containerization of dependencies.

## Scientific Objects And Mechanisms
### Entities
- Magpie software
- Java Runtime Environment (JRE)
- Open Quantum Materials Database (OQMD)
- Reduced Pruning Error Trees (REPTrees)

### Materials / Systems
- Open Quantum Materials Database (OQMD)
- Reproducibility in materials informatics: lessons from ‘A general-purpose machine learning framework for predicting properties of inorganic materials’ This study highlights the difficulty and failure in reproducing results from the foundational materials informatics tool MAGPIE, identifies key reproducibility challenges, and proposes actionable steps to improve the accessibility and trustworthiness of materials informatics tools for the research community.
- Reproducing results from a foundational materials informatics tool (magpie) is difficult and in this study, a failure.
- This failure yields tangible suggestions to promote easy adoption and trust of materials informatics in the future.

### Properties
- Reproducibility in materials informatics: lessons from ‘A general-purpose machine learning framework for predicting properties of inorganic materials’ This study highlights the difficulty and failure in reproducing results from the foundational materials informatics tool MAGPIE, identifies key reproducibility challenges, and proposes actionable steps to improve the accessibility and trustworthiness of materials informatics tools for the research community.
- In this study, we investigate the challenges encountered while attempting to reproduce a section of the results presented in “A general-purpose machine learning framework for predicting properties of inorganic materials.” Our analysis identifies four major categories of challenges: (1) reporting software dependencies, (2) recording and sharing version logs, (3) sequential code organization, and (4) clarifying code references within the manuscript.

### Measurements
- Not specified.

### Conditions
- Not specified.

### Mechanisms
- Containerization of software environments
- Version control system for tracking code evolution
- Pseudo-random seed sensitivity in machine learning models

### Outcomes
- Enhanced reproducibility of computational experiments
- Transparent and trustworthy record of development process
- Reduction in sensitivity and improvement in model generalization

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Materials Science

### Reasoning Motifs
- Incompatibility → Reproducibility Barrier
- Version Control → Traceability
- Sensitivity Analysis → Model Robustness

### General Principles
- Control Through Constraints
- Transparency Enhances Trust

## Failure Paths / Caveats
- failure: Replicate the original study's predictions using the provided scripts and data. Evidence: The bandgaps predicted by our model deviate significantly from the reported values.
- partial: Recreate the extensibility analysis scripts due to their absence. Evidence: Scripts were recreated with some success, but the predictions could not be fully replicated.
- success: Use of different machine learning models (RF and XGB) to assess sensitivity. Evidence: RF model proved less sensitive to variations in the random seed, and XGB model displayed no sensitivity at all.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_fb37db823976.json`
- Cross-SDL extraction quality: 0.7
- Notes: The paper provides a clear narrative of the challenges encountered during the replication attempt and the solutions proposed. However, the reasoning structure is implicit in parts, requiring inference from the descriptive text. The paper does not explicitly state universal scientific principles, which required their derivation from the motifs and practices described.
