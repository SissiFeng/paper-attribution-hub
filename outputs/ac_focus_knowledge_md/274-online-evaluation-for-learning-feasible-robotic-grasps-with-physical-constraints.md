# Online Evaluation for Learning Feasible Robotic Grasps with Physical Constraints

## Metadata
- Paper ID: `acfocus_9bf7716326f7`
- Cross-SDL ID: `not matched`
- DOI: 10.1109/tmech.2024.3451228
- URL: https://ieeexplore.ieee.org/stamp/stamp.jsp?arnumber=10679594
- Year: 2024
- Authors: Liu D, Chen R, Luo J, Liu X, Sun Y
- Venue: IEEE/ASME transactions on mechatronics
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Yu Sun
- AC programs: Not specified
- AC membership status: AC Full Member
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.41
- Missing: hardware, evidence, materials, properties, measurements, mechanisms, outcomes, cross_sdl_match
- Notes: No cross-SDL extraction matched this paper; fields are derived from CSV only.; Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
This article introduces a framework that integrates physical constraints into grasp learning through online evaluation, enabling networks to learn from real-time errors and object geometries, which significantly reduces false predictions and improves real-world grasping success rates compared to traditional methods.

## Abstract
Existing grasp planning networks often learn from labeled images with grasp examples to eliminate the need for training through physical grasp attempts. As a result, trained networks lack an understanding of the physical constraints involved in successful grasps, leading to infeasible predictions and inaccurate evaluation. In this article, we propose a framework for integrating physical constraints, e.g., collision avoidance, into grasp learning through on-line grasp evaluation. During training, the proposed framework initially evaluates the feasibility of network predictions using physical constraints. Subsequently, physical supervision is generated based on both the feasible predictions and the geometries of the objects. In this manner, the network learns from its real-time errors and the object shape, in addition to labeled data. Experimental results demonstrated that our evaluation method achieved a significantly lower false rate (5.5%) than the commonly used metrics (intersection over union: 19.0%, SGT: 17.5%). Furthermore, the proposed framework effectively improves the network's real-world grasping success rate on EGAD objects by 18.7% for isolated objects (2450 attempts) and 15.8% for cluttered scenes (331 attempts). These results highlight the effectiveness of integrating physical constraints for feasible grasp prediction and accurate evaluation.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- This article introduces a framework that integrates physical constraints into grasp learning through online evaluation, enabling networks to learn from real-time errors and object geometries, which significantly reduces false predictions and improves real-world grasping success rates compared to traditional methods.

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

### Materials / Systems
- Not specified.

### Properties
- Not specified.

### Measurements
- Not specified.

### Conditions
- Online Evaluation for Learning Feasible Robotic Grasps with Physical Constraints This article introduces a framework that integrates physical constraints into grasp learning through online evaluation, enabling networks to learn from real-time errors and object geometries, which significantly reduces false predictions and improves real-world grasping success rates compared to traditional methods.
- In this manner, the network learns from its real-time errors and the object shape, in addition to labeled data.
- Experimental results demonstrated that our evaluation method achieved a significantly lower false rate (5.5%) than the commonly used metrics (intersection over union: 19.0%, SGT: 17.5%).
- Furthermore, the proposed framework effectively improves the network's real-world grasping success rate on EGAD objects by 18.7% for isolated objects (2450 attempts) and 15.8% for cluttered scenes (331 attempts).

### Mechanisms
- Not specified.

### Outcomes
- Not specified.

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science

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
