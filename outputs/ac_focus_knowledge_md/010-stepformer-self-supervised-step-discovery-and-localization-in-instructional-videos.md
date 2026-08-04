# StepFormer: Self-supervised Step Discovery and Localization in Instructional Videos

## Metadata
- Paper ID: `acfocus_7fc8fece34da`
- Cross-SDL ID: `acgold_1bf9ddc41484`
- DOI: 10.48550/arxiv.2304.13265
- URL: https://arxiv.org/abs/2304.13265
- Year: 2023
- Authors: Dvornik, Nikita; Hadji, Isma; Zhang, Ran; Derpanis, Konstantinos G.; Garg, Animesh; Wildes, Richard P.; Jepson, Allan D.
- Venue: arxiv
- Category: Preprint
- Peer reviewed: Non Peer Reviewed
- AC members: Animesh Garg
- AC programs: Not specified
- AC membership status: AC Full Member
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.73
- Missing: hardware, materials, measurements, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
StepFormer is a self-supervised transformer model that uses only automatically-generated subtitles to discover and localize key instruction steps in instructional videos, outperforming previous unsupervised and weakly-supervised methods on multiple benchmarks.

## Abstract
Instructional videos are an important resource to learn procedural tasks from human demonstrations. However, the instruction steps in such videos are typically short and sparse, with most of the video being irrelevant to the procedure. This motivates the need to temporally localize the instruction steps in such videos, i.e. the task called key-step localization. Traditional methods for key-step localization require video-level human annotations and thus do not scale to large datasets. In this work, we tackle the problem with no human supervision and introduce StepFormer, a self-supervised model that discovers and localizes instruction steps in a video. StepFormer is a transformer decoder that attends to the video with learnable queries, and produces a sequence of slots capturing the key-steps in the video. We train our system on a large dataset of instructional videos, using their automatically-generated subtitles as the only source of supervision. In particular, we supervise our system with a sequence of text narrations using an order-aware loss function that filters out irrelevant phrases. We show that our model outperforms all previous unsupervised and weakly-supervised approaches on step detection and localization by a large margin on three challenging benchmarks. Moreover, our model demonstrates an emergent property to solve zero-shot multi-step localization and outperforms all relevant baselines at this task.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- The proposed model, StepFormer, is a transformer decoder that attends to the video with learnable queries and produces a sequence of slots capturing the key-steps in the video. It is trained using an order-aware loss function that filters out irrelevant phrases from the subtitles.

### Problem
- Temporally localizing instruction steps in instructional videos, which are typically long and noisy with only a limited number of frames corresponding to the instruction steps.

### Hypothesis
- A self-supervised model can discover and localize instruction steps in videos without human annotations by using automatically-generated subtitles as the only source of supervision.

### Evidence
- The model outperforms previous unsupervised and weakly-supervised approaches on step detection and localization across three challenging benchmarks: CrossTask, ProceL, and COIN.

### Conclusion
- StepFormer demonstrates the ability to effectively discover and localize instruction steps in instructional videos in a self-supervised manner, establishing a new state of the art in this domain.

## Scientific Objects And Mechanisms
### Entities
- Instructional videos
- Subtitles (text narrations)
- Step slots (output of StepFormer)

### Materials / Systems
- Not specified.

### Properties
- Moreover, our model demonstrates an emergent property to solve zero-shot multi-step localization and outperforms all relevant baselines at this task.
- Instructional videos Subtitles (text narrations) Step slots (output of StepFormer) Improved step detection and localization in instructional videos Model generalizes well across different datasets without fine-tuning Emergent property of zero-shot multi-step localization from text prompts

### Measurements
- Not specified.

### Conditions
- Not specified.

### Mechanisms
- Sequence-to-sequence alignment for matching video content with subtitle narrations
- Order-aware loss function for enforcing the temporal order of step slots
- Self-supervised training using automatically-generated subtitles as the only supervision source

### Outcomes
- Improved step detection and localization in instructional videos
- Model generalizes well across different datasets without fine-tuning
- Emergent property of zero-shot multi-step localization from text prompts

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Automation and Robotics

### Reasoning Motifs
- Sequence alignment → Temporal correspondence
- Irrelevant content filtering → Relevant signal enhancement
- Self-supervision → Generalization

### General Principles
- Signal enhancement through noise reduction
- Generalization through minimal supervision

## Failure Paths / Caveats
- failure: Training StepFormer without the sequence-to-sequence alignment loss (Lseq). Evidence: Performance severely degraded, especially on zero-shot key-step localization.
- failure: Training StepFormer without the global contrastive learning loss (Lglobal). Evidence: Impaired performance on both unsupervised step segmentation and zero-shot key-step localization.
- partial: Training StepFormer without diversity (Ldiv) and smoothness (Lsmooth) regularizers. Evidence: Mildly hurts unsupervised step segmentation performance, more noticeable drop in zero-shot key-step localization.
- failure: Replacing Drop-DTW sequence alignment in inference with an order-agnostic procedure. Evidence: Notable drop in performance on zero-shot key-step localization where step order is essential.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_1bf9ddc41484.json`
- Cross-SDL extraction quality: 0.9
- Notes: The paper is highly structured with explicit hypotheses, methods, and results, making the extraction process straightforward. The reasoning is clear, and the conclusions are well-supported by the experiments.
