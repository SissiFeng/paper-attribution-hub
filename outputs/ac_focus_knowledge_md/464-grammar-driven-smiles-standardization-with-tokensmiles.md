# Grammar-driven SMILES standardization with TokenSMILES

## Metadata
- Paper ID: `acfocus_ad7ecafb7ab7`
- Cross-SDL ID: `acgold_e6ac05d676c5`
- DOI: 10.1039/d5sc05004a
- URL: https://www.scopus.com/inward/record.uri?eid=2-s2.0-105023168024&doi=10.1039%2Fd5sc05004a&partnerID=40&md5=946dedd1ae908903c764fcd708da4631
- Year: 2026
- Authors: L. A. González-Ortiz; L. Noriega; F. Ortíz-Chi; G. Vidales-Ayala; E. Soberanis-Cáceres; A. Meneses; A. Aspuru-Guzik; G. Merino
- Venue: Chemical Science
- Category: Journal Article
- Peer reviewed: Peer Reviewed
- AC members: Alán Aspuru-Guzik
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.8
- Missing: hardware, measurements, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
TokenSMILES is a grammatical framework that standardizes SMILES notation into structured, machine-interpretable sentences to reduce redundancy and ensure syntactic and semantic consistency, enabling more systematic chemical space exploration and supporting applications in drug discovery, materials design, and molecular machine learning.

## Abstract
The redundancy of SMILES notation, where multiple strings can describe the same molecule, remains a challenge in computational chemistry and cheminformatics. To mitigate this issue, we introduce TokenSMILES, a grammatical framework that standardizes SMILES into structured sentences composed of context-free words. By applying five syntactic constraints (including branch limitations, balanced parentheses, and aromaticity exclusion), TokenSMILES minimizes redundant SMILES enumerations for alkanes while maintaining valence and octet compliance through semantic parsing rules. TokenSMILES does not replace SMILES but rather formalizes its syntax into a standardized, machine-interpretable form. This grammatical structure enables controlled generation and manipulation of valid SMILES strings, ensuring syntactic and semantic consistency while substantially reducing redundancy. Implemented into SmilX, an open-source tool, TokenSMILES generates valid SMILES with accuracy comparable to existing computational implementations for molecules with low hydrogen deficiency (HDI ≤ 4). Its applicability extends beyond alkanes through stoichiometric modifications such as bond insertion, cyclization, and heteroatom substitution. Nevertheless, challenges remain for highly unsaturated systems, where canonicalization artifacts highlight the need for dynamic feasibility checks. By integrating linguistic principles with cheminformatics, TokenSMILES establishes a scalable framework for systematic chemical space exploration, supporting applications in drug discovery, materials design, and machine learning-driven molecular innovation. This journal is © The Royal Society of Chemistry, 2026

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Applying five syntactic constraints (including branch limitations, balanced parentheses, and aromaticity exclusion) to formalize the SMILES language, along with the development of SmilX, an open-source implementation.

### Problem
- The redundancy of SMILES notation where multiple strings can describe the same molecule.

### Hypothesis
- Introducing TokenSMILES, a grammatical framework that standardizes SMILES into structured sentences composed of context-free words, can minimize redundant SMILES enumerations while maintaining valence and octet compliance.

### Evidence
- TokenSMILES substantially reduces the number of valid SMILES variants for alkanes, and SmilX generates valid SMILES with accuracy comparable to existing computational implementations for molecules with low hydrogen deficiency (HDI # 4).

### Conclusion
- TokenSMILES establishes a scalable framework for systematic chemical space exploration, supporting applications in drug discovery, materials design, and machine learning-driven molecular innovation.

## Scientific Objects And Mechanisms
### Entities
- SMILES strings
- TokenSMILES
- syntactic constraints
- semantic parsing rules
- chemical context

### Materials / Systems
- Grammar-driven SMILES standardization with TokenSMILES TokenSMILES is a grammatical framework that standardizes SMILES notation into structured, machine-interpretable sentences to reduce redundancy and ensure syntactic and semantic consistency, enabling more systematic chemical space exploration and supporting applications in drug discovery, materials design, and molecular machine learning.
- The redundancy of SMILES notation, where multiple strings can describe the same molecule, remains a challenge in computational chemistry and cheminformatics.
- Implemented into SmilX, an open-source tool, TokenSMILES generates valid SMILES with accuracy comparable to existing computational implementations for molecules with low hydrogen deficiency (HDI ≤ 4).

### Properties
- Implemented into SmilX, an open-source tool, TokenSMILES generates valid SMILES with accuracy comparable to existing computational implementations for molecules with low hydrogen deficiency (HDI ≤ 4).
- TokenSMILES substantially reduces the number of valid SMILES variants for alkanes, and SmilX generates valid SMILES with accuracy comparable to existing computational implementations for molecules with low hydrogen deficiency (HDI # 4).

### Measurements
- Not specified.

### Conditions
- Not specified.

### Mechanisms
- standardization of SMILES into structured sentences
- minimization of redundant SMILES enumerations
- maintenance of valence and octet compliance
- systematic computational analysis and exhaustive isomer enumeration

### Outcomes
- controlled generation and manipulation of valid SMILES strings
- ensuring syntactic and semantic consistency
- substantial reduction of redundancy

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Chemistry

### Reasoning Motifs
- Constraint → Consistency
- Reduction → Efficiency
- Compliance → Accuracy

### General Principles
- Control Through Constraints
- Simplicity Through Reduction
- Precision Through Compliance

## Failure Paths / Caveats
- partial: Generating isomers for systems with high hydrogen deficiency (HDI) using SmilX. Evidence: SmilX occasionally yielded one missing structure (false negative) or 1–7 additional isomers (false positives) in systems as C8H2, C9H2, C10H2, C9H4, C10H4, C10H6, C9H8, and C10H10.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_e6ac05d676c5.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper presents a clear hypothesis, method, and results, but some details of the underlying mechanisms and motifs were inferred from the context rather than being explicitly stated.
