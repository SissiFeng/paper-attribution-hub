# Computer Vision To Predict Cell Seeding Coverage In Re-endothelialized Mouse Lungs

## Metadata
- Paper ID: `acfocus_da27514c512b`
- Cross-SDL ID: `acgold_7690053ac614`
- DOI: 10.1038/s41598-025-11272-8
- URL: https://www.researchgate.net/publication/393806570_Computer_vision_to_predict_cell_seeding_coverage_in_re-endothelialized_mouse_lungs
- Year: 2024
- Authors: Paciocco J, Zargar A, Moayad A, Chan JKD, Taniguchi D, Amon C, Karoubi G, Bazylak A
- Venue: Nature Scientific Reports
- Category: Conference
- Peer reviewed: Non Peer Reviewed
- AC members: Aimy Bazylak
- AC programs: Not specified
- AC membership status: AC Full Member
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.65
- Missing: source_summary, hardware, properties, measurements, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
Not specified in CSV.

## Abstract
Computer vision to predict 
cell seeding coverage in re-
endothelialized mouse lungs
Joshua Paciocco1, Ahmed Hasan1, Jason Chan1, Daisuke Taniguchi2, Cristina Amon1,3, 
Golnaz Karoubi1,2,4 & Aimy Bazylak1
Transplantation of donor grafts recellularized with recipient-derived or non-immunogenic universal 
cells is a potential means of reducing the graft rejection and post-transplant complications in lung 
transplantation. Achieving a fully recellularized lung, however, remains a far-off goal and has several 
limitations, including inadequate cell coverage of the acellular scaffold. A key parameter for evaluating 
recellularization efficacy is the cell seeding coverage (CSC); the ratio of seeded cell area to the total 
area of the lung scaffold. To calculate the CSC from a histological image, the lung scaffold and the 
seeded cell areas must be quantified. In this work, the ability of semantic segmentation to accurately 
automate the pixel-wise analysis of histological images is investigated. Specifically, the U-Net 
and LinkNet models are applied to re-endothelialized mouse lung images, generating pixel-wise 
classifications of the lung scaffold and the seeded cell areas to calculate the CSC. Model performance 
when trained on complete images and on image patches is compared. The patch-based U-Net model 
outperformed the other models, predicting CSC with a root mean square error of 2.23 ± 0.36%, in 
addition to classifying lung scaffold pixels and seeded cell pixels with intersection over union scores of 
77.8 ± 1.4% and 69.5 ± 1.1% respectively.
Keywords  Bioengineered lung, Cell seeding coverage, Lung re-endothelialization, Machine learning, 
Medical images, Semantic segmentation
Lung transplantation is the only treatment option for end-stage lung disease and yet, the five-year survival rate 
post-procedure is estimated to be 55%-60%, with high rejection rates and complications post-transplantation 
being among the most common causes of death1,2. In addition, with 

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Applying U-Net and LinkNet models to re-endothelialized mouse lung images for pixel-wise classifications of lung scaffold and seeded cell areas to calculate CSC, comparing model performance when trained on complete images vs. image patches

### Problem
- Inadequate cell coverage of the acellular scaffold in lung recellularization, specifically quantifying cell seeding coverage (CSC) from histological images

### Hypothesis
- Semantic segmentation models, specifically U-Net and LinkNet, can accurately automate pixel-wise analysis of histological images to calculate CSC

### Evidence
- Patch-based U-Net model outperformed with a root mean square error of 2.23 ± 0.36% and intersection over union scores of 77.8 ± 1.4% for lung scaffold and 69.5 ± 1.1% for seeded cells

### Conclusion
- Semantic segmentation via U-Net and LinkNet models is a viable means of automating pixel-wise analysis of re-endothelialized images, potentially saving time and reducing errors in CSC calculation

## Scientific Objects And Mechanisms
### Entities
- lung scaffold
- seeded cells
- histological images

### Materials / Systems
- seeded cells

### Properties
- Not specified.

### Measurements
- Not specified.

### Conditions
- Not specified.

### Mechanisms
- semantic segmentation for pixel-wise classification
- image patching to increase training data
- transfer learning from pre-trained models

### Outcomes
- accurate classification of lung scaffold and seeded cell pixels
- increased training data to improve model performance
- adaptation of pre-trained models to specific task of CSC prediction

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Biology

### Reasoning Motifs
- Data Augmentation → Model Generalizability
- Pre-trained Models → Task-specific Adaptation
- Patch-based Learning → Increased Training Data

### General Principles
- Data Representation Enhancement
- Knowledge Transfer
- Sample Diversity

## Failure Paths / Caveats
- failure: Applying HALO software for image segmentation Evidence: HALO software missed significant lung scaffold tissues and misinterpreted background pixels for lung scaffold
- success: Using k-means clustering for image segmentation Evidence: k-means clustering produced nearly identical pixel classifications as multi-Otsu thresholding, a preferred method

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_7690053ac614.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper provides a structured approach to applying semantic segmentation to a specific problem in bioengineering, with clear problem formulation, hypothesis testing, and methodological details. However, some aspects of the exploration narrative had to be inferred from the results and discussion, particularly regarding initial attempts and motivations behind choosing specific models or techniques.
