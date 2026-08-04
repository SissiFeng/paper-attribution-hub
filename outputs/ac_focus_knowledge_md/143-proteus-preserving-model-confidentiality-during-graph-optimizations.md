# Proteus: Preserving Model Confidentiality during Graph Optimizations

## Metadata
- Paper ID: `acfocus_6e4365274953`
- Cross-SDL ID: `acgold_b869899478b2`
- DOI: 10.48550/arxiv.2404.12512
- URL: https://arxiv.org/abs/2404.12512
- Year: 2024
- Authors: Gao Y, Haghifam M, Giannoula C, Tu R, Pekhimenko G, Vijaykumar N
- Venue: arxiv
- Category: Preprint
- Peer reviewed: Non Peer Reviewed
- AC members: Vijay Narasimhan
- AC programs: Not specified
- AC membership status: N/A
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.58
- Missing: source_summary, hardware, materials, properties, measurements, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
Not specified in CSV.

## Abstract
PROTEUS: PRESERVING MODEL CONFIDENTIALITY DURING GRAPH
OPTIMIZATIONS
Yubo Gao 1 2 3 Maryam Haghifam 1 Christina Giannoula 1 3 Renbo Tu 1 Gennady Pekhimenko 1 2 3
Nandita Vijaykumar 1 2
ABSTRACT
Deep learning (DL) models have revolutionized numerous domains, yet optimizing them for computational
efficiency remains a challenging endeavor. Development of new DL models typically involves two parties: the
model developers and performance optimizers. The collaboration between the parties often necessitates the
model developers exposing the model architecture and computational graph to the optimizers. However, this
exposure is undesirable since the model architecture is an important intellectual property, and its innovations
require significant investments and expertise. During the exchange, the model is also vulnerable to adversarial
attacks via model stealing.
This paper presents PROTEUS, a novel mechanism that enables model optimization by an independent party
while preserving the confidentiality of the model architecture. PROTEUS obfuscates the protected model by
partitioning its computational graph into subgraphs and concealing each subgraph within a large pool of generated
realistic subgraphs that cannot be easily distinguished from the original. We evaluate PROTEUS on a range of
DNNs, demonstrating its efficacy in preserving confidentiality without compromising performance optimization
opportunities. PROTEUS effectively hides the model as one alternative among up to 1032 possible model
architectures, and is resilient against attacks with a learning-based adversary. We also demonstrate that heuristic
based and manual approaches are ineffective in identifying the protected model. To our knowledge, PROTEUS is
the first work that tackles the challenge of model confidentiality during performance optimization. PROTEUS will
be open-sourced for direct use and experimentation, with easy integration with compilers such as ONNXRuntime.
1
INTRODUCTION
Deep learning (DL) has eme

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Developing PROTEUS, a novel obfuscation mechanism that partitions the model's computational graph into subgraphs and conceals each within a pool of generated realistic subgraphs, making it difficult to distinguish the original from the decoys.

### Problem
- Optimizing deep learning models for computational efficiency while preserving the confidentiality of the model architecture during the optimization process.

### Hypothesis
- A mechanism can enable independent model optimization by obfuscating the model's computational graph, preventing the retrieval of the original architecture while still allowing performance optimization.

### Evidence
- PROTEUS demonstrated efficacy in preserving confidentiality without compromising performance optimization opportunities across a range of DNNs, hiding the model as one among up to 10^32 possible architectures and showing resilience against learning-based adversary attacks.

### Conclusion
- PROTEUS effectively enables model optimization by an independent party while preserving the confidentiality of the model architecture, tackling the challenge of model confidentiality during performance optimization.

## Scientific Objects And Mechanisms
### Entities
- DL model
- computational graph
- subgraphs
- sentinel graphs

### Materials / Systems
- Not specified.

### Properties
- Not specified.

### Measurements
- Not specified.

### Conditions
- Not specified.

### Mechanisms
- graph partitioning into subgraphs
- generation of sentinel subgraphs resembling real DL computational graphs
- obfuscation of protected model by mixing protected subgraphs with sentinels

### Outcomes
- preservation of model confidentiality
- enabling independent performance optimization without exposing the original model architecture
- resilience against adversarial attacks aiming to recover the original model

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science

### Reasoning Motifs
- Obfuscation → Confidentiality
- Artificial Mimicry → Deception
- Partitioning → Exposure Limitation

### General Principles
- Control Through Obfuscation
- Deception Through Mimicry
- Privacy Through Partitioning

## Failure Paths / Caveats
- failure: Learning-based adversarial attack to distinguish real subgraphs from sentinels. Evidence: The attack was unable to distinguish the real protected model from a pool of 10^7 to 10^32 potential model architectures.
- failure: Manual identification of sentinels by ML researchers through visual inspection. Evidence: The average accuracy of classification was 52%, similar to random guessing, indicating ineffectiveness of manual identification.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_b869899478b2.json`
- Cross-SDL extraction quality: 0.9
- Notes: The paper presents a structured approach to a novel problem in deep learning model optimization, providing clear hypotheses, methods, and evaluations. The reasoning is explicit, and the conclusions are well-supported by the evidence presented.
