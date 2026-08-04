# Large language models for chemistry robotics

## Metadata
- Paper ID: `acfocus_b4fb4aabd446`
- Cross-SDL ID: `not matched`
- DOI: 10.1007/s10514-023-10136-2
- URL: https://link.springer.com/article/10.1007/s10514-023-10136-2
- Year: 2023
- Authors: Naruki Yoshikawa, Marta Skreta, Kourosh Darvish, Sebastian Arellano-Rubach, Zhi Ji, Lasse Bjørn Kristensen, Andrew Zou Li, Yuchi Zhao, Haoping Xu, Artur Kuramshin, Alán Aspuru-Guzik, Florian Shkurti, Animesh Garg
- Venue: Springer Nature
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Alán Aspuru-Guzik, Kourosh Darvish (Deactivated), Animesh Garg, Florian Shkurti
- AC programs: AC PDF_Florian Shkurti_2022-23, Core Development Grants_Florian Shkurti_2023-24
- AC membership status: AC Full Member, AC Governance, AC Trainee, AC Full Member, AC Full Member, AC Governance
- Flags: acknowledges_ac=checked, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.54
- Missing: evidence, properties, measurements, conditions, mechanisms, outcomes, cross_sdl_match
- Notes: No cross-SDL extraction matched this paper; fields are derived from CSV only.

## Source Summary
This paper introduces CLAIRify, a system that uses large language models and task/motion planning to translate natural language chemistry experiment instructions into robot-executable plans, enabling autonomous, safe, and effective execution of complex lab tasks by robots.

## Abstract
This paper proposes an approach to automate chemistry experiments using robots by translating natural language instructions
into robot-executable plans, using large language models together with task and motion planning. Adding natural language
interfaces to autonomous chemistry experiment systems lowers the barrier to using complicated robotics systems and increases
utility for non-expert users, but translating natural language experiment descriptions from users into low-level robotics languages
is nontrivial. Furthermore, while recent advances have used large language models to generate task plans, reliably
executing those plans in the real world by an embodied agent remains challenging. To enable autonomous chemistry experiments
and alleviate the workload of chemists, robots must interpret natural language commands, perceive the workspace,
autonomously plan multi-step actions and motions, consider safety precautions, and interact with various laboratory equipment.
Our approach, CLAIRify, combines automatic iterative prompting with program verification to ensure syntactically
valid programs in a data-scarce domain-specific language that incorporates environmental constraints. The generated plan is
executed through solving a constrained task and motion planning problem using PDDLStream solvers to prevent spillages of
liquids as well as collisions in chemistry labs.We demonstrate the effectiveness of our approach in planning chemistry experiments,
with plans successfully executed on a real robot using a repertoire of robot skills and lab tools. Specifically,we showcase
the utility of our framework in pouring skills for various materials and two fundamental chemical experiments for materials
synthesis: solubility and recrystallization. Further details about CLAIRify can be found at https://ac-rad.github.io/clairify/.

## Scientific Elements
### Hardware / Physical System
- This paper introduces CLAIRify, a system that uses large language models and task/motion planning to translate natural language chemistry experiment instructions into robot-executable plans, enabling autonomous, safe, and effective execution of complex lab tasks by robots.
- This paper proposes an approach to automate chemistry experiments using robots by translating natural language instructions
into robot-executable plans, using large language models together with task and motion planning.
- Adding natural language
interfaces to autonomous chemistry experiment systems lowers the barrier to using complicated robotics systems and increases
utility for non-expert users, but translating natural language experiment descriptions from users into low-level robotics languages
is nontrivial.
- To enable autonomous chemistry experiments
and alleviate the workload of chemists, robots must interpret natural language commands, perceive the workspace,
autonomously plan multi-step actions and motions, consider safety precautions, and interact with various laboratory equipment.

### Method
- This paper introduces CLAIRify, a system that uses large language models and task/motion planning to translate natural language chemistry experiment instructions into robot-executable plans, enabling autonomous, safe, and effective execution of complex lab tasks by robots.

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
- Automation and Robotics
- Chemistry

### Materials / Systems
- Specifically,we showcase
the utility of our framework in pouring skills for various materials and two fundamental chemical experiments for materials
synthesis: solubility and recrystallization.

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
- SDL 0 - AI & Automation
- Artificial Intelligence & Data Science
- Automation and Robotics
- Chemistry

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
