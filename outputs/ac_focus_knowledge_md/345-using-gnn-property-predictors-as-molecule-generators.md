# Using GNN property predictors as molecule generators

## Metadata
- Paper ID: `acfocus_139e1dfbfcdc`
- Cross-SDL ID: `acgold_7eff49bccb7c`
- DOI: 10.1038/s41467-025-59439-1
- URL: https://www.nature.com/articles/s41467-025-59439-1
- Year: 2025
- Authors: F. Therrien; E. H. Sargent; O. Voznyy
- Venue: Nature Communications
- Category: Journal Article
- Peer reviewed: Peer Reviewed
- AC members: Oleksandr Voznyy
- AC programs: Not specified
- AC membership status: AC Full Member
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=checked

## Validation
- Score: 0.9
- Missing: measurements, conditions
- Notes: No validation notes.

## Source Summary
This article presents a method that leverages invertible graph neural networks to directly generate molecular structures with desired electronic properties by optimizing molecular graphs via gradient ascent, achieving target properties and molecular diversity comparable to or better than state-of-the-art generative models, and introduces a new dataset of 1617 molecules with DFT-calculated properties.

## Abstract
Graph neural networks (GNNs) have emerged as powerful tools to accurately predict materials and molecular properties in computational and automated discovery pipelines. In this article, we exploit the invertible nature of these neural networks to directly generate molecular structures with desired electronic properties. Starting from a random graph or an existing molecule, we perform a gradient ascent while holding the GNN weights fixed in order to optimize its input, the molecular graph, towards the target property. Valence rules are enforced strictly through a judicious graph construction. The method relies entirely on the property predictor; no additional training is required on molecular structures. We demonstrate the application of this method by generating molecules with specific energy gaps verified with density functional theory (DFT) and with specific octanol-water partition coefficients (logP). Our approach hits target properties with rates comparable to or better than state-of-the-art generative models while consistently generating more diverse molecules. Moreover, while validating our framework we created a dataset of 1617 new molecules and their corresponding DFT-calculated properties that could serve as an out-of-distribution test set for QM9-trained models.

## Scientific Elements
### Hardware / Physical System
- Graph neural networks (GNNs) have emerged as powerful tools to accurately predict materials and molecular properties in computational and automated discovery pipelines.

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
- Using GNN property predictors as molecule generators This article presents a method that leverages invertible graph neural networks to directly generate molecular structures with desired electronic properties by optimizing molecular graphs via gradient ascent, achieving target properties and molecular diversity comparable to or better than state-of-the-art generative models, and introduces a new dataset of 1617 molecules with DFT-calculated properties.
- Graph neural networks (GNNs) have emerged as powerful tools to accurately predict materials and molecular properties in computational and automated discovery pipelines.
- Starting from a random graph or an existing molecule, we perform a gradient ascent while holding the GNN weights fixed in order to optimize its input, the molecular graph, towards the target property.

### Properties
- Using GNN property predictors as molecule generators This article presents a method that leverages invertible graph neural networks to directly generate molecular structures with desired electronic properties by optimizing molecular graphs via gradient ascent, achieving target properties and molecular diversity comparable to or better than state-of-the-art generative models, and introduces a new dataset of 1617 molecules with DFT-calculated properties.
- Graph neural networks (GNNs) have emerged as powerful tools to accurately predict materials and molecular properties in computational and automated discovery pipelines.
- In this article, we exploit the invertible nature of these neural networks to directly generate molecular structures with desired electronic properties.
- Starting from a random graph or an existing molecule, we perform a gradient ascent while holding the GNN weights fixed in order to optimize its input, the molecular graph, towards the target property.
- The method relies entirely on the property predictor; no additional training is required on molecular structures.

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
- Not specified.

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
