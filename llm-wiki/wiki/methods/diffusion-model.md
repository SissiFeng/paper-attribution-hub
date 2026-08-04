---
type: method
name: diffusion model
category: generative model
aliases:
- diffusion models
- denoising diffusion
used_by_labs:
- aspuru-guzik-lab
- moosavi-lab
- wang-lab
paper_count: 20
stages:
  characterization_analysis: 1
  generative_design: 11
  optimization: 1
generated: '2026-06-11'
---

# diffusion model

- Type: method
- Category: [[wiki/concepts/generative-model|Generative Model]]
- Aliases: diffusion models, denoising diffusion
- Papers: 20 (2018–2025)

## Labs

| Lab | First year | Papers |
| --- | --- | --- |
| [[wiki/labs/aspuru-guzik-lab|Alán Aspuru-Guzik Group]] | 2023 | 5 |
| [[wiki/labs/moosavi-lab|Mohamad Moosavi Group]] | 2024 | 2 |
| [[wiki/labs/wang-lab|Bo Wang Group]] | 2025 | 1 |

## Stages

- Generative design: 11
- Characterization & analysis: 1
- Optimization: 1

## Usage

- (2018, Characterization & analysis): "The topics discussed include: study on high frequency pulser based power amplifier for underwater imaging sonar application; robot navigation in an uncertain environment using dynamic programming via Markov decision process; design and analysis of di"
- [[wiki/labs/aspuru-guzik-lab|Alán Aspuru-Guzik Group]] (2023, Generative design): "To tackle this inverse problem, we develop KREED (Kraitchman REflection-Equivariant Diffusion), a generative diffusion model that infers a molecule's complete 3D structure from its molecular formula, moments of inertia, and unsigned substitution coor"
- (2023, Generative design): "Presented here are three methodologies of generation of meaningful 2D and 3D designs, merging text-to-image diffusion models Stable Diffusion, and DALL-E 2 with computational methods."
- [[wiki/labs/aspuru-guzik-lab|Alán Aspuru-Guzik Group]] (2024, Generative design): "To tackle this inverse problem, we develop Kreed (Kraitchman REflection-Equivariant Diffusion), a generative diffusion model that infers a molecule’s complete 3D structure from only its molecular formula, moments of inertia, and unsigned substitution"
- [[wiki/labs/moosavi-lab|Mohamad Moosavi Group]] (2024, Generative design): "Mapping this workflow onto material discovery, a new diffusion model was developed for the generation of pure silica zeolite, marking one of the first applications of diffusion models to porous materials."
- [[wiki/labs/aspuru-guzik-lab|Alán Aspuru-Guzik Group]] (2024, Generative design): "We present a generative diffusion model specifically tailored to the discovery of surface structures."
- (2024, Generative design): "This study shows that applying denoising diffusion probabilistic models (DDPMs), a generative AI method, to US simulation data reduces the computational cost significantly."
- (2024): "By means of simulated data sets corresponding to paradigmatic diffusion models, we showcase its effectiveness in extracting the minimal relevant parameters that accurately describe these dynamics."
- (2024, Generative design): "Very recently denoising diffusion probabilistic models have been shown to be extremely powerful generators producing synthetic data of various modalities e.g."
- (2024, Generative design): "Improvement and adoption of generative machine learning models is rapidly accelerating, as exemplified by the popularity of LLMs (Large Language Models) for text, and diffusion models for image generation."
- (2024, Optimization): "Our study introduces a Generative AI method that employs a cooling-guided diffusion model to optimize the layout of battery cells, a crucial step for enhancing the cooling performance and efficiency of battery thermal management systems."
- (2024): "In this letter, we leverage Signal Temporal Logic (STL) and Diffusion Models to learn controllable, diverse, and rule-aware policy."
- (2024): "A Mechanism-Based Reaction-Diffusion Model for Accelerated Discovery of Thermoset Resins Frontally Polymerized by Olefin Metathesis"
- [[wiki/labs/wang-lab|Bo Wang Group]] (2025): "The model integrates perturbation embeddings as guiding signals within a 2D latent diffusion model."
- [[wiki/labs/aspuru-guzik-lab|Alán Aspuru-Guzik Group]] (2025): "Empirically, enforcing exact moment constraints allows Stiefel Flow Matching to achieve higher success rates and faster sampling than Euclidean diffusion models, even on high-dimensional manifolds corresponding to large molecules in the GEOM dataset."

## Adoption

- Origin: [[wiki/labs/aspuru-guzik-lab|Alán Aspuru-Guzik Group]] (2023)
- [[wiki/labs/moosavi-lab|Mohamad Moosavi Group]]: first mention 2024 (+1y)
- [[wiki/labs/wang-lab|Bo Wang Group]]: first mention 2025 (+2y)

## Papers

- 2018 International Conference on Control, Power, Communication and Computing Technologies, ICCPCCT 2018 (2018) — `ADJACENT`
- Reflection-Equivariant Diffusion for 3D Structure Determination from Isotopologue Rotational Spectra in Natural Abundance (2023) — labs: [[wiki/labs/aspuru-guzik-lab|Alán Aspuru-Guzik Group]] — `CORE_RELEVANT`
- MULTIMODAL ARCHITECTURE: Applications of Language in a Machine Learning Aided Design Process (2023) — `ADJACENT`
- Determining 3D structure from molecular formula and isotopologue rotational spectra in natural abundance with reflection-equivariant diffusion (2024) — labs: [[wiki/labs/aspuru-guzik-lab|Alán Aspuru-Guzik Group]] — `CORE_RELEVANT`
- Inverse design of porous materials: a diffusion model approach (2024) — labs: [[wiki/labs/moosavi-lab|Mohamad Moosavi Group]] — `CORE_RELEVANT`
- Generative diffusion model for surface structure discovery (2024) — labs: [[wiki/labs/aspuru-guzik-lab|Alán Aspuru-Guzik Group]] — `CORE_RELEVANT`
- Application of Generative Artificial Intelligence in Predicting Membrane Partitioning of Drugs: Combining Denoising Diffusion Probabilistic Models and MD Simulations Reduces the Computational Cost to One-Third (2024) — `ADJACENT`
- Learning minimal representations of stochastic processes with variational autoencoders (2024) — `UNCERTAIN`
- Denoising diffusion probabilistic models for generative alloy design (2024) — `ADJACENT`
- Heat Death of Generative Models in Closed-Loop Learning (2024) — `ADJACENT`
- COOLING-GUIDED DIFFUSION MODEL FOR BATTERY CELL ARRANGEMENT (2024) — `EXCLUDE`
- Diverse Controllable Diffusion Policy With Signal Temporal Logic (2024) — `EXCLUDE`
- A Mechanism-Based Reaction-Diffusion Model for Accelerated Discovery of Thermoset Resins Frontally Polymerized by Olefin Metathesis (2024) — `ADJACENT`
- MORPHODIFF: CELLULAR MORPHOLOGY PAINTING WITH DIFFUSION MODELS (2025) — labs: [[wiki/labs/wang-lab|Bo Wang Group]] — `RELATED_RELEVANT`
- STIEFEL FLOW MATCHING FOR MOMENT-CONSTRAINED STRUCTURE ELUCIDATION (2025) — labs: [[wiki/labs/aspuru-guzik-lab|Alán Aspuru-Guzik Group]] — `RELATED_RELEVANT`
- The Rise of Generative AI for Metal-Organic Framework Design and Synthesis (2025) — labs: [[wiki/labs/aspuru-guzik-lab|Alán Aspuru-Guzik Group]], [[wiki/labs/moosavi-lab|Mohamad Moosavi Group]] — `CORE_RELEVANT`
- How Machine Learning Has Driven the Development of Rechargeable Ion Batteries (2025) — `ADJACENT`
- GoFlow: efficient transition state geometry prediction with flow matching and E(3)-equivariant neural networks (2025) — `ADJACENT`
- Molecular representation learning: cross-domain foundations and future Frontiers (2025) — `ADJACENT`
- Generative AI for the Design of Molecules: Advances and Challenges (2025) — `ADJACENT`
