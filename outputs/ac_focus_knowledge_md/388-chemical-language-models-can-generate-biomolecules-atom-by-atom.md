# Chemical language models can generate biomolecules atom-by-atom

## Metadata
- Paper ID: `acfocus_3ee3a2a14fa2`
- Cross-SDL ID: `acgold_9920048a18d3`
- DOI: 10.1039/d5dd00107b
- URL: https://pubs.rsc.org/en/content/articlelanding/2025/dd/d5dd00107b
- Year: 2025
- Authors: K. Zhu; D. Flam-Shepherd; A. Aspuru-Guzik
- Venue: Digital Discovery
- Category: Journal Article
- Peer reviewed: Peer Reviewed
- AC members: Alán Aspuru-Guzik
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=checked, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.73
- Missing: hardware, properties, measurements, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
Chemical language models can learn and generate atom-level representations of large biomolecules, including proteins and protein-drug conjugates, enabling hierarchical and novel biomolecular design.

## Abstract
Chemical language models are powerful generative models, capable of learning complex molecular distributions such as the largest molecules in Pubchem. In this work, we further show that chemical language models can learn atom-level representations of substantially larger molecules - scaling even to biomolecules like proteins. We show that chemical language models can generate entire biomolecules atom by atom - effectively learning the multiple hierarchical layers of molecular information from primary sequence to tertiary structure. Even further, we demonstrate that chemical language models can explore chemical space and protein space simultaneously by generating novel examples of protein-drug conjugates. The results demonstrate the potential for atom level biomolecular design with chemical language models.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Training chemical language models on various biomolecules including proteins from the Protein DataBank and creating synthetic biomolecular datasets by attaching small molecules to single-domain antibodies.

### Problem
- The ability of chemical language models to generate large biomolecules atom by atom, including proteins and protein-drug conjugates.

### Hypothesis
- Chemical language models can learn atom-level representations of substantially larger molecules, scaling to biomolecules like proteins.

### Evidence
- The model generated proteins with valid primary sequences, unique amino acid sequences, and meaningful secondary and tertiary structures as confirmed by AlphaFold structure predictions.

### Conclusion
- Chemical language models can effectively learn the hierarchical layers of molecular information from primary sequence to tertiary structure and explore chemical space and protein space simultaneously.

## Scientific Objects And Mechanisms
### Entities
- Proteins
- Protein-drug conjugates
- Small molecules
- Amino acid sequences

### Materials / Systems
- Proteins
- Protein-drug conjugates
- Small molecules
- Chemical language models are powerful generative models, capable of learning complex molecular distributions such as the largest molecules in Pubchem.
- In this work, we further show that chemical language models can learn atom-level representations of substantially larger molecules - scaling even to biomolecules like proteins.
- Training chemical language models on various biomolecules including proteins from the Protein DataBank and creating synthetic biomolecular datasets by attaching small molecules to single-domain antibodies.

### Properties
- Not specified.

### Measurements
- Not specified.

### Conditions
- Not specified.

### Mechanisms
- Learning atom-level representations of biomolecules
- Generating molecular graphs representing proteins and protein-drug conjugates
- Exploring chemical and protein space by generating novel molecular structures

### Outcomes
- Generation of proteins with valid primary sequences and structures
- Creation of novel protein-drug conjugates with valid and novel protein sequences and structures attached to drug-like molecules

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Biochemistry

### Reasoning Motifs
- Learning → Generation
- Data augmentation → Enhanced exploration
- Sequence pattern recognition → Novel sequence creation

### General Principles
- Information Representation
- Generative Modeling
- Pattern Recognition

## Failure Paths / Caveats
- success: Training chemical language models on larger biomolecules and protein-drug conjugates. Evidence: The model successfully learned to generate proteins and protein-drug conjugates with valid structures and sequences.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_9920048a18d3.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper provides a clear structure of the problem, hypothesis, method, and results, but some details on the specific training processes and model architectures were inferred.
