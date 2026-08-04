# ACS: Concurrent Kernel Execution on Irregular, Input-Dependent Computational Graphs

## Metadata
- Paper ID: `acfocus_6560e61cd558`
- Cross-SDL ID: `acgold_f698fb325e4d`
- DOI: 10.48550/arxiv.2401.12377
- URL: https://arxiv.org/abs/2401.12377
- Year: 2024
- Authors: Durvasula S, Zhao A, Kiguru R, Guan Y, Chen Z, Vijaykumar N
- Venue: arxiv
- Category: Preprint
- Peer reviewed: Non Peer Reviewed
- AC members: Vijay Narasimhan
- AC programs: Not specified
- AC membership status: N/A
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.42
- Missing: hardware, evidence, materials, properties, measurements, conditions, mechanisms, outcomes
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
Concurrent Kernel Execution on Irregular, Input-Dependent Computational Graphs

## Abstract
ACS: Concurrent Kernel Execution on Irregular,
Input-Dependent Computational Graphs
Sankeerth Durvasula∗, Adrian Zhao∗, Raymond Kiguru, Yushi Guan, Zhonghan Chen, Nandita Vijaykumar
Abstract—GPUs are widely used to accelerate many important
classes of workloads today. However, in this work, we observe
that several important emerging classes of workloads, including
simulation engines for deep reinforcement learning and dynamic
neural networks, are unable to fully utilize the massive paral-
lelism that GPUs offer. These applications tend to have kernels
that are small in size, i.e., have few threads and thread blocks
that cannot saturate the GPU’s compute resources. Executing
independent kernels concurrently is a promising approach to
improve parallelism and utilization. However, this inter-kernel
concurrency is difficult to leverage in such workloads with
existing approaches: First, the inter-kernel dependencies and
computational graph are input-dependent and vary each time the
application is executed. Second, the computational graphs tend to
be irregular, requiring fine-grain scheduling and synchronization;
thus incurring significant synchronization overheads if kernel
execution is parallelized. In this work, we propose ACS, a new
framework that enables lightweight detection of inter-kernel
dependencies and low overhead kernel scheduling at runtime.
The key idea behind ACS is to perform inter-kernel dependency
checks for a small window of kernels at runtime, similar to out-of-
order instruction scheduling. This enables concurrent execution
of kernels in applications whose computational graphs are input-
dependent and require fine-grained scheduling. We propose
ACS-SW, a software-only open-source implementation of ACS
and ACS-HW, a hardware-software cooperative implementation.
ACS-HW further reduces synchronization overheads by reducing
communication between the CPU and GPU. We evaluate ACS
for deep RL simulation engines and dynamic and static DNNs
on both real hardw

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Concurrent Kernel Execution on Irregular, Input-Dependent Computational Graphs

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
- Artificial Intelligence & Data Science

### Reasoning Motifs
- Not specified by cross-SDL extraction.

### General Principles
- Not specified by cross-SDL extraction.

## Failure Paths / Caveats
- No explicit failure path available in CSV/cross-SDL extraction.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_f698fb325e4d.json`
- Cross-SDL extraction quality: 0.0
- Notes: Extraction failed — parse error: Expecting ',' delimiter: line 68 column 4 (char 3863)
