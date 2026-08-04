# Automatic graph representation algorithm for heterogeneous catalysis

## Metadata
- Paper ID: `acfocus_82897d87d4d0`
- Cross-SDL ID: `acgold_f8dc1b1cd49a`
- DOI: 10.48550/arxiv.2306.04742
- URL: https://arxiv.org/abs/2306.04742
- Year: 2023
- Authors: Gariepy, Zachary; Chen, ZhiWen; Tamblyn, Isaac; Singh, Chandra Veer; Feugmo, Conrard Giresse Tetsassi
- Venue: arxiv
- Category: Preprint
- Peer reviewed: Non Peer Reviewed
- AC members: Chandra Veer Singh
- AC programs: Not specified
- AC membership status: AC Full Member
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.9
- Missing: hardware
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
The study introduces an automatic graph representation algorithm (AGRA) that streamlines the extraction and modeling of local chemical environments in heterogeneous catalysis, demonstrating superior transferability, reduced computational cost, and strong predictive performance across multiple catalytic reaction datasets compared to existing methods.

## Abstract
One of the most appealing aspects of machine learning for material design is its high throughput exploration of chemical spaces, but to reach the ceiling of ML-aided exploration, more than current model architectures and processing algorithms are required. New architectures such as Graph Neural Networks (GNNs) have seen significant research investments recently. For heterogeneous catalysis, defining substrate intramolecular bonds and adsorbate/substrate intermolecular bonds is a time-consuming and challenging process. Before applying a model, dataset pre-processing, node/bond descriptor design, and specific model constraints have to be considered. In this work, a framework designed to solve these issues is presented in the form of an automatic graph representation algorithm (AGRA) tool to extract the local chemical environment of metallic surface adsorption sites is presented. This tool is able to gather multiple adsorption geometry datasets composed of different systems and combine them into a single model. To show AGRA's excellent transferability and reduced computational cost compared to other graph representation methods, it was applied to 5 different catalytic reaction datasets and benchmarked against the Open Catalyst Projects (OCP) graph representation method. The two ORR datasets with O/OH adsorbates obtained 0.053 eV RMSD when combined together, whereas the three CO2RR datasets with CHO/CO/COOH obtained an average performance of 0.088 eV RMSD. To further display the algorithm's versatility and extrapolation ability, a model was trained on a subset combination of all 5 datasets with an RMSD of 0.105 eV. This universal model was then used to predict a wide range of adsorption energies and an entirely new ORR catalyst system and then verified through Density Functional Theory calculations

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- AGRA tool development using Python packages Atomic Simulation Environment (ASE) and NetworkX to analyze material systems surface and construct graph representations.

### Problem
- Defining substrate intramolecular bonds and adsorbate/substrate intermolecular bonds for heterogeneous catalysis is time-consuming and challenging.

### Hypothesis
- An automatic graph representation algorithm (AGRA) can efficiently extract the local chemical environment of metallic surface adsorption sites and improve model transferability and reduced computational cost.

### Evidence
- AGRA was applied to 5 different catalytic reaction datasets and benchmarked against the Open Catalyst Projects (OCP) graph representation method, showing improved transferability and reduced computational cost.

### Conclusion
- AGRA successfully automates the graph representation process for adsorption sites, enhancing the efficiency and accuracy of machine learning models in predicting catalytic properties.

## Scientific Objects And Mechanisms
### Entities
- Metallic surface adsorption sites
- Graph Neural Networks (GNNs)
- Adsorbate/catalyst system geometry
- Local chemical environment

### Materials / Systems
- Adsorbate/catalyst system geometry
- One of the most appealing aspects of machine learning for material design is its high throughput exploration of chemical spaces, but to reach the ceiling of ML-aided exploration, more than current model architectures and processing algorithms are required.
- To show AGRA's excellent transferability and reduced computational cost compared to other graph representation methods, it was applied to 5 different catalytic reaction datasets and benchmarked against the Open Catalyst Projects (OCP) graph representation method.
- This universal model was then used to predict a wide range of adsorption energies and an entirely new ORR catalyst system and then verified through Density Functional Theory calculations AGRA tool development using Python packages Atomic Simulation Environment (ASE) and NetworkX to analyze material systems surface and construct graph representations.

### Properties
- Metallic surface adsorption sites Graph Neural Networks (GNNs) Adsorbate/catalyst system geometry Local chemical environment Improved model transferability across different catalytic reaction datasets Reduced computational cost compared to other graph representation methods Enhanced predictive accuracy for catalytic properties

### Measurements
- To show AGRA's excellent transferability and reduced computational cost compared to other graph representation methods, it was applied to 5 different catalytic reaction datasets and benchmarked against the Open Catalyst Projects (OCP) graph representation method.
- AGRA was applied to 5 different catalytic reaction datasets and benchmarked against the Open Catalyst Projects (OCP) graph representation method, showing improved transferability and reduced computational cost.

### Conditions
- One of the most appealing aspects of machine learning for material design is its high throughput exploration of chemical spaces, but to reach the ceiling of ML-aided exploration, more than current model architectures and processing algorithms are required.
- For heterogeneous catalysis, defining substrate intramolecular bonds and adsorbate/substrate intermolecular bonds is a time-consuming and challenging process.

### Mechanisms
- Automatic extraction of local chemical environment based on adsorption site geometry
- Graph construction using node/bond descriptors
- Model training on combined adsorption geometry datasets

### Outcomes
- Improved model transferability across different catalytic reaction datasets
- Reduced computational cost compared to other graph representation methods
- Enhanced predictive accuracy for catalytic properties

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Materials Science
- Catalysis

### Reasoning Motifs
- Data Integration → Model Generalization
- Automated Feature Extraction → Computational Efficiency
- Graph Representation → Predictive Model Accuracy

### General Principles
- Modularity Enables Generalization
- Representation Learning Enhances Prediction
- Graph Theory Unifies Structure-Property Relationships

## Failure Paths / Caveats
- success: Combining multiple adsorbate datasets into a single model for predicting catalytic properties. Evidence: The combined model achieved an average RMSE of 0.053 eV for the ORR datasets and 0.088 eV for the CO2RR datasets.
- success: Predicting a wide range of adsorption energies and an entirely new ORR catalyst system using the universal model. Evidence: The universal model predicted adsorption energies with an RMSD of 0.105 eV and was verified through Density Functional Theory calculations.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_f8dc1b1cd49a.json`
- Cross-SDL extraction quality: 0.9
- Notes: The paper provides a clear structure of the problem, hypothesis, method, and results, making the extraction process straightforward. The reasoning is explicit and well-documented, leading to a high extraction quality.
