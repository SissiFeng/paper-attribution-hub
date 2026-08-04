# Using GNN property predictors as molecule generators

## Metadata
- Paper ID: `acfocus_9a6d8a639010`
- Cross-SDL ID: `acgold_7eff49bccb7c`
- DOI: 10.48550/arxiv.2406.03278
- URL: https://www.nature.com/articles/s41467-025-59439-1
- Year: 2024
- Authors: Therrien F, Sargent EH, Voznyy O
- Venue: Nature Communications
- Category: Preprint
- Peer reviewed: Non Peer Reviewed
- AC members: Oleksandr Voznyy
- AC programs: Not specified
- AC membership status: AC Full Member
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.72
- Missing: source_summary, hardware, measurements, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
Not specified in CSV.

## Abstract
Using GNN property predictors as molecule generators
F´elix Therrien,1, 2 Edward H. Sargent,2 and Oleksandr Voznyy1
1University of Toronto, Department of Physical & Environmental Science
2University of Toronto, Department of Electrical and Computer Engineering
Graph neural networks (GNNs) have emerged as powerful tools to accurately predict materials and
molecular properties in computational discovery pipelines. In this article, we exploit the invertible
nature of these neural networks to directly generate molecular structures with desired electronic
properties. Starting from a random graph or an existing molecule, we perform a gradient ascent while
holding the GNN weights fixed in order to optimize its input, the molecular graph, towards the target
property. Valence rules are enforced strictly through a judicious graph construction. The method
relies entirely on the property predictor; no additional training is required on molecular structures.
We demonstrate the application of this method by generating molecules with specific DFT-verified
energy gaps and octanol-water partition coefficients (logP). Our approach hits target properties with
rates comparable to or better than state-of-the-art generative models while consistently generating
more diverse molecules.
One of the ultimate goals of computational materials
science is to be able to rapidly uncover material struc-
tures and compositions with specific properties [1]. This
is particularly true in the fields of pharmacy and ma-
terials for energy and sustainability where time is of
the essence. In the past decades, computational mate-
rials discovery has been achieved by going through large
databases of existing materials and computing proper-
ties from first principles using methods such as density
functional theory (DFT) and molecular dynamics [2, 3].
These methods have proven to be successful in many
cases [4–7], but suffer from two main limitations: (1)
they are computationally expensive and (2) they cover a


## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Exploit the invertible nature of GNNs to perform gradient ascent on the molecular graph input towards a target property while strictly enforcing valence rules through judicious graph construction.

### Problem
- Rapid uncovering of material structures and compositions with specific properties in fields such as pharmacy and materials for energy and sustainability.

### Hypothesis
- Graph neural networks (GNNs) can be inverted to generate molecular structures with desired electronic properties directly from property predictors without additional training.

### Evidence
- Generated molecules with specific DFT-verified energy gaps and octanol-water partition coefficients (logP), demonstrating comparable or better performance than state-of-the-art generative models in hitting target properties and generating more diverse molecules.

### Conclusion
- A property predicting GNN can be turned into a diverse conditional generator without additional training by carefully constraining the representation of molecules.

## Scientific Objects And Mechanisms
### Entities
- Graph neural networks (GNNs)
- Molecular graphs
- Property predictors
- Density functional theory (DFT)
- Octanol-water partition coefficient (logP)

### Materials / Systems
- Using GNN property predictors as molecule generators Exploit the invertible nature of GNNs to perform gradient ascent on the molecular graph input towards a target property while strictly enforcing valence rules through judicious graph construction.
- Generated molecules with specific DFT-verified energy gaps and octanol-water partition coefficients (logP), demonstrating comparable or better performance than state-of-the-art generative models in hitting target properties and generating more diverse molecules.
- Graph neural networks (GNNs) Molecular graphs Property predictors Density functional theory (DFT) Octanol-water partition coefficient (logP) Generation of molecules with desired electronic properties Achievement of target properties comparable to or better than state-of-the-art models Generation of more diverse molecules

### Properties
- Using GNN property predictors as molecule generators Exploit the invertible nature of GNNs to perform gradient ascent on the molecular graph input towards a target property while strictly enforcing valence rules through judicious graph construction.
- Generated molecules with specific DFT-verified energy gaps and octanol-water partition coefficients (logP), demonstrating comparable or better performance than state-of-the-art generative models in hitting target properties and generating more diverse molecules.
- Graph neural networks (GNNs) Molecular graphs Property predictors Density functional theory (DFT) Octanol-water partition coefficient (logP) Generation of molecules with desired electronic properties Achievement of target properties comparable to or better than state-of-the-art models Generation of more diverse molecules

### Measurements
- Not specified.

### Conditions
- Not specified.

### Mechanisms
- Gradient ascent on molecular graph input
- Enforcement of valence rules in graph construction
- Optimization of molecular graph towards target property
- Validation of generated molecules through DFT calculations

### Outcomes
- Generation of molecules with desired electronic properties
- Achievement of target properties comparable to or better than state-of-the-art models
- Generation of more diverse molecules

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Chemistry
- Materials Science

### Reasoning Motifs
- Optimization → Property Achievement
- Diversity → Solution Space Coverage
- Rule Enforcement → Validity Assurance

### General Principles
- Inverse Design Paradigm
- Generalizability Through Constraints
- Diversity for Multi-Criteria Optimization

## Failure Paths / Caveats
- success: Generating molecules with specific energy gaps and logP values using the proposed method. Evidence: Generated molecules achieved target properties with rates comparable to or better than state-of-the-art generative models and consistently generated more diverse molecules.
- success: Comparison of the proposed method with JANUS, a state-of-the-art genetic algorithm. Evidence: The proposed method nearly matched or outperformed JANUS in all metrics, demonstrating its effectiveness.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_7eff49bccb7c.json`
- Cross-SDL extraction quality: 0.9
- Notes: The paper is highly structured with explicit hypotheses, methods, and results, making the extraction process straightforward. The reasoning is clear and well-documented, allowing for a reliable extraction of the scientific reasoning structure.
