# DISORF: A Distributed Online 3D Reconstruction Framework for Mobile Robots

## Metadata
- Paper ID: `acfocus_e204ae3e82a2`
- Cross-SDL ID: `acgold_2af7adc76b0f`
- DOI: 10.48550/arxiv.2403.00228
- URL: https://arxiv.org/abs/2403.00228
- Year: 2024
- Authors: Li C, Fan H, Huang X, Liang R, Durvasula S, Vijaykumar N
- Venue: arxiv
- Category: Preprint
- Peer reviewed: Non Peer Reviewed
- AC members: Vijay Narasimhan
- AC programs: Not specified
- AC membership status: N/A
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.22
- Missing: source_summary, hardware, method, evidence, materials, properties, measurements, conditions, mechanisms, outcomes
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
Not specified in CSV.

## Abstract
DISORF: A Distributed Online 3D Reconstruction Framework for
Mobile Robots
Chunlin Li1∗, Hanrui Fan1∗, Xiaorui Huang1∗, Ruofan Liang2, Sankeerth Durvasula2, Nandita Vijaykumar2
Abstract— We present a framework, DISORF, to enable
online 3D reconstruction and visualization of scenes captured
by resource-constrained mobile robots and edge devices. To
address the limited computing capabilities of edge devices and
potentially limited network availability, we design a framework
that efficiently distributes computation between the edge device
and the remote server. We leverage on-device SLAM systems
to generate posed keyframes and transmit them to remote
servers that can perform high-quality 3D reconstruction and
visualization at runtime by leveraging recent advances in neural
3D methods. We identify a key challenge with online training
where naive image sampling strategies can lead to significant
degradation in rendering quality. We propose a novel shifted ex-
ponential frame sampling method that addresses this challenge
for online training. We demonstrate the effectiveness of our
framework in enabling high-quality real-time reconstruction
and visualization of unknown scenes as they are captured and
streamed from cameras in mobile robots and edge devices.
Index Terms— Visual Learning, Incremental Learning, Dis-
tributed Robot Systems, Mapping
I. INTRODUCTION
Online 3D reconstruction to learn a representation of a
scene at real-time—where RGB images are continuously
captured and used to optimize a 3D model that can be
rendered and visualized—holds immense potential in various
domains. For example, mobile robots and embodied devices
(e.g., drones) navigating a previously unseen environment
with the ability to construct and visualize a 3D model of
the environment on the fly, offer opportunities for enhanced
navigation, scene understanding, and interactive exploration
of the environment. Online 3D scene reconstruction has
been extensively studied with various methods to repre

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Not specified.

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
- Automation and Robotics

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
- Automation and Robotics

### Reasoning Motifs
- Not specified by cross-SDL extraction.

### General Principles
- Not specified by cross-SDL extraction.

## Failure Paths / Caveats
- No explicit failure path available in CSV/cross-SDL extraction.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_2af7adc76b0f.json`
- Cross-SDL extraction quality: 0.0
- Notes: Extraction failed — parse error: Expecting ',' delimiter: line 60 column 4 (char 3351)
