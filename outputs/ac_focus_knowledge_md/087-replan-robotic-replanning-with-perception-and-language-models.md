# RePLan: Robotic Replanning with Perception and Language Models

## Metadata
- Paper ID: `acfocus_011ccea52093`
- Cross-SDL ID: `acgold_416318135a95`
- DOI: 10.48550/arxiv.2401.04157
- URL: https://arxiv.org/abs/2401.04157
- Year: 2024
- Authors: Skreta, Marta; Zhou, Zihan; Yuan, Jia Lin; Darvish, Kourosh; Aspuru-Guzik, Alán; Garg, Animesh
- Venue: arxiv
- Category: Preprint
- Peer reviewed: Non Peer Reviewed
- AC members: Alán Aspuru-Guzik, Animesh Garg
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance, AC Full Member
- Flags: acknowledges_ac=checked, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.86
- Missing: materials, properties
- Notes: No validation notes.

## Source Summary
RePLan is a novel framework that leverages Vision Language Models to enable robots to adapt and replan in real time for long-horizon tasks, successfully overcoming failures in initial plans by grounding actions in visual understanding of the environment.

## Abstract
Advancements in large language models (LLMs) have demonstrated their potential in facilitating high-level reasoning, logical reasoning and robotics planning. Recently, LLMs have also been able to generate reward functions for low-level robot actions, effectively bridging the interface between high-level planning and low-level robot control. However, the challenge remains that even with syntactically correct plans, robots can still fail to achieve their intended goals due to imperfect plans or unexpected environmental issues. To overcome this, Vision Language Models (VLMs) have shown remarkable success in tasks such as visual question answering. Leveraging the capabilities of VLMs, we present a novel framework called Robotic Replanning with Perception and Language Models (RePLan) that enables online replanning capabilities for long-horizon tasks. This framework utilizes the physical grounding provided by a VLM's understanding of the world's state to adapt robot actions when the initial plan fails to achieve the desired goal. We developed a Reasoning and Control (RC) benchmark with eight long-horizon tasks to test our approach. We find that RePLan enables a robot to successfully adapt to unforeseen obstacles while accomplishing open-ended, long-horizon goals, where baseline models cannot, and can be readily applied to real robots. Find more information at https://replan-lm.github.io/replan.github.io/

## Scientific Elements
### Hardware / Physical System
- RePLan is a novel framework that leverages Vision Language Models to enable robots to adapt and replan in real time for long-horizon tasks, successfully overcoming failures in initial plans by grounding actions in visual understanding of the environment.
- Recently, LLMs have also been able to generate reward functions for low-level robot actions, effectively bridging the interface between high-level planning and low-level robot control.
- However, the challenge remains that even with syntactically correct plans, robots can still fail to achieve their intended goals due to imperfect plans or unexpected environmental issues.
- Leveraging the capabilities of VLMs, we present a novel framework called Robotic Replanning with Perception and Language Models (RePLan) that enables online replanning capabilities for long-horizon tasks.

### Method
- Developing a Robotic Replanning with Perception and Language Models (REPLAN) framework that utilizes VLMs for understanding the world's state and adapting robot actions when initial plans fail to achieve goals.

### Problem
- Designing embodied agents to execute multi-stage, long-horizon tasks in robotics, which requires manipulation skills, perception, reasoning, and planning over extended periods.

### Hypothesis
- A framework that combines large language models (LLMs) for high-level planning and vision-language models (VLMs) for physical grounding can enable online replanning capabilities for long-horizon tasks.

### Evidence
- The REPLAN framework was tested on a Reasoning and Control (RC) benchmark with eight long-horizon tasks, demonstrating the ability to adapt to unforeseen obstacles and accomplish open-ended goals without human intervention.

### Conclusion
- REPLAN enables multi-stage, long-horizon task execution by integrating high-level planning, low-level reward generation, and online replanning based on sensory feedback, outperforming baseline models in task completion.

## Scientific Objects And Mechanisms
### Entities
- Robotic agent
- High-Level LLM Planner
- VLM Perceiver
- Low-Level LLM Planner
- Motion Controller
- LLM Verifier

### Materials / Systems
- Not specified.

### Properties
- Not specified.

### Measurements
- We developed a Reasoning and Control (RC) benchmark with eight long-horizon tasks to test our approach.
- The REPLAN framework was tested on a Reasoning and Control (RC) benchmark with eight long-horizon tasks, demonstrating the ability to adapt to unforeseen obstacles and accomplish open-ended goals without human intervention.

### Conditions
- RePLan: Robotic Replanning with Perception and Language Models RePLan is a novel framework that leverages Vision Language Models to enable robots to adapt and replan in real time for long-horizon tasks, successfully overcoming failures in initial plans by grounding actions in visual understanding of the environment.

### Mechanisms
- High-level reasoning and planning
- Physical grounding and perception
- Low-level reward function generation
- Robot motion control
- Verification and correction of plans and perceptions

### Outcomes
- Adaptation of robot actions to environmental changes
- Online replanning when initial plans fail
- Execution of long-horizon tasks without human intervention

## Cross-SDL Transfer
### SDL / Domain Tags
- SDL 0 - AI & Automation
- Automation and Robotics
- Artificial Intelligence & Data Science

### Reasoning Motifs
- Perception → Action
- Failure → Adaptation
- Feedback → Correction

### General Principles
- Control Through Feedback
- Adaptation to Change
- Verification for Reliability

## Failure Paths / Caveats
- failure: Using LLMs alone for task planning without physical grounding. Evidence: LLMs fail to account for environmental obstacles and uncertainties, leading to ineffective plans.
- failure: Employing VLMs directly for generating multi-stage task plans. Evidence: VLMs, while accurate in object recognition, fail to generate feasible plans for complex tasks due to lack of high-level reasoning.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_416318135a95.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper presents a novel framework for robotic planning and replanning, with clear hypotheses, methods, and results. However, the extraction of phase 4 failures relies on implicit negative results scattered throughout the paper, which required careful inference.
