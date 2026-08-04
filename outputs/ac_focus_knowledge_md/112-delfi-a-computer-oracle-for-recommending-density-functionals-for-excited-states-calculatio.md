# DELFI: a computer oracle for recommending density functionals for excited states calculations

## Metadata
- Paper ID: `acfocus_22a6c87e4468`
- Cross-SDL ID: `acgold_bdc06b3a427a`
- DOI: 10.1039/d3sc06440a
- URL: https://xlink.rsc.org/?DOI=D3SC06440A
- Year: 2024
- Authors: Avagliano D, Skreta M, Arellano-Rubach S, Aspuru-Guzik A
- Venue: Chemical Science
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Alán Aspuru-Guzik
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=checked, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.9
- Missing: hardware
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
The authors developed DELFI, a neural network-based tool that uses a novel scoring system and a large open database to recommend and rank functionals for TD-DFT excited state calculations of organic molecules, simplifying and accelerating the selection process for accurate photophysical property predictions.

## Abstract
Density functional theory (DFT) is the workhorse of computational quantum chemistry. One of its main limitations is that choosing the right functional is a non-trivial task left for human experts. The choice is particularly hard for excited state calculations when using its time-dependent formulation (TD-DFT). This is due to the approximations of the method, but also because the photophysical properties of a molecule are defined by a manifold of states that all need to be properly described. This includes not only the relative energy of the states, but also capturing the correct character, order, and intensity of the transitions. In this work, we developed a neural network to recommend functionals to be used on molecules for TD-DFT calculations, by simultaneously considering all these properties for a manifold of states. This was possible by developing a scoring system to define the accuracy of an excited state's calculation against a higher-accuracy reference. The scoring system is generalizable to any level of theory; we here applied it to evaluate the performance of common functionals of different rungs against a higher accuracy method on a large set of organic molecules. The results are collected in a database that we released and made open, providing four million data points to the community for future applications. The scoring system assigns a value between zero and one hundred to each functional for each molecule, transforming the complicated task of learning photophysical properties into a simpler regression task. We used the dataset to train a graph attention neural network to predict the scores for unseen molecules. We call this oracle DELFI (Data-driven EvaLuation of Functionals by Inference), which can be used to quickly screen and predict the ranking of functionals to calculate the optical properties of organic molecules. We validated DELFI in two in silico experiments: choosing a common functional for a series of spiropyran-merocyanine isomers and a unique functional to screen a large dataset of over 50 000 organic photovoltaic molecules, for which an extensive benchmark would be unfeasible. A corresponding web application allows DELFI to be easily run and the results to be analyzed, alleviating the hurdle of choosing the right functional for TD-DFT calculations.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Develop a scoring system to define the accuracy of an excited state's calculation against a higher-accuracy reference and train a graph attention neural network on a large dataset of molecular calculations.

### Problem
- Choosing the right functional for time-dependent density functional theory (TD-DFT) excited state calculations is a non-trivial task left for human experts.

### Hypothesis
- A neural network can be developed to recommend functionals for TD-DFT calculations by considering photophysical properties of molecules.

### Evidence
- The scoring system assigns a value between zero and one hundred to each functional for each molecule, and the trained model (DELFI) can predict the ranking of functionals for calculating the optical properties of organic molecules.

### Conclusion
- DELFI can be used to quickly screen and predict the ranking of functionals for TD-DFT calculations, reducing the need for extensive benchmarks.

## Scientific Objects And Mechanisms
### Entities
- Density functionals
- Excited states
- Molecular properties
- Neural network model (DELFI)

### Materials / Systems
- DELFI: a computer oracle for recommending density functionals for excited states calculations The authors developed DELFI, a neural network-based tool that uses a novel scoring system and a large open database to recommend and rank functionals for TD-DFT excited state calculations of organic molecules, simplifying and accelerating the selection process for accurate photophysical property predictions.
- This is due to the approximations of the method, but also because the photophysical properties of a molecule are defined by a manifold of states that all need to be properly described.
- In this work, we developed a neural network to recommend functionals to be used on molecules for TD-DFT calculations, by simultaneously considering all these properties for a manifold of states.

### Properties
- DELFI: a computer oracle for recommending density functionals for excited states calculations The authors developed DELFI, a neural network-based tool that uses a novel scoring system and a large open database to recommend and rank functionals for TD-DFT excited state calculations of organic molecules, simplifying and accelerating the selection process for accurate photophysical property predictions.
- This is due to the approximations of the method, but also because the photophysical properties of a molecule are defined by a manifold of states that all need to be properly described.
- This includes not only the relative energy of the states, but also capturing the correct character, order, and intensity of the transitions.
- In this work, we developed a neural network to recommend functionals to be used on molecules for TD-DFT calculations, by simultaneously considering all these properties for a manifold of states.
- This was possible by developing a scoring system to define the accuracy of an excited state's calculation against a higher-accuracy reference.

### Measurements
- We validated DELFI in two in silico experiments: choosing a common functional for a series of spiropyran-merocyanine isomers and a unique functional to screen a large dataset of over 50 000 organic photovoltaic molecules, for which an extensive benchmark would be unfeasible.
- Density functionals Excited states Molecular properties Neural network model (DELFI) Quantitative assessment of functional performance Automated prediction of suitable functionals for TD-DFT calculations Reduction in the need for extensive benchmarking of functionals

### Conditions
- The choice is particularly hard for excited state calculations when using its time-dependent formulation (TD-DFT).

### Mechanisms
- Scoring system development for excited state calculations
- Neural network training on molecular property data
- Functional recommendation based on molecular properties

### Outcomes
- Quantitative assessment of functional performance
- Automated prediction of suitable functionals for TD-DFT calculations
- Reduction in the need for extensive benchmarking of functionals

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Chemistry

### Reasoning Motifs
- Data Integration → Model Accuracy
- Pattern Recognition → Prediction Improvement

### General Principles
- Data-Driven Prediction Enhancement
- Model Generalization from Training Data

## Failure Paths / Caveats
- success: Benchmarking of functionals against higher-level methods or experimental results for each excited state. Evidence: This approach is prohibitive when studying large-size molecular systems or screening the optical properties of a large set of molecules.
- partial: Using general qualitative indexes or focusing on specific types of excitations. Evidence: These approaches always require actually running the calculations a priori and might leave out the outperforming functional.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_bdc06b3a427a.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper presents a clear structure of the problem, hypothesis, and the approach taken to develop DELFI. However, some details of the neural network architecture and training process were simplified in the extraction to fit the structured format.
