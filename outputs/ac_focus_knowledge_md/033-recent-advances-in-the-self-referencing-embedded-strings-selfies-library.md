# Recent advances in the self-referencing embedded strings (SELFIES) library

## Metadata
- Paper ID: `acfocus_1c4b25a8b316`
- Cross-SDL ID: `acgold_cfe8c932b223`
- DOI: 10.1039/d3dd00044c
- URL: https://xlink.rsc.org/?DOI=D3DD00044C
- Year: 2023
- Authors: Lo, Alston; Pollice, Robert; Nigam, AkshatKumar; White, Andrew D.; Krenn, Mario; Aspuru-Guzik, Alán
- Venue: Digital Discovery
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Alán Aspuru-Guzik
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.77
- Missing: hardware, properties, measurements
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
The manuscript presents the current state of the SELFIES library (version 2.1.1), highlighting significant advances in its algorithms, design, and API that enhance its robustness, efficiency, and molecular representation capabilities for cheminformatics and machine learning applications.

## Abstract
We describe the current state of the SELFIES library (version 2.1.1), and, in particular, the advances and improvements we have made in its underlying algorithms, design, and API.           ,              String-based molecular representations play a crucial role in cheminformatics applications, and with the growing success of deep learning in chemistry, have been readily adopted into machine learning pipelines. However, traditional string-based representations such as SMILES are often prone to syntactic and semantic errors when produced by generative models. To address these problems, a novel representation, SELF-referencing embedded strings (SELFIES), was proposed that is inherently 100% robust, alongside an accompanying open-source implementation called selfies. Since then, we have generalized SELFIES to support a wider range of molecules and semantic constraints, and streamlined its underlying grammar. We have implemented this updated representation in subsequent versions of selfies, where we have also made major advances with respect to design, efficiency, and supported features. Hence, we present the current status of selfies (version 2.1.1) in this manuscript. Our library, selfies, is available at GitHub (https://github.com/aspuru-guzik-group/selfies).

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- The authors developed and implemented the SELFIES representation in an open-source library called selfies, which supports a wide range of molecules and semantic constraints, and compared its performance and capabilities to SMILES.

### Problem
- Traditional string-based molecular representations like SMILES have issues with syntactic and semantic errors when used in machine learning models, especially generative models.

### Hypothesis
- SELF-referencing embedded strings (SELFIES) can be used as a robust molecular string representation that is inherently 100% valid against both syntactic and semantic errors.

### Evidence
- The library 'selfies' can efficiently translate between SELFIES strings and SMILES strings, supports aromatic molecules, partial charges, radicals, explicit hydrogens, non-standard isotopes, and stereochemical definitions, and allows for custom semantic constraints.

### Conclusion
- SELFIES is a robust molecular string representation that can be used in place of SMILES to avoid syntactic and semantic errors, and the 'selfies' library provides an efficient tool for this representation.

## Scientific Objects And Mechanisms
### Entities
- SELFIES string
- SMILES string
- Molecular graph
- Semantic constraints

### Materials / Systems
- Since then, we have generalized SELFIES to support a wider range of molecules and semantic constraints, and streamlined its underlying grammar.
- The authors developed and implemented the SELFIES representation in an open-source library called selfies, which supports a wide range of molecules and semantic constraints, and compared its performance and capabilities to SMILES.
- The library 'selfies' can efficiently translate between SELFIES strings and SMILES strings, supports aromatic molecules, partial charges, radicals, explicit hydrogens, non-standard isotopes, and stereochemical definitions, and allows for custom semantic constraints.

### Properties
- Not specified.

### Measurements
- Not specified.

### Conditions
- Recent advances in the self-referencing embedded strings (SELFIES) library The manuscript presents the current state of the SELFIES library (version 2.1.1), highlighting significant advances in its algorithms, design, and API that enhance its robustness, efficiency, and molecular representation capabilities for cheminformatics and machine learning applications.
- We describe the current state of the SELFIES library (version 2.1.1), and, in particular, the advances and improvements we have made in its underlying algorithms, design, and API.
- Hence, we present the current status of selfies (version 2.1.1) in this manuscript.

### Mechanisms
- String-based molecular representation
- Syntax and semantic validation
- Graph derivation from string representation
- Customizable constraint application

### Outcomes
- Error-free machine learning model input
- Wider range of molecule representation
- Flexible handling of molecular features
- Adjustable rule sets for different chemical contexts

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Chemistry

### Reasoning Motifs
- Robustness → Error reduction
- Flexibility → Feature representation
- Customization → Context适配

### General Principles
- Error Minimization
- Feature Inclusion
- Context-Sensitive Design

## Failure Paths / Caveats
- No explicit failure path available in CSV/cross-SDL extraction.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_cfe8c932b223.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper is well-structured and clearly presents the development and capabilities of the 'selfies' library for SELFIES representation. However, some specific details on the底层 mechanisms of graph derivation and semantic validation could be more explicit.
