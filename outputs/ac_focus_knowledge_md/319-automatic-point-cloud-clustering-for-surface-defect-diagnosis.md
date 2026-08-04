# Automatic Point Cloud Clustering for Surface Defect Diagnosis

## Metadata
- Paper ID: `acfocus_75de2252b5c6`
- Cross-SDL ID: `not matched`
- DOI: 10.1109/tase.2025.3542076
- URL: https://ieeexplore.ieee.org/document/10887345
- Year: 2025
- Authors: J. Ye; X. Liu; H. Madhusudanan; Y. Wang; J. Zhu; Y. Wang; C. Ru; X. Liu; Y. Sun
- Venue: IEEE Transactions on Automation Science and Engineering
- Category: Journal Article
- Peer reviewed: Peer Reviewed
- AC members: Yu Sun
- AC programs: Not specified
- AC membership status: AC Full Member
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.58
- Missing: evidence, materials, measurements, mechanisms, outcomes, cross_sdl_match
- Notes: No cross-SDL extraction matched this paper; fields are derived from CSV only.

## Source Summary
This paper presents an automatic, coarse-to-fine point cloud clustering method for 3D surface defect diagnosis in manufacturing, which eliminates manual parameter selection by using KNN graph analysis and a modified DBSCAN algorithm, achieving higher accuracy and speed than traditional methods.

## Abstract
Point cloud clustering is a promising method for 3D surface defect diagnosis in manufacturing but requires manual clustering parameter selection, reducing usability. This paper proposes an automatic point cloud clustering method to address this issue. It employs a strategy that progresses from coarse to fine. In the coarse searching stage, a K-Nearest Neighbor (KNN) graph analysis technique is developed to recognize potential defective regions in parallel. Moving on to the fine stage of extracting detailed defects, a modified DBSCAN algorithm is proposed, in which the clustering parameters are calculated automatically from the KNN graph analysis results. Experimental results showed that the proposed method achieved cloud clustering with automatically calculated clustering parameters for surface defect diagnosis. The proposed method outperformed the traditional region growing algorithm in accuracy (0.942 vs. 0.680) and processing speed (21500 points/sec vs. 8740 points/sec) without requiring manual intervention.Note to Practitioners - This paper presents a method for diagnosing defects on automobile and flat steel surfaces. Current 3D point cloud techniques for surface defect diagnosis require manual parameter adjustments, reducing usability. This paper proposes an automatic method without manual intervention. The proposed method uses a coarse-to-fine strategy. The 3D point cloud is divided into sub-blocks to locate potential defects, and a clustering algorithm then extracts detailed defects with automatically determined parameters. We mathematically characterize changes in point density caused by surface defects and show how these features can be used for clustering parameter calculation. Experimental results demonstrate the method's efficiency on flat as well as some curved surfaces, but it has yet to be evaluated on complex structures. Future work will aim to broaden its application to include a more extensive variety of surfaces and integrate it with robotic vision systems. © 2025 IEEE.

## Scientific Elements
### Hardware / Physical System
- Future work will aim to broaden its application to include a more extensive variety of surfaces and integrate it with robotic vision systems.

### Method
- This paper presents an automatic, coarse-to-fine point cloud clustering method for 3D surface defect diagnosis in manufacturing, which eliminates manual parameter selection by using KNN graph analysis and a modified DBSCAN algorithm, achieving higher accuracy and speed than traditional methods.

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
- Materials Science

### Materials / Systems
- Not specified.

### Properties
- Automatic Point Cloud Clustering for Surface Defect Diagnosis This paper presents an automatic, coarse-to-fine point cloud clustering method for 3D surface defect diagnosis in manufacturing, which eliminates manual parameter selection by using KNN graph analysis and a modified DBSCAN algorithm, achieving higher accuracy and speed than traditional methods.
- The proposed method outperformed the traditional region growing algorithm in accuracy (0.942 vs.

### Measurements
- Not specified.

### Conditions
- Current 3D point cloud techniques for surface defect diagnosis require manual parameter adjustments, reducing usability.

### Mechanisms
- Not specified.

### Outcomes
- Not specified.

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Materials Science

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
