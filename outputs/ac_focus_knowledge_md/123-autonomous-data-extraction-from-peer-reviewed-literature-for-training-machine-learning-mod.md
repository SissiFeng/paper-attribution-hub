# Autonomous data extraction from peer reviewed literature for training machine learning models of oxidation potentials

## Metadata
- Paper ID: `acfocus_7124ba74d64d`
- Cross-SDL ID: `acgold_d4b828631ef9`
- DOI: 10.1088/2632-2153/ad2f52
- URL: https://iopscience.iop.org/article/10.1088/2632-2153/ad2f52
- Year: 2024
- Authors: Lee, Siwoo; Heinen, Stefan; Khan, Danish; Anatole von Lilienfeld O.
- Venue: Machine Learning: Science and Technology
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Anatole von Lilienfeld
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=checked, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.96
- Missing: conditions
- Notes: No validation notes.

## Source Summary
An automated pipeline combining a convolutional neural network and a large language model was developed to extract and curate tabular data on oxidation potentials from literature, enabling machine learning models to predict values for thousands of organic molecules and revealing trends, while significantly reducing manual data collection effort.

## Abstract
We present an automated data-collection pipeline involving a convolutional neural network and a large language model to extract user-specified tabular data from peer-reviewed literature. The pipeline is applied to 74 reports published between 1957 and 2014 with experimentally-measured oxidation potentials for 592 organic molecules (−0.75 to 3.58 V). After data curation (solvents, reference electrodes, and missed data points), we trained multiple supervised machine learning (ML) models reaching prediction errors similar to experimental uncertainty (∼0.2 V). For experimental measurements of identical molecules reported in multiple studies, we identified the most likely value based on out-of-sample ML predictions. Using the trained ML models, we then estimated oxidation potentials of ∼132k small organic molecules from the QM9 (quantum mechanics data for organic molecules with up to 9 atoms not counting hydrogens) data set, with predicted values spanning 0.21-3.46 V. Analysis of the QM9 predictions in terms of plausible descriptor-property trends suggests that aliphaticity increases the oxidation potential of an organic molecule on average from ∼1.5 V to ∼2 V, while an increase in number of heavy atoms lowers it systematically. The pipeline introduced offers significant reductions in human labor otherwise required for conventional manual data collection of experimental results, and exemplifies how to accelerate scientific research through automation. © 2024 The Author(s). Published by IOP Publishing Ltd

## Scientific Elements
### Hardware / Physical System
- An automated pipeline combining a convolutional neural network and a large language model was developed to extract and curate tabular data on oxidation potentials from literature, enabling machine learning models to predict values for thousands of organic molecules and revealing trends, while significantly reducing manual data collection effort.
- We present an automated data-collection pipeline involving a convolutional neural network and a large language model to extract user-specified tabular data from peer-reviewed literature.

### Method
- Utilizing a convolutional neural network (CNN) for table detection and a large language model (LLM) for text extraction, followed by training supervised machine learning models on the curated data.

### Problem
- Extraction of user-specified tabular data from peer-reviewed literature for training machine learning models of oxidation potentials.

### Hypothesis
- An automated data-collection pipeline can accurately extract and utilize data from scientific literature to train machine learning models for predicting oxidation potentials of organic molecules.

### Evidence
- The pipeline successfully extracted data from 74 scientific publications, leading to a dataset of 592 unique organic molecules with measured oxidation potentials. Trained ML models achieved prediction errors similar to experimental uncertainty (∼0.2 V).

### Conclusion
- The automated pipeline offers significant reductions in human labor required for data collection and exemplifies how to accelerate scientific research through automation.

## Scientific Objects And Mechanisms
### Entities
- Convolutional neural network (CNN) model
- Large language model (LLM)
- Organic molecules
- Oxidation potentials
- Machine learning models

### Materials / Systems
- Organic molecules
- Autonomous data extraction from peer reviewed literature for training machine learning models of oxidation potentials An automated pipeline combining a convolutional neural network and a large language model was developed to extract and curate tabular data on oxidation potentials from literature, enabling machine learning models to predict values for thousands of organic molecules and revealing trends, while significantly reducing manual data collection effort.
- The pipeline is applied to 74 reports published between 1957 and 2014 with experimentally-measured oxidation potentials for 592 organic molecules (−0.75 to 3.58 V).
- For experimental measurements of identical molecules reported in multiple studies, we identified the most likely value based on out-of-sample ML predictions.

### Properties
- Analysis of the QM9 predictions in terms of plausible descriptor-property trends suggests that aliphaticity increases the oxidation potential of an organic molecule on average from ∼1.5 V to ∼2 V, while an increase in number of heavy atoms lowers it systematically.

### Measurements
- For experimental measurements of identical molecules reported in multiple studies, we identified the most likely value based on out-of-sample ML predictions.

### Conditions
- Not specified.

### Mechanisms
- Table detection in document images via CNN
- Text extraction from images using LLM
- Data curation and preprocessing for ML training
- Supervised machine learning for property prediction

### Outcomes
- Creation of a dataset of experimentally-measured oxidation potentials
- Training of ML models with prediction errors similar to experimental uncertainty
- Estimation of oxidation potentials for ∼132k small organic molecules

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Chemistry

### Reasoning Motifs
- Data Extraction → Model Training
- Model Training → Property Prediction

### General Principles
- Information Extraction Enables Knowledge Discovery

## Failure Paths / Caveats
- success: Initial trials with the automated pipeline to extract data from scientific literature. Evidence: The pipeline successfully extracted data from 74 scientific publications with an error rate of ∼10% at both the image and text extraction steps.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_d4b828631ef9.json`
- Cross-SDL extraction quality: 0.9
- Notes: The paper presents a structured approach to automating data extraction from scientific literature and using it for machine learning model training. The reasoning is explicit and well-documented, allowing for a high-confidence extraction.
