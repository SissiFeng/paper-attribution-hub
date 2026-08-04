# STIEFEL FLOW MATCHING FOR MOMENT-CONSTRAINED STRUCTURE ELUCIDATION

## Metadata
- Paper ID: `acfocus_a04deb56beb2`
- Cross-SDL ID: `not matched`
- DOI: Not specified
- URL: https://www.scopus.com/inward/record.uri?eid=2-s2.0-105010187202&partnerID=40&md5=2f81d51fe110ead6ffb29195c0ab5a8d
- Year: 2025
- Authors: A. H. Cheng; A. Lo; K. L. K. Lee; S. Miret; A. Aspuru-Guzik
- Venue: 13th International Conference on Learning Representations, ICLR 2025
- Category: Conference Proceedings
- Peer reviewed: Not specified
- AC members: Alán Aspuru-Guzik
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=checked, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.6
- Missing: evidence, entities, conditions, mechanisms, outcomes, cross_sdl_match
- Notes: No cross-SDL extraction matched this paper; fields are derived from CSV only.

## Source Summary
The authors introduce Stiefel Flow Matching, a generative model that predicts a molecule's precise 3D structure from its formula and moments of inertia by enforcing exact moment constraints, outperforming existing models in accuracy and efficiency on complex molecular datasets.

## Abstract
Molecular structure elucidation is a fundamental step in understanding chemical phenomena, with applications in identifying molecules in natural products, lab syntheses, forensic samples, and the interstellar medium. We consider the task of predicting a molecule's all-atom 3D structure given only its molecular formula and moments of inertia, motivated by the ability of rotational spectroscopy to measure these moments. While existing generative models can conditionally sample 3D structures with approximately correct moments, this soft conditioning fails to leverage the many digits of precision afforded by experimental rotational spectroscopy. To address this, we first show that the space of n-atom point clouds with a fixed set of moments of inertia is embedded in the Stiefel manifold St(n, 4). We then propose Stiefel Flow Matching as a generative model for elucidating 3D structure under exact moment constraints. Additionally, we learn simpler and shorter flows by finding approximate solutions for equivariant optimal transport on the Stiefel manifold. Empirically, enforcing exact moment constraints allows Stiefel Flow Matching to achieve higher success rates and faster sampling than Euclidean diffusion models, even on high-dimensional manifolds corresponding to large molecules in the GEOM dataset. © 2025 13th International Conference on Learning Representations, ICLR 2025. All rights reserved.

## Scientific Elements
### Hardware / Physical System
- We consider the task of predicting a molecule's all-atom 3D structure given only its molecular formula and moments of inertia, motivated by the ability of rotational spectroscopy to measure these moments.
- While existing generative models can conditionally sample 3D structures with approximately correct moments, this soft conditioning fails to leverage the many digits of precision afforded by experimental rotational spectroscopy.

### Method
- The authors introduce Stiefel Flow Matching, a generative model that predicts a molecule's precise 3D structure from its formula and moments of inertia by enforcing exact moment constraints, outperforming existing models in accuracy and efficiency on complex molecular datasets.

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
- Not specified.

### Materials / Systems
- STIEFEL FLOW MATCHING FOR MOMENT-CONSTRAINED STRUCTURE ELUCIDATION The authors introduce Stiefel Flow Matching, a generative model that predicts a molecule's precise 3D structure from its formula and moments of inertia by enforcing exact moment constraints, outperforming existing models in accuracy and efficiency on complex molecular datasets.
- Molecular structure elucidation is a fundamental step in understanding chemical phenomena, with applications in identifying molecules in natural products, lab syntheses, forensic samples, and the interstellar medium.
- We consider the task of predicting a molecule's all-atom 3D structure given only its molecular formula and moments of inertia, motivated by the ability of rotational spectroscopy to measure these moments.

### Properties
- STIEFEL FLOW MATCHING FOR MOMENT-CONSTRAINED STRUCTURE ELUCIDATION The authors introduce Stiefel Flow Matching, a generative model that predicts a molecule's precise 3D structure from its formula and moments of inertia by enforcing exact moment constraints, outperforming existing models in accuracy and efficiency on complex molecular datasets.

### Measurements
- We consider the task of predicting a molecule's all-atom 3D structure given only its molecular formula and moments of inertia, motivated by the ability of rotational spectroscopy to measure these moments.
- While existing generative models can conditionally sample 3D structures with approximately correct moments, this soft conditioning fails to leverage the many digits of precision afforded by experimental rotational spectroscopy.

### Conditions
- Not specified.

### Mechanisms
- Not specified.

### Outcomes
- Not specified.

## Cross-SDL Transfer
### SDL / Domain Tags
- Not specified.

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
