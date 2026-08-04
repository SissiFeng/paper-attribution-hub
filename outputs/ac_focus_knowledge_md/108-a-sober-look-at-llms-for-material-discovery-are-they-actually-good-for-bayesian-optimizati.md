# A Sober Look at LLMs for Material Discovery: Are They Actually Good for Bayesian Optimization Over Molecules?

## Metadata
- Paper ID: `acfocus_cec5e0d2199b`
- Cross-SDL ID: `acgold_9bd23f1c5c24`
- DOI: 10.48550/arxiv.2402.05015
- URL: https://arxiv.org/abs/2402.05015
- Year: 2024
- Authors: Kristiadi A, Strieth-Kalthoff F, Skreta M, Poupart P, Aspuru-Guzik A, Pleiss G
- Venue: arXiv
- Category: Conference
- Peer reviewed: Peer Reviewed
- AC members: Alán Aspuru-Guzik
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.73
- Missing: hardware, properties, measurements, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
This work investigates whether large language models (LLMs) can effectively accelerate principled Bayesian optimization in molecular discovery, finding that LLMs are beneficial for Bayesian optimization only when pretrained or finetuned with domain-specific data.

## Abstract
Automation is one of the cornerstones of contemporary material discovery. Bayesian optimization (BO) is an essential part of such workflows, enabling scientists to leverage prior domain knowledge into efficient exploration of a large molecular space. While such prior knowledge can take many forms, there has been significant fanfare around the ancillary scientific knowledge encapsulated in large language models (LLMs). However, existing work thus far has only explored LLMs for heuristic materials searches. Indeed, recent work obtains the uncertainty estimate-an integral part of BO-from point-estimated, non-Bayesian LLMs. In this work, we study the question of whether LLMs are actually useful to accelerate principled Bayesian optimization in the molecular space. We take a sober, dispassionate stance in answering this question. This is done by carefully (i) viewing LLMs as fixed feature extractors for standard but principled BO surrogate models and by (ii) leveraging parameter-efficient finetuning methods and Bayesian neural networks to obtain the posterior of the LLM surrogate. Our extensive experiments with real-world chemistry problems show that LLMs can be useful for BO over molecules, but only if they have been pretrained or finetuned with domain-specific data.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Compare BO performance using LLMs as fixed feature extractors versus finetuned LLMs, with domain-specific and general-purpose LLMs.

### Problem
- Determine whether large language models (LLMs) are effective for accelerating Bayesian optimization (BO) in molecular space.

### Hypothesis
- LLMs can provide useful features for BO over molecules when pretrained or finetuned with domain-specific data.

### Evidence
- Experiments with 8 real-world chemistry problems using various LLMs show that domain-specific LLMs and finetuned LLMs improve BO performance.

### Conclusion
- LLMs can be useful for BO over molecules if they are pretrained or finetuned with domain-specific data.

## Scientific Objects And Mechanisms
### Entities
- Large language models (LLMs)
- Bayesian optimization (BO) surrogate models
- Domain-specific data

### Materials / Systems
- A Sober Look at LLMs for Material Discovery: Are They Actually Good for Bayesian Optimization Over Molecules?
- Automation is one of the cornerstones of contemporary material discovery.
- However, existing work thus far has only explored LLMs for heuristic materials searches.

### Properties
- Not specified.

### Measurements
- Not specified.

### Conditions
- Not specified.

### Mechanisms
- Feature extraction from LLMs for BO
- Parameter-efficient finetuning of LLMs
- Incorporation of domain-specific data in LLM training

### Outcomes
- Improved BO performance with domain-specific LLMs
- Enhanced BO performance through finetuning
- Better generalization of LLMs to chemistry problems with domain-specific training

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Chemistry

### Reasoning Motifs
- Domain-specific data → Improved generalization
- Finetuning → Enhanced performance
- Feature quality → BO efficiency

### General Principles
- Adaptation through domain-specific learning
- Performance enhancement through targeted finetuning
- Efficiency through feature relevance

## Failure Paths / Caveats
- failure: Using general-purpose LLMs as feature extractors for BO. Evidence: General-purpose LLMs tend to underperform compared to domain-specific LLMs.
- failure: Employing in-context learning with non-Bayesian LLMs for BO. Evidence: Non-Bayesian uncertainties from in-context learning may not be optimal for the exploration-exploitation tradeoff in BO.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_9bd23f1c5c24.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper provides a structured exploration of LLMs in the context of BO for molecular discovery, allowing for a clear extraction of the scientific reasoning. However, some details on the specific experimental setups and data preprocessing steps were not fully detailed, requiring some assumptions during extraction.
