# Does this smell the same? Learning representations of olfactory mixtures using inductive biases

## Metadata
- Paper ID: `acfocus_821d50acb29d`
- Cross-SDL ID: `acgold_525270086955`
- DOI: 10.1088/2632-2153/adfffc
- URL: https://iopscience.iop.org/article/10.1088/2632-2153/adfffc
- Year: 2025
- Authors: G. Tom; C. Tian Ser; E. M. Rajaonson; S. Lo; H. Suk Park; B. K. Lee; B. Sanchez-Lengeling
- Venue: Machine Learning: Science and Technology
- Category: Journal Article
- Peer reviewed: Peer Reviewed
- AC members: Benjamin Sanchez
- AC programs: Not specified
- AC membership status: AC Full Member
- Flags: acknowledges_ac=checked, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.8
- Missing: hardware, measurements, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
POMMix is a new model that extends the principal odor map to represent complex odor mixtures using deep learning techniques, achieving state-of-the-art results and advancing the digitization of olfaction.

## Abstract
Olfaction—how molecules are perceived as odors to humans—is a relatively less understood sensory system compared to vision or hearing. Recently, the principal odor map (POM) was introduced to digitize the olfactory properties of single compounds. However, smells in real life are not pure single molecules, but complex mixtures of molecules, whose representations remain relatively under-explored due to limited data in olfactory mixtures. We introduce POMMix, a mixture model extension of POM which leverages mono-molecular olfactory data to build meaningful mixture representations of smells. Our model builds upon the symmetries of the problem space in a hierarchical manner: (1) graph neural networks for building mono-molecular embeddings, (2) attention mechanisms for aggregating molecular representations into mixture representations, and (3) cosine prediction heads to encode olfactory perceptual distance in the mixture embedding space. POMMix achieves state-of-the-art performance across multiple datasets. We perform comprehensive ablation studies of the components of POMMix to understand the contribution of each component. We evaluate the generalizability of the model, explore olfactory phenomena with the representations, and analyze the interpretability of the representations. Our work advances the effort to digitize olfaction, highlighting the synergy of domain expertise and deep learning in crafting mixture representations in low-data regimes. © 2025 The Author(s). Published by IOP Publishing Ltd.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- The POMMIX model, which combines graph neural networks for building mono-molecular embeddings, attention mechanisms for aggregating molecular representations into mixture representations, and cosine prediction heads to encode olfactory perceptual distance in the mixture embedding space.

### Problem
- How molecules are perceived as odors to humans, specifically the challenge of representing complex mixtures of molecules in olfaction compared to single molecules.

### Hypothesis
- A model can be developed to predict the olfactory similarities between mixtures of molecules by leveraging mono-molecular olfactory data.

### Evidence
- POMMIX achieves state-of-the-art performance across multiple datasets, as evidenced by high Pearson correlation coefficients, low root-mean-squared error, and high Kendall ranking coefficient.

### Conclusion
- POMMIX, an extension of the principal odor map, successfully predicts olfactory similarities between mixtures of molecules, highlighting the synergy of domain expertise and deep learning in crafting mixture representations in low-data regimes.

## Scientific Objects And Mechanisms
### Entities
- Molecular graphs derived from SMILES representations
- Graph neural networks (GNNs)
- Attention mechanisms
- Mixture embeddings
- Olfactory perceptual distance

### Materials / Systems
- Olfaction—how molecules are perceived as odors to humans—is a relatively less understood sensory system compared to vision or hearing.
- However, smells in real life are not pure single molecules, but complex mixtures of molecules, whose representations remain relatively under-explored due to limited data in olfactory mixtures.
- A new model building block, CHEMIX, for encoding mixtures of molecules.

### Properties
- Recently, the principal odor map (POM) was introduced to digitize the olfactory properties of single compounds.
- POMMIX achieves state-of-the-art performance across multiple datasets, as evidenced by high Pearson correlation coefficients, low root-mean-squared error, and high Kendall ranking coefficient.

### Measurements
- Not specified.

### Conditions
- Not specified.

### Mechanisms
- Graph neural networks create embeddings for individual molecules based on their graph structures.
- Attention mechanisms aggregate molecular embeddings into a representation for the entire mixture.
- Cosine prediction heads compare mixture embeddings to predict the perceptual similarity of mixtures.

### Outcomes
- Improved predictions of olfactory mixture similarity.
- State-of-the-art performance on olfactory mixture similarity prediction tasks.
- A new model building block, CHEMIX, for encoding mixtures of molecules.

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Biology
- Therapeutics

### Reasoning Motifs
- Permutation invariance → Robustness to input order
- Domain expertise incorporation → Improved generalization
- Hierarchical representation learning → Enhanced expressivity

### General Principles
- Information integration across levels (from molecular to mixture level)
- Symmetry and invariance in representation learning
- Aggregation of individual components to system-level properties

## Failure Paths / Caveats
- No explicit failure path available in CSV/cross-SDL extraction.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_525270086955.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper provides a clear structure and explicit statements of the problem, hypothesis, and methods, facilitating the extraction process. However, some inferences were necessary to fill in the details of the exploration narrative and potential future work.
