---
type: method
name: variational autoencoder
category: generative model
aliases:
- variational autoencoders
- VAE
used_by_labs:
- aspuru-guzik-lab
- buonassisi-lab
- garton-lab
- moosavi-lab
- wang-lab
paper_count: 31
stages:
  generative_design: 13
  automation_orchestration: 2
  property_prediction: 4
  characterization_analysis: 1
generated: '2026-06-11'
---

# variational autoencoder

- Type: method
- Category: [[wiki/concepts/generative-model|Generative Model]]
- Aliases: variational autoencoders, VAE
- Papers: 31 (2018–2025)

## Labs

| Lab | First year | Papers |
| --- | --- | --- |
| [[wiki/labs/aspuru-guzik-lab|Alán Aspuru-Guzik Group]] | 2025 | 1 |
| [[wiki/labs/buonassisi-lab|Tonio Buonassisi Group]] | 2020 | 1 |
| [[wiki/labs/garton-lab|Michael Garton Group]] | 2024 | 1 |
| [[wiki/labs/moosavi-lab|Mohamad Moosavi Group]] | 2025 | 1 |
| [[wiki/labs/wang-lab|Bo Wang Group]] | 2025 | 1 |

## Stages

- Generative design: 13
- Property prediction: 4
- Automation & orchestration: 2
- Characterization & analysis: 1

## Usage

- (2018): "Our proposed model, SeCTAR, draws inspiration from variational autoencoders, and learns latent representations of trajectories."
- (2020, Generative design): "We adopt variational autoencoder (VAE), a machine learning generative model to learn a latent, reduced representation of a given RVE configuration."
- [[wiki/labs/buonassisi-lab|Tonio Buonassisi Group]] (2020, Automation & orchestration): "To fully achieve the automatic micro-crack detection, we use a variational autoencoder using the principle of unsupervised anomaly detection."
- (2021): "One notable example of such success is the variational autoencoder (VAE)."
- (2021): "Among such approaches, unsupervised learning methods via neural networks including autoencoders (AEs) or variational autoencoders (VAEs) have shown promising performances with applications on various type of data and in different contexts, from cance"
- (2022, Property prediction): "To address this need, we present VADEERS, a Variational Autoencoder-based Drug Efficacy Estimation Recommender System."
- (2022): "The extracted data is visualized in 2-D latent space using an unsupervised machine learning model called the variational autoencoder (VAE)."
- (2022, Generative design): "We focus on different representations of material structure, their impact on inverse design strategies using variational autoencoders or generative adversarial networks, and highlight the potential of these approaches for discovering materials with t"
- (2023, Generative design): "In this paper, we propose an intelligent inverse design approach for electric machines based on a variational autoencoder (VAE), which can effectively address the problem and provide desired motor design candidates for multiple design targets at the"
- (2023, Generative design): "Variational autoencoders (VAEs) are a popular DGM approach that can learn the correlated patterns of amino acid mutations within a multiple sequence alignment (MSA) of protein sequences and distill this information into a low-dimensional latent space"
- (2023, Property prediction): "Through high-throughput screening, UP, and the deep-generative VAE method, PSP relationships that are too complex can be revealed by exploiting the materials’ design space with an emphasis on microstructures."
- (2023, Property prediction): "According to the validations, the VAE-predicted interfacial configuration demonstrates highly similar shear properties to the reference one, justifying its potential for the microstructure design of composite interface."
- (2023): "The variational autoencoder (VAE) approach is used to discover the latent factors of variability in the system."
- (2023, Characterization & analysis): "Pair-Variational Autoencoders for Linking and Cross-Reconstruction of Characterization Data from Complementary Structural Characterization Techniques"
- [[wiki/labs/garton-lab|Michael Garton Group]] (2024, Generative design): "We present a variational autoencoder (ProteinVAE) that can generate synthetic viral vector serotypes without epitopes for pre-existing neutralizing antibodies."

## Adoption

- Origin: [[wiki/labs/buonassisi-lab|Tonio Buonassisi Group]] (2020)
- [[wiki/labs/garton-lab|Michael Garton Group]]: first mention 2024 (+4y)
- [[wiki/labs/aspuru-guzik-lab|Alán Aspuru-Guzik Group]]: first mention 2025 (+5y)
- [[wiki/labs/moosavi-lab|Mohamad Moosavi Group]]: first mention 2025 (+5y)
- [[wiki/labs/wang-lab|Bo Wang Group]]: first mention 2025 (+5y)

## Papers

- Self-Consistent Trajectory Autoencoder: Hierarchical Reinforcement Learning with Trajectory Embeddings (2018) — `ADJACENT`
- Machine learning generative models for automatic design of multi-material 3D printed composite solids (2020) — `ADJACENT`
- Detecting Microcracks in Photovoltaics Silicon Wafers using Varitional Autoencoder (2020) — labs: [[wiki/labs/buonassisi-lab|Tonio Buonassisi Group]] — `EXCLUDE`
- Solving Bayesian Inverse Problems via Variational Autoencoders (2021) — `ADJACENT`
- A survey of autoencoder algorithms to pave the diagnosis of rare diseases (2021) — `ADJACENT`
- A GENERATIVE RECOMMENDER SYSTEM WITH GMM PRIOR FOR CANCER DRUG GENERATION AND SENSITIVITY PREDICTION (2022) — `EXCLUDE`
- PRISMS-Plasticity TM: An Open-Source Rapid Texture Evolution Analysis Pipeline (2022) — `EXCLUDE`
- Deep Generative Models for Materials Discovery and Machine Learning-Accelerated Innovation (2022) — `ADJACENT`
- Electric Machine Inverse Design with Variational Auto-Encoder (VAE) (2023) — `ADJACENT`
- ProtWave-VAE: Integrating Autoregressive Sampling with Latent-Based Inference for Data-Driven Protein Design (2023) — `EXCLUDE`
- Towards inverse microstructure-centered materials design using generative phase-field modeling and deep variational autoencoders (2023) — `ADJACENT`
- Shear behavior of SiCf/SiC interface under the thermo-chemo-mechanical influence and machine-learning-based interfacial microstructure design (2023) — `EXCLUDE`
- Exploring the Evolution of Metal Halide Perovskites via Latent Representations of the Photoluminescent Spectra (2023) — `EXCLUDE`
- Pair-Variational Autoencoders for Linking and Cross-Reconstruction of Characterization Data from Complementary Structural Characterization Techniques (2023) — `ADJACENT`
- Variational autoencoder for design of synthetic viral vector serotypes (2024) — labs: [[wiki/labs/garton-lab|Michael Garton Group]] — `CORE_RELEVANT`
- Co-orchestration of multiple instruments to uncover structure-property relationships in combinatorial libraries (2024) — `ADJACENT`
- Machine learning-enabled discovery of multi-resonance TADF molecules: Unraveling PLQY predictions from molecular structures (2024) — `UNCERTAIN`
- Learning minimal representations of stochastic processes with variational autoencoders (2024) — `UNCERTAIN`
- Multi-Objective Design of DNA-Stabilized Nanoclusters Using Variational Autoencoders With Automatic Feature Extraction (2024) — `ADJACENT`
- Accelerated discovery of eutectic compositionally complex alloys by generative machine learning (2024) — `UNCERTAIN`
- ...and 11 more
