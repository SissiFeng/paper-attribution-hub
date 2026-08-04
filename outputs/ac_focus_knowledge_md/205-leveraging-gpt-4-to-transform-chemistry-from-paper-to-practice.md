# Leveraging GPT-4 to transform chemistry from paper to practice

## Metadata
- Paper ID: `acfocus_1c826a99588f`
- Cross-SDL ID: `acgold_8592360ada93`
- DOI: 10.1039/d4dd00248b
- URL: https://pubs.rsc.org/en/content/articlelanding/2024/dd/d4dd00248b
- Year: 2024
- Authors: Zhang W.; Guy M.A.; Yang J.; Hao L.; Liu J.; Hawkins J.M.; Mustakis J.; Monfette S.; Hein J.E.
- Venue: Digital Discovery
- Category: Article
- Peer reviewed: Peer Reviewed
- AC members: Jason Hein
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=checked, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.64
- Missing: source_summary, hardware, materials, properties, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
Not specified in CSV.

## Abstract
Leveraging GPT-4 to transform chemistry from
paper to practice†
Wenyu Zhang,
a Mason A. Guy,a Jerrica Yang,a Lucy Hao,a Junliang Liu,b
Joel M. Hawkins,c Jason Mustakis,
c Sebastien Monfette
*c
and Jason E. Hein
*abde
Large Language Models (LLMs) have revolutionized numerous industries as well as accelerated scientiﬁc
research. However, their application in planning and conducting experimental science, has been limited.
In this study, we introduce an adaptable prompt-set with GPT-4, converting literature experimental
procedures into actionable experimental steps for a Mettler Toledo EasyMax automated laboratory
reactor. Through prompt engineering, we developed a 2-step sequential prompt: the ﬁrst prompt
converts literature synthesis procedures into step-by-step instructions for reaction planning; the second
prompt generates an XML script to communicate these instructions to the EasyMax reactor, automating
experimental design and execution. We successfully automated the reproduction of three distinct
literature-based synthetic procedures and validated the reactions by monitoring and characterizing the
products. This approach bridges the gap between text-to-procedure transcription and automated
execution, and streamlines literature procedure reproduction.
Introduction
Self-Driving Labs (SDLs) integrate robotic automation with
machine learning (ML) to explore chemical space. SDLs accel-
erate
research
and
discovery
across
various
disciplines,
including organic synthesis,1–3 materials chemistry,4–6 photo-7,8
and
electrochemistry.9–11
Automation
liberates
human
researchers from time-consuming and repetitive tasks, while
closed-loop optimization algorithms and/or computer vision
further reduce the need for human oversight.7,12–14 However, the
broader adoption of SDLs remains challenging because the
required expertise in engineering and programming are beyond
the scope of many chemistry laboratories. For example,
programming an established automation system to execute
a sin

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Developing a two-step sequential prompt approach to transcribe literature procedures into step-by-step instructions and XML scripts, utilizing GPT-4's capabilities.

### Problem
- The challenge of translating literature experimental procedures into actionable steps for automated laboratory reactors.

### Hypothesis
- A two-step sequential prompt using GPT-4 can convert literature synthesis procedures into executable XML scripts for an automated laboratory reactor.

### Evidence
- Successful automation of three distinct literature-based synthetic procedures, validated by monitoring and characterizing the products using online HPLC and NMR spectroscopy.

### Conclusion
- The approach bridges the gap between text-to-procedure transcription and automated execution, streamlining literature procedure reproduction.

## Scientific Objects And Mechanisms
### Entities
- GPT-4
- Mettler Toledo EasyMax automated laboratory reactor
- XML script
- literature synthesis procedures

### Materials / Systems
- Not specified.

### Properties
- Not specified.

### Measurements
- Successful automation of three distinct literature-based synthetic procedures, validated by monitoring and characterizing the products using online HPLC and NMR spectroscopy.
- GPT-4 Mettler Toledo EasyMax automated laboratory reactor XML script literature synthesis procedures Replication of literature-based synthetic procedures Validation of automated execution through product monitoring and characterization

### Conditions
- Not specified.

### Mechanisms
- Prompt engineering to convert literature procedures into actionable steps
- XML script generation for automated reactor communication
- Automated execution of transcriptions

### Outcomes
- Replication of literature-based synthetic procedures
- Validation of automated execution through product monitoring and characterization

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Chemistry

### Reasoning Motifs
- Textual Description → Actionable Steps
- Actionable Steps → Automated Execution
- Automated Execution → Validated Outcomes

### General Principles
- Information Transduction
- Automation of Sequential Tasks
- Feedback-Driven Validation

## Failure Paths / Caveats
- failure: Translation of lengthy protocols exceeding the token limit of GPT models. Evidence: Lengthy protocols need to be broken down into smaller portions due to token limit issues.
- partial: GPT-4's accuracy in molecular weight lookup for chemical compounds. Evidence: GPT-4 showed 100% accuracy in density lookup but failed to output the correct molecular weight for 5,6-dichloropyrazine-2,3-dicarbonitrile in all conversations.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_8592360ada93.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper provides a structured approach to solving the problem of automating literature procedure transcription. However, some details regarding the failure cases and limitations were inferred from the discussion on robustness evaluation and limitations.
