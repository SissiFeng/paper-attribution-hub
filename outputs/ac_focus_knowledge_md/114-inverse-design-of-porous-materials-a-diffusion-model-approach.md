# Inverse design of porous materials: a diffusion model approach

## Metadata
- Paper ID: `acfocus_d27292a1b7a9`
- Cross-SDL ID: `acgold_626d9fac0070`
- DOI: 10.1039/d3ta06274k
- URL: https://pubs.rsc.org/en/content/articlehtml/2024/ta/d3ta06274k
- Year: 2024
- Authors: Park J, Gill APS, Moosavi SM, Kim J
- Venue: Journal of Materials Chemistry A
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Mohamad Moosavi
- AC programs: Not specified
- AC membership status: AC Full Member
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=checked

## Validation
- Score: 0.84
- Missing: hardware, measurements
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
A newly developed diffusion model for generating pure silica zeolite demonstrates superior performance over GANs in creating novel crystalline porous materials and excels in inverse design tasks, highlighting the transformative potential of diffusion models in material discovery.

## Abstract
The success of diffusion models in the field of image processing has propelled the creation of software such as Dall-E, Midjourney and Stable Diffusion, which are tools used for text-to-image generation. Mapping this workflow onto material discovery, a new diffusion model was developed for the generation of pure silica zeolite, marking one of the first applications of diffusion models to porous materials. Our model demonstrates the ability to generate novel crystalline porous materials that are not present in the training dataset, while exhibiting exceptional performance in inverse design tasks targeted on various chemical properties including the void fraction, Henry coefficient and heat of adsorption. Comparing our model with a Generative Adversarial Network (GAN) revealed that the diffusion model outperforms the GAN in terms of structure validity, exhibiting an over 2000-fold improvement in performance. We firmly believe that diffusion models (along with other deep generative models) hold immense potential in revolutionizing the design of new materials, and anticipate the wide extension of our model to other classes of porous materials.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- The authors developed a new diffusion model named zeolite diffusion (ZeoDiﬀ) based on the Denoising Diﬀusion Probabilistic Model (DDPM) framework, using three-dimensional grids composed of energy, silicon, and oxygen channels as input representation.

### Problem
- The generation of porous materials using diffusion models remains unexplored due to challenges arising from the relatively large number of atoms and the difficulty in capturing essential topological features.

### Hypothesis
- A diffusion model can be developed to generate pure silica zeolites, marking one of the first applications of diffusion models to porous materials.

### Evidence
- The model successfully generated structures with high validity while exhibiting exceptional capabilities in inverse design at the same time. Quantitative comparisons with GAN demonstrated that the diffusion model outperforms GAN by more than 2000 times in terms of structure validity.

### Conclusion
- The diffusion model developed in this work can generate new zeolite structures unseen during the training phase and demonstrates vast improvement over the GAN model under the same conditions.

## Scientific Objects And Mechanisms
### Entities
- pure silica zeolites
- Denoising Diﬀusion Probabilistic Model (DDPM)
- zeolite structures
- energy grid
- silicon grid
- oxygen grid

### Materials / Systems
- Inverse design of porous materials: a diffusion model approach A newly developed diffusion model for generating pure silica zeolite demonstrates superior performance over GANs in creating novel crystalline porous materials and excels in inverse design tasks, highlighting the transformative potential of diffusion models in material discovery.
- Mapping this workflow onto material discovery, a new diffusion model was developed for the generation of pure silica zeolite, marking one of the first applications of diffusion models to porous materials.
- Our model demonstrates the ability to generate novel crystalline porous materials that are not present in the training dataset, while exhibiting exceptional performance in inverse design tasks targeted on various chemical properties including the void fraction, Henry coefficient and heat of adsorption.

### Properties
- Our model demonstrates the ability to generate novel crystalline porous materials that are not present in the training dataset, while exhibiting exceptional performance in inverse design tasks targeted on various chemical properties including the void fraction, Henry coefficient and heat of adsorption.
- The authors developed a new diffusion model named zeolite diffusion (ZeoDiﬀ) based on the Denoising Diﬀusion Probabilistic Model (DDPM) framework, using three-dimensional grids composed of energy, silicon, and oxygen channels as input representation.
- pure silica zeolites Denoising Diﬀusion Probabilistic Model (DDPM) zeolite structures energy grid silicon grid oxygen grid generation of novel crystalline porous materials not present in the training dataset exceptional performance in inverse design tasks targeted on various chemical properties over 2000-fold improvement in performance compared to GAN in terms of structure validity

### Measurements
- Not specified.

### Conditions
- The model successfully generated structures with high validity while exhibiting exceptional capabilities in inverse design at the same time.

### Mechanisms
- generation of new samples from random noises through the denoising process
- representation of zeolite structures by three-dimensional grids
- calculation of interaction energy between methane and zeolite framework for energy grid preparation
- application of Gaussian functions centered at zeolite atoms' positions for silicon and oxygen grid preparation

### Outcomes
- generation of novel crystalline porous materials not present in the training dataset
- exceptional performance in inverse design tasks targeted on various chemical properties
- over 2000-fold improvement in performance compared to GAN in terms of structure validity

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Chemistry
- Materials Science

### Reasoning Motifs
- Data Representation → Model Performance
- Input Dimensionality → Consistency
- Grid Information → Structural Validity

### General Principles
- Information Representation
- Consistency and Invariance
- Validation and Verification

## Failure Paths / Caveats
- failure: Deem and coworkers employed the Monte Carlo approach for zeolite design. Evidence: lacked the ability to generate structures with user-desired properties
- failure: Kim et al. used the GAN architecture to generate new zeolite structures. Evidence: structures generated exhibited poor structural validity

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_626d9fac0070.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper provides a clear problem statement, hypothesis, and methodology. The reasoning structure is well-organized, but some details on the layer3 motifs and layer4 principles had to be inferred.
