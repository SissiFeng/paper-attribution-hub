# QueST: Self-Supervised Skill Abstractions for Learning Continuous Control

## Metadata
- Paper ID: `acfocus_7e47c58cf4bc`
- Cross-SDL ID: `not matched`
- DOI: 10.52202/079017-0133
- URL: https://proceedings.neurips.cc/paper_files/paper/2024/file/076c3e48fa502c660902105965fdd9f6-Paper-Conference.pdf
- Year: 2024
- Authors: Mete A, Xue H, Wilcox A, Chen Y, Garg A
- Venue: Advances in Neural Information Processing Systems
- Category: Conference
- Peer reviewed: Peer Reviewed
- AC members: Animesh Garg
- AC programs: Not specified
- AC membership status: AC Full Member
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=checked

## Validation
- Score: 0.4
- Missing: evidence, entities, materials, properties, measurements, conditions, mechanisms, outcomes, cross_sdl_match
- Notes: No cross-SDL extraction matched this paper; fields are derived from CSV only.

## Source Summary
The paper introduces Quantized Skill Transformer (QueST), a latent variable model that improves generalization in robot learning by learning flexible, causally-structured latent representations of low-level skills, outperforming existing imitation learning and LVM baselines on multitask and few-shot benchmarks.

## Abstract
Generalization capabilities, or rather a lack thereof, is one of the most important unsolved problems in the field of robot learning, and while several large scale efforts have set out to tackle this problem, unsolved it remains. In this paper, we hypothesize that learning temporal action abstractions using latent variable models (LVMs), which learn to map data to a compressed latent space and back, is a promising direction towards low-level skills that can readily be used for new tasks. Although several works have attempted to show this, they have generally been limited by architectures that do not faithfully capture sharable representations. To address this we present Quantized Skill Transformer (QueST), which learns a larger and more flexible latent encoding that is more capable of modeling the breadth of low-level skills necessary for a variety of tasks. To make use of this extra flexibility, QueST imparts causal inductive bias from the action sequence data into the latent space, leading to more semantically useful and transferable representations. We compare to state-of-the-art imitation learning and LVM baselines and see that QueST's architecture leads to strong performance on several multitask and fewshot learning benchmarks. Further results and videos are available at https://quest-model.github.io.

## Scientific Elements
### Hardware / Physical System
- The paper introduces Quantized Skill Transformer (QueST), a latent variable model that improves generalization in robot learning by learning flexible, causally-structured latent representations of low-level skills, outperforming existing imitation learning and LVM baselines on multitask and few-shot benchmarks.
- Generalization capabilities, or rather a lack thereof, is one of the most important unsolved problems in the field of robot learning, and while several large scale efforts have set out to tackle this problem, unsolved it remains.

### Method
- The paper introduces Quantized Skill Transformer (QueST), a latent variable model that improves generalization in robot learning by learning flexible, causally-structured latent representations of low-level skills, outperforming existing imitation learning and LVM baselines on multitask and few-shot benchmarks.

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
- Not specified.

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
