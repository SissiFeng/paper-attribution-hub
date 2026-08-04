# Interpretable discovery of semiconductors with machine learning

## Metadata
- Paper ID: `acfocus_6db333904543`
- Cross-SDL ID: `acgold_e997d42c4b91`
- DOI: 10.1038/s41524-023-01066-9
- URL: https://www.nature.com/articles/s41524-023-01066-9
- Year: 2023
- Authors: Choubisa, Hitarth; Todorović, Petar; Pina, Joao M.; Parmar, Darshan H.; Li, Ziliang; Voznyy, Oleksandr; Tamblyn, Isaac; Sargent, Edward H.
- Venue: npj Computational Materials
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Oleksandr Voznyy
- AC programs: Not specified
- AC membership status: AC Full Member
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.8
- Missing: hardware, measurements, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
The authors present a framework that combines evolutionary algorithms, machine learning surrogate models, and statistical testing to efficiently search materials space and generate interpretable, statistically robust design rules for materials discovery, demonstrated in applications such as direct bandgap materials and UV/IR emitters.

## Abstract
Abstract                            Machine learning models of material properties accelerate materials discovery, reproducing density functional theory calculated results at a fraction of the cost               1–6               . To bridge the gap between theory and experiments, machine learning predictions need to be distilled in the form of interpretable chemical rules that can be used by experimentalists. Here we develop a framework to address this gap by combining evolutionary algorithm-powered search with machine-learning surrogate models. We then couple the search results with supervised learning and statistical testing. This strategy enables the efficient search of a materials space while providing interpretable design rules. We demonstrate its effectiveness by developing rules for the design of direct bandgap materials, stable UV emitters, and IR perovskite emitters. Finally, we conclusively show how DARWIN-generated rules are statistically more robust and applicable to a wide range of applications including the design of UV halide perovskites.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Development of the DARWIN framework, integrating property prediction models, search algorithms, and interpretability analysis to generate and identify statistically significant chemical rules.

### Problem
- Accelerating materials discovery by bridging the gap between theoretical predictions and experimental validations through interpretable machine learning models.

### Hypothesis
- A framework combining evolutionary algorithm-powered search with machine-learning surrogate models can efficiently search material space and provide interpretable design rules.

### Evidence
- The effectiveness of DARWIN demonstrated by developing rules for designing direct bandgap materials, stable UV emitters, and IR perovskite emitters, with statistically robust rules applicable to a wide range of applications.

### Conclusion
- DARWIN-generated rules are statistically robust and applicable to various applications, including the design of UV halide perovskites, thereby bridging the gap between theory and experiment.

## Scientific Objects And Mechanisms
### Entities
- Graph Neural Networks (GNNs)
- Evolutionary Algorithm (EA)
- Machine Learning (ML) models
- Chemical features and operations
- Statistical techniques

### Materials / Systems
- Interpretable discovery of semiconductors with machine learning The authors present a framework that combines evolutionary algorithms, machine learning surrogate models, and statistical testing to efficiently search materials space and generate interpretable, statistically robust design rules for materials discovery, demonstrated in applications such as direct bandgap materials and UV/IR emitters.
- Abstract                            Machine learning models of material properties accelerate materials discovery, reproducing density functional theory calculated results at a fraction of the cost               1–6               .
- This strategy enables the efficient search of a materials space while providing interpretable design rules.

### Properties
- Abstract                            Machine learning models of material properties accelerate materials discovery, reproducing density functional theory calculated results at a fraction of the cost               1–6               .
- Development of the DARWIN framework, integrating property prediction models, search algorithms, and interpretability analysis to generate and identify statistically significant chemical rules.
- Graph Neural Networks (GNNs) Evolutionary Algorithm (EA) Machine Learning (ML) models Chemical features and operations Statistical techniques Prediction of materials with optimal properties Generation of multiple candidates meeting desired target properties Identification of relevant statistically significant chemical rules

### Measurements
- Not specified.

### Conditions
- Not specified.

### Mechanisms
- Property prediction using unrelaxed structures
- Search algorithm integration for materials space search
- Extraction of interpretable chemical design rules through supervised learning and statistical testing

### Outcomes
- Prediction of materials with optimal properties
- Generation of multiple candidates meeting desired target properties
- Identification of relevant statistically significant chemical rules

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Materials Science
- Electronics
- Optical Materials
- Clean energy

### Reasoning Motifs
- Model Prediction → Search Algorithm Optimization
- Feature Relevance → Material Property Correlation
- Statistical Significance → Rule Validation

### General Principles
- Prediction Informs Search
- Feature Relevance Dictates Outcome
- Statistical Validation Ensures Reliability

## Failure Paths / Caveats
- failure: Removing the search component of DARWIN and relying solely on Materials Project data for developing interpretable chemical rules. Evidence: Lack of promising candidates for statistical significance calculation and failure to recover known rules for material design.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_e997d42c4b91.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper presents a structured approach to materials discovery using machine learning, with clear hypotheses, methods, and conclusions. The reasoning structure is well-defined, but some details of the interpretability analysis and feature selection are complex and may require further clarification.
