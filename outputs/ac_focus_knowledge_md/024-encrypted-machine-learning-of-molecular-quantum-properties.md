# Encrypted machine learning of molecular quantum properties

## Metadata
- Paper ID: `acfocus_b16848c76770`
- Cross-SDL ID: `acgold_81ec999121aa`
- DOI: 10.1088/2632-2153/acc928
- URL: https://iopscience.iop.org/article/10.1088/2632-2153/acc928
- Year: 2023
- Authors: Weinreich, Jan; Falk Von Rudorff, Guido; Anatole Von Lilienfeld, O
- Venue: Machine Learning: Science and Technology
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Anatole von Lilienfeld
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=checked

## Validation
- Score: 0.73
- Missing: hardware, materials, measurements, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
The authors present a secure and computationally feasible method for encrypted machine learning predictions of molecular quantum properties using oblivious transfer, but find that such encrypted predictions are vastly more expensive than unencrypted ones, highlighting the urgent need for more compact and efficient model architectures.

## Abstract
Abstract             Large machine learning (ML) models with improved predictions have become widely available in the chemical sciences. Unfortunately, these models do not protect the privacy necessary within commercial settings, prohibiting the use of potentially extremely valuable data by others. Encrypting the prediction process can solve this problem by double-blind model evaluation and prohibits the extraction of training or query data. However, contemporary ML models based on fully homomorphic encryption or federated learning are either too expensive for practical use or have to trade higher speed for weaker security. We have implemented secure and computationally feasible encrypted ML models using oblivious transfer enabling and secure predictions of molecular quantum properties across chemical compound space. However, we find that encrypted predictions using kernel ridge regression models are a million times more expensive than without encryption. This demonstrates a dire need for a compact ML model architecture, including molecular representation and kernel matrix size, that minimizes model evaluation costs.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Implementation of secure and computationally feasible encrypted ML models using oblivious transfer enabling secure predictions.

### Problem
- Privacy preservation in machine learning models to protect sensitive data within commercial settings.

### Hypothesis
- Encrypted machine learning can enable secure predictions of molecular quantum properties without disclosing training or query data.

### Evidence
- Encrypted predictions using kernel ridge regression models accurately reproduce unencrypted calculations' results.

### Conclusion
- Encrypted machine learning models can securely predict molecular properties without compromising data privacy.

## Scientific Objects And Mechanisms
### Entities
- Molecular quantum properties
- Encrypted machine learning models
- Kernel ridge regression
- Molecular representation vectors (Coulomb matrix and FCHL19)

### Materials / Systems
- Not specified.

### Properties
- Encrypted machine learning of molecular quantum properties The authors present a secure and computationally feasible method for encrypted machine learning predictions of molecular quantum properties using oblivious transfer, but find that such encrypted predictions are vastly more expensive than unencrypted ones, highlighting the urgent need for more compact and efficient model architectures.
- We have implemented secure and computationally feasible encrypted ML models using oblivious transfer enabling and secure predictions of molecular quantum properties across chemical compound space.
- Molecular quantum properties Encrypted machine learning models Kernel ridge regression Molecular representation vectors (Coulomb matrix and FCHL19) Secure predictions of molecular properties Privacy preservation of training and query data Reduction of computational costs through compact molecular representations

### Measurements
- Not specified.

### Conditions
- Not specified.

### Mechanisms
- Oblivious transfer for secure data exchange
- Kernel ridge regression for supervised learning
- Molecular representation for feature extraction

### Outcomes
- Secure predictions of molecular properties
- Privacy preservation of training and query data
- Reduction of computational costs through compact molecular representations

## Cross-SDL Transfer
### SDL / Domain Tags
- Chemistry
- Artificial Intelligence & Data Science

### Reasoning Motifs
- Privacy → Security
- Feature Complexity → Computational Efficiency
- Model Compactness → Prediction Cost

### General Principles
- Security through encryption
- Computational efficiency through model optimization
- Cost-effectiveness through algorithmic simplicity

## Failure Paths / Caveats
- success: Using encrypted predictions for molecular properties to maintain data privacy. Evidence: Encrypted predictions accurately reproduce unencrypted calculations' results.
- partial: Comparing encrypted predictions using different molecular representations (Coulomb matrix and FCHL19). Evidence: While both representations are effective, the compactness of the Coulomb matrix reduces prediction time and data transfer.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_81ec999121aa.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper provides a clear structure for the problem, hypothesis, method, and results. However, the extraction of layer4_principles is somewhat inferred based on the overall scientific context rather than explicitly stated in the paper.
