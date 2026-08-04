# ORBIT-Surgical: An Open-Simulation Framework for Learning Surgical Augmented Dexterity

## Metadata
- Paper ID: `acfocus_fe8f6d2b6d95`
- Cross-SDL ID: `acgold_bcb5f344c646`
- DOI: 10.48550/arxiv.2404.16027
- URL: https://arxiv.org/abs/2404.16027
- Year: 2024
- Authors: Yu, Qinxi; Moghani, Masoud; Dharmarajan, Karthik; Schorp, Vincent; Panitch, William Chung-Ho; Liu, Jingzhou; Hari, Kush; Huang, Huang; Mittal, Mayank; Goldberg, Ken; Garg, Animesh
- Venue: arxiv
- Category: Preprint
- Peer reviewed: Non Peer Reviewed
- AC members: Animesh Garg
- AC programs: Not specified
- AC membership status: AC Full Member
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.89
- Missing: properties, conditions
- Notes: No validation notes.

## Source Summary
ORBIT-Surgical is a physics-based surgical robot simulation framework with photorealistic rendering that enables reinforcement and imitation learning for surgical tasks, provides benchmarks for dVRK and STAR robots, supports realistic data generation, and demonstrates sim-to-real policy transfer.

## Abstract
Physics-based simulations have accelerated progress in robot learning for driving, manipulation, and locomotion. Yet, a fast, accurate, and robust surgical simulation environment remains a challenge. In this paper, we present ORBIT-Surgical, a physics-based surgical robot simulation framework with photorealistic rendering in NVIDIA Omniverse. We provide 14 benchmark surgical tasks for the da Vinci Research Kit (dVRK) and Smart Tissue Autonomous Robot (STAR) which represent common subtasks in surgical training. ORBIT-Surgical leverages GPU parallelization to train reinforcement learning and imitation learning algorithms to facilitate study of robot learning to augment human surgical skills. ORBIT-Surgical also facilitates realistic synthetic data generation for active perception tasks. We demonstrate ORBIT-Surgical sim-to-real transfer of learned policies onto a physical dVRK robot. Project website: orbit-surgical.github.io

## Scientific Elements
### Hardware / Physical System
- ORBIT-Surgical is a physics-based surgical robot simulation framework with photorealistic rendering that enables reinforcement and imitation learning for surgical tasks, provides benchmarks for dVRK and STAR robots, supports realistic data generation, and demonstrates sim-to-real policy transfer.
- Physics-based simulations have accelerated progress in robot learning for driving, manipulation, and locomotion.
- In this paper, we present ORBIT-Surgical, a physics-based surgical robot simulation framework with photorealistic rendering in NVIDIA Omniverse.
- We provide 14 benchmark surgical tasks for the da Vinci Research Kit (dVRK) and Smart Tissue Autonomous Robot (STAR) which represent common subtasks in surgical training.

### Method
- Creation of ORBIT-Surgical, a simulation framework based on NVIDIA Isaac Sim, providing GPU-accelerated physics, contact-rich physical interactions, and high-fidelity rendering.

### Problem
- Developing a fast, accurate, and robust surgical simulation environment for robot learning.

### Hypothesis
- A physics-based surgical robot simulation framework with photorealistic rendering can facilitate study of robot learning to augment human surgical skills.

### Evidence
- Successful sim-to-real transfer of learned policies onto a physical dVRK robot, high learning speed facilitated by ORBIT-Surgical, and improved perception performance by over 2× using synthetic data generation.

### Conclusion
- ORBIT-Surgical enables efficient training of reinforcement learning policies for surgical robotics tasks and high-fidelity synthetic data generation, accelerating progress in learning-based assistive autonomy in robotic surgery.

## Scientific Objects And Mechanisms
### Entities
- ORBIT-Surgical simulation framework
- da Vinci Research Kit (dVRK)
- Smart Tissue Autonomous Robot (STAR)
- Rigid and deformable surgical materials

### Materials / Systems
- Rigid and deformable surgical materials
- ORBIT-Surgical simulation framework da Vinci Research Kit (dVRK) Smart Tissue Autonomous Robot (STAR) Rigid and deformable surgical materials Augmented human surgical skills through robot learning Realistic interactions with both rigid and deformable materials in surgical training Improved perception performance in surgical tool segmentation

### Properties
- Not specified.

### Measurements
- We provide 14 benchmark surgical tasks for the da Vinci Research Kit (dVRK) and Smart Tissue Autonomous Robot (STAR) which represent common subtasks in surgical training.

### Conditions
- Not specified.

### Mechanisms
- GPU parallelization for fast simulation
- Reinforcement learning and imitation learning algorithms for policy training
- Synthetic data generation for active perception tasks

### Outcomes
- Augmented human surgical skills through robot learning
- Realistic interactions with both rigid and deformable materials in surgical training
- Improved perception performance in surgical tool segmentation

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Automation and Robotics

### Reasoning Motifs
- Simulation Fidelity → Real-World Performance
- Data Augmentation → Improved Perception
- Parallelization → Accelerated Learning

### General Principles
- High Fidelity Simulation Enhances Learning
- Data Augmentation Improves Model Generalization
- Parallel Processing Accelerates Computational Tasks

## Failure Paths / Caveats
- partial: Deploying a PPO policy trained with RSL-rl on the Suture Needle Lift task in Cartesian space on a real dVRK setup. Evidence: The transferred policy achieved a 50% success rate.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_bcb5f344c646.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper provides a clear structure for the development and evaluation of the ORBIT-Surgical simulation framework, with explicit hypotheses, methods, and results. However, some details on the underlying mechanisms and principles were inferred from the paper's content, as not all causal relationships were explicitly stated.
