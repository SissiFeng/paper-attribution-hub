# Automated electrosynthesis reaction mining with multimodal large language models (MLLMs)

## Metadata
- Paper ID: `acfocus_752322d0d603`
- Cross-SDL ID: `acgold_080d923904b3`
- DOI: 10.26434/chemrxiv-2024-7fwxv
- URL: https://chemrxiv.org/doi/full/10.26434/chemrxiv-2024-7fwxv
- Year: 2024
- Authors: Leong SX, Pablo-García S, Zhang Z, Aspuru-Guzik A
- Venue: ChemRxiv
- Category: Preprint
- Peer reviewed: Non Peer Reviewed
- AC members: Alán Aspuru-Guzik
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.96
- Missing: conditions
- Notes: No validation notes.

## Source Summary
This work introduces MERMES, an end-to-end multimodal large language model (MLLM)-powered toolkit that integrates article retrieval, information extraction, and multimodal analysis to automate and streamline knowledge extraction from diverse data formats in electrosynthesis research, achieving ≥96% accuracy in key tasks and paving the way for accelerated digitization of chemistry knowledge.

## Abstract
Leveraging the chemical data that is available in legacy formats such as publications and patents is a significant challenge for the community. Automated reaction mining offers a promising solution to unleash this knowledge into a learnable digital form and therefore help expedite materials and reaction discovery. However, existing reaction mining toolkits are limited to single input modalities (text or images) and cannot effectively integrate heterogeneous data that is scattered across different modalities including text, tables, and figures. In this work, we go beyond single input modalities and explore multimodal large language models (MLLMs) for the analysis of diverse data inputs for automated electrosynthesis reaction mining. We compiled a test dataset of 65 articles and employed it to benchmark five prominent MLLMs against two critical tasks: (i) reaction diagram parsing and (ii) resolving cross-modality data interdependencies. The frontrunner MLLM achieved ≥ 96% accuracy in both tasks, with the strategic integration of single-shot visual prompts and image pre-processing techniques. We integrate this capability into a toolkit named MERMES (Multimodal Reaction Mining pipeline for ElectroSynthesis). Our toolkit functions as an end-to-end MLLM-powered pipeline that integrates article retrieval, information extraction and multimodal analysis for streamlining and automating knowledge extraction. This work lays the groundwork for the increased utilization of MLLMs to accelerate the digitization of chemistry knowledge for data-driven research.

## Scientific Elements
### Hardware / Physical System
- Automated reaction mining offers a promising solution to unleash this knowledge into a learnable digital form and therefore help expedite materials and reaction discovery.
- In this work, we go beyond single input modalities and explore multimodal large language models (MLLMs) for the analysis of diverse data inputs for automated electrosynthesis reaction mining.

### Method
- Benchmarking five prominent MLLMs against two critical tasks: reaction diagram parsing and resolving cross-modality data interdependencies using a test dataset of 65 articles (MERMES-T24 set).

### Problem
- Leveraging chemical data available in legacy formats such as publications and patents for materials and reaction discovery

### Hypothesis
- Multimodal large language models (MLLMs) can effectively process and integrate textual and visual inputs from scientific literature for specialized, domain-specific tasks such as reaction mining.

### Evidence
- The frontrunner MLLM achieved 96% accuracy in both tasks, with the strategic integration of single-shot visual prompts and image pre-processing techniques.

### Conclusion
- MLLMs exhibit multi-modal cognition capabilities that are suitable for chemical applications, laying the groundwork for the increased utilization of MLLMs to accelerate the digitization of chemistry knowledge for data-driven research.

## Scientific Objects And Mechanisms
### Entities
- MLLMs
- reaction diagrams
- cross-modality data interdependencies

### Materials / Systems
- Automated reaction mining offers a promising solution to unleash this knowledge into a learnable digital form and therefore help expedite materials and reaction discovery.

### Properties
- Automated electrosynthesis reaction mining with multimodal large language models (MLLMs) This work introduces MERMES, an end-to-end multimodal large language model (MLLM)-powered toolkit that integrates article retrieval, information extraction, and multimodal analysis to automate and streamline knowledge extraction from diverse data formats in electrosynthesis research, achieving ≥96% accuracy in key tasks and paving the way for accelerated digitization of chemistry knowledge.
- The frontrunner MLLM achieved ≥ 96% accuracy in both tasks, with the strategic integration of single-shot visual prompts and image pre-processing techniques.
- The frontrunner MLLM achieved 96% accuracy in both tasks, with the strategic integration of single-shot visual prompts and image pre-processing techniques.

### Measurements
- We compiled a test dataset of 65 articles and employed it to benchmark five prominent MLLMs against two critical tasks: (i) reaction diagram parsing and (ii) resolving cross-modality data interdependencies.
- Benchmarking five prominent MLLMs against two critical tasks: reaction diagram parsing and resolving cross-modality data interdependencies using a test dataset of 65 articles (MERMES-T24 set).

### Conditions
- Not specified.

### Mechanisms
- multimodal cognition skills for information assimilation
- text-based preconditioning prompts for in-context learning
- image cropping for information overload management

### Outcomes
- accurate parameter identification and role assignment in reaction diagrams
- resolution of cross-modality data interdependencies with high F1 scores

## Cross-SDL Transfer
### SDL / Domain Tags
- SDL 0 - AI & Automation
- Chemistry
- Materials Science
- Artificial Intelligence & Data Science

### Reasoning Motifs
- Data Integration → Comprehensive Knowledge
- Contextual Cues → Accurate Interpretation
- Preprocessing → Enhanced Performance

### General Principles
- Information Integration for Enhanced Understanding
- Adaptability through Contextual Learning
- Optimization of Data Processing

## Failure Paths / Caveats
- failure: Benchmarking ReactionDataExtractor2.0 and RxnScribe against MLLMs for reaction diagram parsing. Evidence: ReactionDataExtractor2.0 and RxnScribe struggled to parse electrosynthesis reaction diagrams accurately, achieving softmatch accuracies ranging from 23–36% to 50–99% on the test dataset.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_080d923904b3.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper presents a structured approach to evaluating MLLMs for reaction mining tasks, but some details of the reasoning process, such as specific challenges faced during the development of MERMES, are not explicitly detailed.
