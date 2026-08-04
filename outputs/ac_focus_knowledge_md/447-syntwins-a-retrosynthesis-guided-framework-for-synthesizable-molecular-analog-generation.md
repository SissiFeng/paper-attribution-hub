# SynTwins: a retrosynthesis-guided framework for synthesizable molecular analog generation

## Metadata
- Paper ID: `acfocus_be85cb7b4086`
- Cross-SDL ID: `acgold_c5840f9efa9c`
- DOI: 10.1039/d5sc05225d
- URL: https://pubs.rsc.org/en/content/articlelanding/2026/sc/d5sc05225d
- Year: 2025
- Authors: S. Chen; G. Nam; A. Aspuru-Guzik; Y. Jung
- Venue: Chemical Science
- Category: Journal Article
- Peer reviewed: Peer Reviewed
- AC members: Alán Aspuru-Guzik, Alan Veerman
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance, N/A
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.86
- Missing: hardware, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
SynTwins is a retrosynthesis-guided molecule design framework that outperforms existing AI models by efficiently generating synthetically accessible molecular analogs with high structural similarity and desirable properties, thus bridging the gap between computational design and experimental synthesis.

## Abstract
The disconnect between AI-generated molecules with desirable properties and their synthetic feasibility remains a critical bottleneck in computational discovery of drugs and materials. While generative AI has accelerated the proposal of candidate molecules, many of these structures prove challenging or impossible to synthesize using established chemical reactions. Here, we introduce SynTwins, a novel retrosynthesis-guided molecule design framework that finds synthetically accessible molecular analogs by emulating expert chemists' strategies in three steps: retrosynthesis, searching similar building blocks, and virtual synthesis. Using a search algorithm instead of a stochastic data-driven generator, SynTwins outperforms state-of-the-art machine learning models at exploring synthetically accessible analogs while maintaining high structural similarity to original target molecules. Furthermore, when integrated into existing molecular property-optimization frameworks, our hybrid approach produces synthetically feasible analogs with minimal loss in property scores. Our comprehensive benchmarking across diverse molecular datasets demonstrates that SynTwins effectively bridges the gap between computational design and experimental synthesis, providing a practical solution for accelerating the discovery of synthesizable molecules with desired properties for a wide range of applications.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- A novel retrosynthesis-guided molecule design framework that emulates expert chemists' strategies in three steps: retrosynthesis, searching similar building blocks, and virtual synthesis

### Problem
- The disconnect between AI-generated molecules with desirable properties and their synthetic feasibility

### Hypothesis
- SynTwins can generate synthetically accessible molecular analogs that maintain high structural similarity to original target molecules

### Evidence
- SynTwins outperforms state-of-the-art machine learning models at exploring synthetically accessible analogs while maintaining high structural similarity to original target molecules

### Conclusion
- SynTwins effectively bridges the gap between computational design and experimental synthesis, providing a practical solution for accelerating the discovery of synthesizable molecules with desired properties

## Scientific Objects And Mechanisms
### Entities
- Target molecule
- Precursors
- Building blocks
- Molecular analogs

### Materials / Systems
- Target molecule
- SynTwins: a retrosynthesis-guided framework for synthesizable molecular analog generation SynTwins is a retrosynthesis-guided molecule design framework that outperforms existing AI models by efficiently generating synthetically accessible molecular analogs with high structural similarity and desirable properties, thus bridging the gap between computational design and experimental synthesis.
- The disconnect between AI-generated molecules with desirable properties and their synthetic feasibility remains a critical bottleneck in computational discovery of drugs and materials.
- While generative AI has accelerated the proposal of candidate molecules, many of these structures prove challenging or impossible to synthesize using established chemical reactions.

### Properties
- SynTwins: a retrosynthesis-guided framework for synthesizable molecular analog generation SynTwins is a retrosynthesis-guided molecule design framework that outperforms existing AI models by efficiently generating synthetically accessible molecular analogs with high structural similarity and desirable properties, thus bridging the gap between computational design and experimental synthesis.
- The disconnect between AI-generated molecules with desirable properties and their synthetic feasibility remains a critical bottleneck in computational discovery of drugs and materials.
- Furthermore, when integrated into existing molecular property-optimization frameworks, our hybrid approach produces synthetically feasible analogs with minimal loss in property scores.
- Our comprehensive benchmarking across diverse molecular datasets demonstrates that SynTwins effectively bridges the gap between computational design and experimental synthesis, providing a practical solution for accelerating the discovery of synthesizable molecules with desired properties for a wide range of applications.
- A novel retrosynthesis-guided molecule design framework that emulates expert chemists' strategies in three steps: retrosynthesis, searching similar building blocks, and virtual synthesis SynTwins outperforms state-of-the-art machine learning models at exploring synthetically accessible analogs while maintaining high structural similarity to original target molecules Target molecule Precursors Building blocks Molecular analogs Structurally similar and synthetically accessible molecular analogs Enable systematic property optimization Discover alternative routes using available chemistry components

### Measurements
- Our comprehensive benchmarking across diverse molecular datasets demonstrates that SynTwins effectively bridges the gap between computational design and experimental synthesis, providing a practical solution for accelerating the discovery of synthesizable molecules with desired properties for a wide range of applications.

### Conditions
- Not specified.

### Mechanisms
- Retrosynthetic analysis to identify key structural components
- Searching for similar yet readily available building blocks that maintain essential pharmacophores
- Virtual synthesis using well-established reaction templates to assemble the final molecular analog

### Outcomes
- Structurally similar and synthetically accessible molecular analogs
- Enable systematic property optimization
- Discover alternative routes using available chemistry components

## Cross-SDL Transfer
### SDL / Domain Tags
- Not specified.

### Reasoning Motifs
- Decomposition → Reconstruction
- Constraint → Feasibility
- Similarity → Analogy

### General Principles
- Control Through Constraints
- Multi-scale Coupling

## Failure Paths / Caveats
- failure: Generating molecular analogs using existing machine learning models Evidence: Existing models typically achieve suboptimal structural similarity to target molecules, limiting their practical utility

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_c5840f9efa9c.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper presents a clear problem statement, hypothesis, and methodology. The reasoning structure is well-organized, but some details are buried in the supplementary information. The extraction relies on inferring the underlying mechanisms and motifs from the described approach.
