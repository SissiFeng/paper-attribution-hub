# Errors are Useful Prompts: Instruction Guided Task Programming with Verifier-Assisted Iterative Prompting

## Metadata
- Paper ID: `acfocus_96fcbbcad556`
- Cross-SDL ID: `acgold_e7a120b62075`
- DOI: 10.48550/arxiv.2303.14100
- URL: https://arxiv.org/abs/2303.14100
- Year: 2023
- Authors: Skreta, Marta; Yoshikawa, Naruki; Arellano-Rubach, Sebastian; Ji, Zhi; Kristensen, Lasse Bjørn; Darvish, Kourosh; Aspuru-Guzik, Alán; Shkurti, Florian; Garg, Animesh
- Venue: arxiv
- Category: Preprint
- Peer reviewed: Non Peer Reviewed
- AC members: Alán Aspuru-Guzik, Kourosh Darvish (Deactivated), Animesh Garg, Florian Shkurti
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance, AC Trainee, AC Full Member, AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.83
- Missing: materials, measurements, conditions
- Notes: No validation notes.

## Source Summary
The paper introduces CLAIRIFY, a method that combines iterative prompting and program verification to guide language models in generating syntactically valid, environment-constrained robot task plans from high-level instructions, demonstrating state-of-the-art results in planning chemistry experiments and real robot execution.

## Abstract
Generating low-level robot task plans from high-level natural language instructions remains a challenging problem. Although large language models have shown promising results in generating plans, the accuracy of the output remains unverified. Furthermore, the lack of domain-specific language data poses a limitation on the applicability of these models. In this paper, we propose CLAIRIFY, a novel approach that combines automatic iterative prompting with program verification to ensure programs written in data-scarce domain-specific language are syntactically valid and incorporate environment constraints. Our approach provides effective guidance to the language model on generating structured-like task plans by incorporating any errors as feedback, while the verifier ensures the syntactic accuracy of the generated plans. We demonstrate the effectiveness of CLAIRIFY in planning chemistry experiments by achieving state-of-the-art results. We also show that the generated plans can be executed on a real robot by integrating them with a task and motion planner.

## Scientific Elements
### Hardware / Physical System
- The paper introduces CLAIRIFY, a method that combines iterative prompting and program verification to guide language models in generating syntactically valid, environment-constrained robot task plans from high-level instructions, demonstrating state-of-the-art results in planning chemistry experiments and real robot execution.
- Generating low-level robot task plans from high-level natural language instructions remains a challenging problem.
- We also show that the generated plans can be executed on a real robot by integrating them with a task and motion planner.
- Proposing CLAIRIFY, a framework that translates natural language into a domain-specific structured task plan using an automated iterative verification technique to ensure syntactic validity in the target DSL.

### Method
- Proposing CLAIRIFY, a framework that translates natural language into a domain-specific structured task plan using an automated iterative verification technique to ensure syntactic validity in the target DSL.

### Problem
- Generating low-level robot task plans from high-level natural language instructions in data-scarce domain-specific languages remains challenging.

### Hypothesis
- A novel approach combining automatic iterative prompting with program verification can ensure programs written in data-scarce domain-specific languages are syntactically valid and incorporate environment constraints.

### Evidence
- CLAIRIFY demonstrated state-of-the-art results in planning chemistry experiments and the generated plans were executable on a real robot, integrating with a task and motion planner.

### Conclusion
- CLAIRIFY effectively translates natural language instructions into structured task plans for domain-specific languages with syntactic correctness and executable by real robots.

## Scientific Objects And Mechanisms
### Entities
- Large Language Model (LLM)
- Program Verifier
- Domain-Specific Language (DSL)
- Environment Constraints
- Task and Motion Planner (TAMP)

### Materials / Systems
- Not specified.

### Properties
- Although large language models have shown promising results in generating plans, the accuracy of the output remains unverified.
- Our approach provides effective guidance to the language model on generating structured-like task plans by incorporating any errors as feedback, while the verifier ensures the syntactic accuracy of the generated plans.

### Measurements
- Not specified.

### Conditions
- Not specified.

### Mechanisms
- Iterative prompting with feedback incorporation
- Program verification for syntactic accuracy
- Incorporation of environmental constraints into task planning
- Translation of DSL plans into robot executable actions

### Outcomes
- Improved syntactic correctness of generated task plans
- Increased applicability of LLMs to data-scarce domains
- Executable task plans on real robots
- State-of-the-art performance in chemistry experiment planning

## Cross-SDL Transfer
### SDL / Domain Tags
- SDL 0 - AI & Automation
- Artificial Intelligence & Data Science

### Reasoning Motifs
- Feedback → Adaptation
- Constraint → Stability
- Translation → Execution

### General Principles
- Control Through Constraints
- Emergent Order

## Failure Paths / Caveats
- failure: Prompting the generator without a DSL description Evidence: The LLM was unable to generate XDL for any of the inputs from the small validation set.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_e7a120b62075.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper presents a structured approach to generating task plans from natural language instructions using a novel framework. However, some details of the iterative process and the specific challenges faced in integrating with real-world robots are not fully elaborated.
