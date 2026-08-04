# HyperBrain: Anomaly Detection for Temporal Hypergraph Brain Networks

## Metadata
- Paper ID: `acfocus_1c6986325867`
- Cross-SDL ID: `not matched`
- DOI: 10.1007/978-3-031-78761-4_4
- URL: https://dl.acm.org/doi/10.1007/978-3-031-78761-4_4
- Year: 2025
- Authors: S. Sadeghian; X. Li; M. Seltzer
- Venue: Lecture Notes in Computer Science (including subseries Lecture Notes in Artificial Intelligence and Lecture Notes in Bioinformatics)
- Category: Conference Proceedings
- Peer reviewed: Non Peer Reviewed
- AC members: Margo Seltzer
- AC programs: Not specified
- AC membership status: AC Full Member
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.54
- Missing: hardware, evidence, materials, measurements, mechanisms, cross_sdl_match
- Notes: No cross-SDL extraction matched this paper; fields are derived from CSV only.; Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
HyperBrain is an unsupervised anomaly detection framework that models fMRI data as temporal hypergraphs to capture dynamic, higher-order brain interactions, outperforming existing methods in detecting abnormal co-activations linked to brain disorders like Autism and ADHD.

## Abstract
Identifying unusual brain activity is a crucial task in neuroscience research, as it aids in the early detection of brain disorders. It is common to represent brain networks as graphs, and researchers have developed various graph-based machine learning methods for analyzing them. However, the majority of existing graph learning tools for the brain face a combination of the following three key limitations. First, they focus only on pairwise correlations between regions of the brain, limiting their ability to capture synchronized activity among larger groups of regions. Second, they model the brain network as a static network, overlooking the temporal changes in the brain. Third, most are designed only for classifying brain networks as healthy or disordered, lacking the ability to identify abnormal brain activity patterns linked to biomarkers associated with disorders. To address these issues, we present HyperBrain, an unsupervised anomaly detection framework for temporal hypergraph brain networks. HyperBrain models fMRI time series data as temporal hypergraphs capturing dynamic higher-order interactions. It then uses a novel customized temporal walk (BrainWalk) and neural encodings to detect abnormal co-activations among brain regions. We evaluate the performance of HyperBrain in both synthetic and real-world settings for Autism Spectrum Disorder and Attention Deficit Hyperactivity Disorder (ADHD). HyperBrain outperforms all other baselines on detecting abnormal co-activations in brain networks. Furthermore, results obtained from HyperBrain are consistent with clinical research on these brain disorders. Our findings suggest that learning temporal and higher-order connections in the brain provides a promising approach to uncover intricate connectivity patterns in brain networks, offering improved diagnosis. Our code is available at: https://github.com/ubc-systopia/HyperBrain. © The Author(s), under exclusive license to Springer Nature Switzerland AG 2025.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- HyperBrain is an unsupervised anomaly detection framework that models fMRI data as temporal hypergraphs to capture dynamic, higher-order brain interactions, outperforming existing methods in detecting abnormal co-activations linked to brain disorders like Autism and ADHD.

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
- Identifying unusual brain activity is a crucial task in neuroscience research, as it aids in the early detection of brain disorders.
- First, they focus only on pairwise correlations between regions of the brain, limiting their ability to capture synchronized activity among larger groups of regions.
- Third, most are designed only for classifying brain networks as healthy or disordered, lacking the ability to identify abnormal brain activity patterns linked to biomarkers associated with disorders.

### Measurements
- Not specified.

### Conditions
- HyperBrain models fMRI time series data as temporal hypergraphs capturing dynamic higher-order interactions.

### Mechanisms
- Not specified.

### Outcomes
- Therapeutics

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Biology
- Therapeutics

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
