# Reflection-Equivariant Diffusion for 3D Structure Determination from Isotopologue Rotational Spectra in Natural Abundance

## Metadata
- Paper ID: `acfocus_8b038025e268`
- Cross-SDL ID: `acgold_98eab3a4dd92`
- DOI: 10.48550/arxiv.2310.11609
- URL: https://arxiv.org/abs/2310.11609
- Year: 2023
- Authors: Cheng, Austin; Lo, Alston; Miret, Santiago; Pate, Brooks; Aspuru-Guzik, Alán
- Venue: arxiv
- Category: Preprint
- Peer reviewed: Non Peer Reviewed
- AC members: Alán Aspuru-Guzik
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=checked, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.72
- Missing: evidence, conditions, mechanisms, outcomes
- Notes: No validation notes.

## Source Summary
KREED is a generative diffusion model that accurately infers the complete 3D structure of small organic molecules from molecular formula, moments of inertia, and unsigned isotopic substitution coordinates, achieving over 98% accuracy on benchmark datasets and demonstrating experimental applicability for structure determination using rotational spectroscopy.

## Abstract
Structure determination is necessary to identify unknown organic molecules, such as those in natural products, forensic samples, the interstellar medium, and laboratory syntheses. Rotational spectroscopy enables structure determination by providing accurate 3D information about small organic molecules via their moments of inertia. Using these moments, Kraitchman analysis determines isotopic substitution coordinates, which are the unsigned $|x|,|y|,|z|$ coordinates of all atoms with natural isotopic abundance, including carbon, nitrogen, and oxygen. While unsigned substitution coordinates can verify guesses of structures, the missing $+/-$ signs make it challenging to determine the actual structure from the substitution coordinates alone. To tackle this inverse problem, we develop KREED (Kraitchman REflection-Equivariant Diffusion), a generative diffusion model that infers a molecule's complete 3D structure from its molecular formula, moments of inertia, and unsigned substitution coordinates of heavy atoms. KREED's top-1 predictions identify the correct 3D structure with &gt;98% accuracy on the QM9 and GEOM datasets when provided with substitution coordinates of all heavy atoms with natural isotopic abundance. When substitution coordinates are restricted to only a subset of carbons, accuracy is retained at 91% on QM9 and 32% on GEOM. On a test set of experimentally measured substitution coordinates gathered from the literature, KREED predicts the correct all-atom 3D structure in 25 of 33 cases, demonstrating experimental applicability for context-free 3D structure determination with rotational spectroscopy.

## Scientific Elements
### Hardware / Physical System
- KREED is a generative diffusion model that accurately infers the complete 3D structure of small organic molecules from molecular formula, moments of inertia, and unsigned isotopic substitution coordinates, achieving over 98% accuracy on benchmark datasets and demonstrating experimental applicability for structure determination using rotational spectroscopy.
- Rotational spectroscopy enables structure determination by providing accurate 3D information about small organic molecules via their moments of inertia.
- On a test set of experimentally measured substitution coordinates gathered from the literature, KREED predicts the correct all-atom 3D structure in 25 of 33 cases, demonstrating experimental applicability for context-free 3D structure determination with rotational spectroscopy.

### Method
- KREED is a generative diffusion model that accurately infers the complete 3D structure of small organic molecules from molecular formula, moments of inertia, and unsigned isotopic substitution coordinates, achieving over 98% accuracy on benchmark datasets and demonstrating experimental applicability for structure determination using rotational spectroscopy.

### Problem
- Not specified by cross-SDL extraction.

### Hypothesis
- Not specified by cross-SDL extraction.

### Evidence
- Not specified by cross-SDL extraction.

### Conclusion
- Not specified by cross-SDL extraction.

## Scientific Objects And Mechanisms
### Entities
- Artificial Intelligence & Data Science
- Chemistry

### Materials / Systems
- Reflection-Equivariant Diffusion for 3D Structure Determination from Isotopologue Rotational Spectra in Natural Abundance KREED is a generative diffusion model that accurately infers the complete 3D structure of small organic molecules from molecular formula, moments of inertia, and unsigned isotopic substitution coordinates, achieving over 98% accuracy on benchmark datasets and demonstrating experimental applicability for structure determination using rotational spectroscopy.
- Structure determination is necessary to identify unknown organic molecules, such as those in natural products, forensic samples, the interstellar medium, and laboratory syntheses.
- Rotational spectroscopy enables structure determination by providing accurate 3D information about small organic molecules via their moments of inertia.

### Properties
- Reflection-Equivariant Diffusion for 3D Structure Determination from Isotopologue Rotational Spectra in Natural Abundance KREED is a generative diffusion model that accurately infers the complete 3D structure of small organic molecules from molecular formula, moments of inertia, and unsigned isotopic substitution coordinates, achieving over 98% accuracy on benchmark datasets and demonstrating experimental applicability for structure determination using rotational spectroscopy.
- KREED's top-1 predictions identify the correct 3D structure with &gt;98% accuracy on the QM9 and GEOM datasets when provided with substitution coordinates of all heavy atoms with natural isotopic abundance.
- When substitution coordinates are restricted to only a subset of carbons, accuracy is retained at 91% on QM9 and 32% on GEOM.

### Measurements
- Reflection-Equivariant Diffusion for 3D Structure Determination from Isotopologue Rotational Spectra in Natural Abundance KREED is a generative diffusion model that accurately infers the complete 3D structure of small organic molecules from molecular formula, moments of inertia, and unsigned isotopic substitution coordinates, achieving over 98% accuracy on benchmark datasets and demonstrating experimental applicability for structure determination using rotational spectroscopy.
- Rotational spectroscopy enables structure determination by providing accurate 3D information about small organic molecules via their moments of inertia.
- On a test set of experimentally measured substitution coordinates gathered from the literature, KREED predicts the correct all-atom 3D structure in 25 of 33 cases, demonstrating experimental applicability for context-free 3D structure determination with rotational spectroscopy.

### Conditions
- Not specified.

### Mechanisms
- Not specified.

### Outcomes
- Not specified.

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Chemistry

### Reasoning Motifs
- Not specified by cross-SDL extraction.

### General Principles
- Not specified by cross-SDL extraction.

## Failure Paths / Caveats
- No explicit failure path available in CSV/cross-SDL extraction.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_98eab3a4dd92.json`
- Cross-SDL extraction quality: 0.0
- Notes: Extraction failed — parse error: Expecting ',' delimiter: line 52 column 4 (char 2553)
