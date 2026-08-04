# Weakly-Supervised Depth Completion during Robotic Micromanipulation from a Monocular Microscopic Image

## Metadata
- Paper ID: `acfocus_1a7a4a1241c7`
- Cross-SDL ID: `not matched`
- DOI: 10.1109/icra57147.2024.10611357
- URL: https://ieeexplore.ieee.org/document/10611357
- Year: 2024
- Authors: Yang H, Jin Y, Shan G, Wang Y, Zheng Y, Yu J, Sun Y, Zhang Z
- Venue: Proceedings - IEEE International Conference on Robotics and Automation
- Category: Conference
- Peer reviewed: Peer Reviewed
- AC members: Yu Sun
- AC programs: Not specified
- AC membership status: AC Full Member
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.6
- Missing: evidence, materials, conditions, mechanisms, outcomes, cross_sdl_match
- Notes: No cross-SDL extraction matched this paper; fields are derived from CSV only.

## Source Summary
This paper proposes a weakly-supervised depth completion network that combines cell images and sparse contact-based depth data to generate accurate, dense depth maps for robotic cell micromanipulation, achieving a depth prediction error (MAE) of less than 0.3 μm and enabling seamless integration with micromanipulation tasks.

## Abstract
Obtaining three-dimensional information, especially the z-axis depth information, is crucial for robotic micromanipulation. Due to the unavailability of depth sensors such as lidars in micromanipulation setups, traditional depth acquisition methods such as depth from focus or depth from defocus directly infer depth from microscopic images and suffer from poor resolution. Alternatively, micromanipulation tasks obtain accurate depth information by detecting the contact between an end-effector and an object (e.g., a cell). Despite its high accuracy, only sparse depth data can be obtained due to its low efficiency. This paper aims to address the challenge of acquiring dense depth information during robotic cell micromanipulation. A weakly-supervised depth completion network is proposed to take cell images and sparse depth data obtained by contact detection as input to generate a dense depth map. A two-stage data augmentation method is proposed to augment the sparse depth data, and the depth map is optimized by a network refinement method. The experimental results show that the MAE value of the depth prediction error is less than 0.3 μm, which proves the accuracy and effectiveness of the method. This deep learning network pipeline can be seamlessly integrated with the robotic micromanipulation tasks to provide accurate depth information.

## Scientific Elements
### Hardware / Physical System
- This paper proposes a weakly-supervised depth completion network that combines cell images and sparse contact-based depth data to generate accurate, dense depth maps for robotic cell micromanipulation, achieving a depth prediction error (MAE) of less than 0.3 μm and enabling seamless integration with micromanipulation tasks.
- Obtaining three-dimensional information, especially the z-axis depth information, is crucial for robotic micromanipulation.
- This paper aims to address the challenge of acquiring dense depth information during robotic cell micromanipulation.
- This deep learning network pipeline can be seamlessly integrated with the robotic micromanipulation tasks to provide accurate depth information.

### Method
- This paper proposes a weakly-supervised depth completion network that combines cell images and sparse contact-based depth data to generate accurate, dense depth maps for robotic cell micromanipulation, achieving a depth prediction error (MAE) of less than 0.3 μm and enabling seamless integration with micromanipulation tasks.

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
- Automation and Robotics
- Biology

### Materials / Systems
- Not specified.

### Properties
- Despite its high accuracy, only sparse depth data can be obtained due to its low efficiency.
- The experimental results show that the MAE value of the depth prediction error is less than 0.3 μm, which proves the accuracy and effectiveness of the method.

### Measurements
- Weakly-Supervised Depth Completion during Robotic Micromanipulation from a Monocular Microscopic Image This paper proposes a weakly-supervised depth completion network that combines cell images and sparse contact-based depth data to generate accurate, dense depth maps for robotic cell micromanipulation, achieving a depth prediction error (MAE) of less than 0.3 μm and enabling seamless integration with micromanipulation tasks.
- Due to the unavailability of depth sensors such as lidars in micromanipulation setups, traditional depth acquisition methods such as depth from focus or depth from defocus directly infer depth from microscopic images and suffer from poor resolution.

### Conditions
- Not specified.

### Mechanisms
- Not specified.

### Outcomes
- Not specified.

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Automation and Robotics
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
