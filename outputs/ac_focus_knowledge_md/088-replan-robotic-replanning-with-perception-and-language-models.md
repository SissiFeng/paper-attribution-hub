# RePLan: Robotic Replanning with Perception and Language Models

## Metadata
- Paper ID: `acfocus_011ccea52093`
- Cross-SDL ID: `acgold_416318135a95`
- DOI: 10.48550/arxiv.2401.04157
- URL: https://arxiv.org/abs/2401.04157
- Year: 2024
- Authors: Skreta M, Zhou Z, Yuan JL, Darvish K, Aspuru-Guzik A, Garg A
- Venue: arxiv
- Category: Preprint
- Peer reviewed: Non Peer Reviewed
- AC members: Alán Aspuru-Guzik, Kourosh Darvish
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance, AC Staff
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.74
- Missing: source_summary, materials, properties, conditions
- Notes: No validation notes.

## Source Summary
Not specified in CSV.

## Abstract
REPLAN: Robotic Replanning with Perception and
Language Models
Marta Skreta∗, Zihan Zhou∗, Jia Lin Yuan∗, Kourosh Darvish, Alán Aspuru-Guzik, and Animesh Garg
University of Toronto, Vector Institute for Artificial Intelligence, Georgia Institute of Technology, NVIDIA
{martaskreta, footoredo, jly, kdarvish}@cs.toronto.edu, alan@aspuru.com, animesh.garg@gatech.edu
∗These authors contributed equally to this work.
Place apple
in the bowl
USER
Place apple
in the bowl
USER
LOW-LEVEL PLAN
HIGH-LEVEL PLAN
HIGH-LEVEL
PLAN
minimize_l2_distance_reward(
"palm", "apple")
minimize_l2_distance_reward(
"apple", "lemon",
primary_reward=True)
MPC
Identify the apple's location
Identify the
apple's location
Grasp the apple
Grasp the apple
Move the apple
over the bowl
Release apple
into the bowl
Release apple into the bowl
Did robot
do the task?
NO
REPLAN:
REPLAN: try a new idea
X
FEEDBACK
move lemon
NO
YES
YES
Is the goal
accomplished?
RePLan
GPT-4V
infeasible plan
Perception
✓
Figure 1: Overview of REPLAN using an example user goal: “place apple in the bowl". REPLAN generates a high-level plan of a possible
solution, followed by low-level reward functions. If it is unable to accomplish a subtask, perception is used to diagnose any issues that may be
present in the scene. For example, in this instance there is a lemon already in the bowl, which the robot must first remove. REPLAN generates
a plan to remove the obstacle and continue with the task. Once completing all the subtasks, if the original goal still is not accomplished,
REPLAN can reason at a higher level to try a new solution. Meanwhile, prompting vanilla GPT-4V with an image of the scene and the user
goal returns an infeasible plan because it does not take into account object states.
Abstract—Advancements in large language models (LLMs) have
demonstrated their potential in facilitating high-level reasoning,
logical reasoning and robotics planning. Recently, LLMs have also
been able to generate reward functions for low-level ro

## Scientific Elements
### Hardware / Physical System
- Developing a Robotic Replanning with Perception and Language Models (REPLAN) framework that utilizes VLMs for understanding the world's state and adapting robot actions when initial plans fail to achieve goals.

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
- The REPLAN framework was tested on a Reasoning and Control (RC) benchmark with eight long-horizon tasks, demonstrating the ability to adapt to unforeseen obstacles and accomplish open-ended goals without human intervention.

### Conditions
- Not specified.

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
