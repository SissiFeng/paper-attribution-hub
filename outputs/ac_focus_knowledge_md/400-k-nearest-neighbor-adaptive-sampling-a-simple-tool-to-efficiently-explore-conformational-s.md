# k-Nearest Neighbor Adaptive Sampling, a Simple Tool to Efficiently Explore Conformational Space

## Metadata
- Paper ID: `acfocus_0973972cfe7e`
- Cross-SDL ID: `not matched`
- DOI: 10.1021/acs.jctc.5c00462
- URL: https://pubs.acs.org/doi/10.1021/acs.jctc.5c00462
- Year: 2025
- Authors: E. Rovers; A. Thudi; J. Hénin; C. J. Maddison; M. Schapira
- Venue: Journal of Chemical Theory and Computation
- Category: Journal Article
- Peer reviewed: Peer Reviewed
- AC members: Matthieu Schapira
- AC programs: Not specified
- AC membership status: AC Full Member
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.37
- Missing: hardware, evidence, entities, materials, measurements, conditions, mechanisms, outcomes, cross_sdl_match
- Notes: No cross-SDL extraction matched this paper; fields are derived from CSV only.; Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
The authors present k-NN adaptive sampling (kNN-AS), a novel and lightweight algorithm that accelerates molecular dynamics simulations by using a k-nearest neighbor graph to prioritize exploration from boundary states, demonstrating superior performance and generalizability to complex biomolecular systems.

## Abstract
Molecular dynamics (MD) simulations are computationally expensive, which is a limiting factor when simulating biomolecular systems. Adaptive sampling approaches can accelerate the exploration of the conformational space by running repeated short MD simulations from well-chosen starting points. Existing approaches to adaptive sampling have been optimized to either guide sampling in a desired direction or explore well-formed convex spaces. Here, we describe a novel adaptive sampling algorithm that leverages a k-nearest neighbor (k-NN) graph of the sampled conformational space to preferentially launch explorations from boundary states. We term this approach k-NN adaptive sampling (kNN-AS) and show state-of-the-art performance on simple and complex artificial energy functions and generalizes well on a protein test case. Implementation of kNN-AS is light, simple, and suited to complex real-world applications where the dimension and shape of the energy landscape is unknown. © 2025 American Chemical Society

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- The authors present k-NN adaptive sampling (kNN-AS), a novel and lightweight algorithm that accelerates molecular dynamics simulations by using a k-nearest neighbor graph to prioritize exploration from boundary states, demonstrating superior performance and generalizability to complex biomolecular systems.

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
- Not specified.

### Properties
- We term this approach k-NN adaptive sampling (kNN-AS) and show state-of-the-art performance on simple and complex artificial energy functions and generalizes well on a protein test case.
- Implementation of kNN-AS is light, simple, and suited to complex real-world applications where the dimension and shape of the energy landscape is unknown.

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
