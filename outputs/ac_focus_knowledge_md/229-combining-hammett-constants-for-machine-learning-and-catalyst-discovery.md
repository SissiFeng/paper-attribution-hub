# Combining Hammett σ constants for Δ-machine learning and catalyst discovery

## Metadata
- Paper ID: `acfocus_594b9b1922b8`
- Cross-SDL ID: `acgold_320cac94a8b2`
- DOI: 10.1039/d4dd00228h
- URL: https://pubs.rsc.org/en/content/articlelanding/2024/dd/d4dd00228h
- Year: 2024
- Authors: Rakotonirina, V. Diana; Bragato, Marco; Heinen, Stefan; von Lilienfeld, O. Anatole
- Venue: Digital Discovery
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Anatole von Lilienfeld
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=checked, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.86
- Missing: hardware, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
The study demonstrates that the Hammett-inspired product (HIP) Ansatz, with an additive combination rule for ligand constants (cHIP), improves data efficiency and predictive accuracy in computational ligand tuning for organometallic catalysis, enabling effective Δ-machine learning baselines and identification of promising novel catalysts, particularly for the Suzuki-Miyaura reaction.

## Abstract
We study the applicability of the Hammett-inspired product (HIP) Ansatz to model relative substrate binding within homogenous organometallic catalysis, assigning σ and ρ to ligands and metals, respectively. Implementing an additive combination (c) rule for obtaining σ constants for any ligand pair combination results in a cHIP model that enhances data efficiency in computational ligand tuning. We show its usefulness (i) as a baseline for Δ-machine learning (ML), and (ii) to identify novel catalyst candidates via volcano plots. After testing the combination rule on Hammett constants previously published in the literature, we have generated numerical evidence for the Suzuki-Miyaura (SM) C-C cross-coupling reaction using two synthetic datasets of metallic catalysts (including (10) and (11)-metals Ni, Pd, Pt, and Cu, Ag, Au as well as 96 ligands such as N-heterocyclic carbenes, phosphines, or pyridines). When used as a baseline, Δ-ML prediction errors of relative binding decrease systematically with training set size and reach chemical accuracy (∼1 kcal mol−1) for 20k training instances. Employing the individual ligand constants obtained from cHIP, we report relative substrate binding for a novel dataset consisting of 720 catalysts (not part of training data), of which 145 fall into the most promising range on the volcano plot accounting for oxidative addition, transmetalation, and reductive elimination steps. Multiple Ni-based catalysts, e.g. Aphos-Ni-P(t-Bu)3, are included among these promising candidates, potentially offering dramatic cost savings in experimental applications. © 2024 RSC.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Implementing an additive combination rule for obtaining s constants for any ligand pair combination, resulting in a cHIP model, tested via D-machine learning and volcano plots for novel catalyst candidate identification

### Problem
- Efficient exploration of vast chemical compound space for catalyst discovery

### Hypothesis
- The Hammett-inspired product (HIP) Ansatz can model relative substrate binding within homogeneous organometallic catalysis, enhancing data efficiency in computational ligand tuning

### Evidence
- D-ML prediction errors of relative binding decrease systematically with training set size, reaching chemical accuracy for 20k training instances; 145 promising catalyst candidates identified using cHIP

### Conclusion
- The additive combination rule with Hammett's equation is effective for computational catalyst discovery, particularly for smaller chemical compound subspaces

## Scientific Objects And Mechanisms
### Entities
- Hammett constants (s and r)
- Ligand-metal catalyst complexes
- Relative binding energies
- Volcano plots

### Materials / Systems
- Ligand-metal catalyst complexes
- Combining Hammett σ constants for Δ-machine learning and catalyst discovery The study demonstrates that the Hammett-inspired product (HIP) Ansatz, with an additive combination rule for ligand constants (cHIP), improves data efficiency and predictive accuracy in computational ligand tuning for organometallic catalysis, enabling effective Δ-machine learning baselines and identification of promising novel catalysts, particularly for the Suzuki-Miyaura reaction.
- We show its usefulness (i) as a baseline for Δ-machine learning (ML), and (ii) to identify novel catalyst candidates via volcano plots.
- After testing the combination rule on Hammett constants previously published in the literature, we have generated numerical evidence for the Suzuki-Miyaura (SM) C-C cross-coupling reaction using two synthetic datasets of metallic catalysts (including (10) and (11)-metals Ni, Pd, Pt, and Cu, Ag, Au as well as 96 ligands such as N-heterocyclic carbenes, phosphines, or pyridines).

### Properties
- Combining Hammett σ constants for Δ-machine learning and catalyst discovery The study demonstrates that the Hammett-inspired product (HIP) Ansatz, with an additive combination rule for ligand constants (cHIP), improves data efficiency and predictive accuracy in computational ligand tuning for organometallic catalysis, enabling effective Δ-machine learning baselines and identification of promising novel catalysts, particularly for the Suzuki-Miyaura reaction.
- When used as a baseline, Δ-ML prediction errors of relative binding decrease systematically with training set size and reach chemical accuracy (∼1 kcal mol−1) for 20k training instances.
- Implementing an additive combination rule for obtaining s constants for any ligand pair combination, resulting in a cHIP model, tested via D-machine learning and volcano plots for novel catalyst candidate identification D-ML prediction errors of relative binding decrease systematically with training set size, reaching chemical accuracy for 20k training instances; 145 promising catalyst candidates identified using cHIP Hammett constants (s and r) Ligand-metal catalyst complexes Relative binding energies Volcano plots Enhanced data efficiency in computational ligand tuning Identification of novel catalyst candidates Prediction of relative binding energies for catalyst complexes

### Measurements
- Implementing an additive combination rule for obtaining s constants for any ligand pair combination, resulting in a cHIP model, tested via D-machine learning and volcano plots for novel catalyst candidate identification D-ML prediction errors of relative binding decrease systematically with training set size, reaching chemical accuracy for 20k training instances; 145 promising catalyst candidates identified using cHIP Hammett constants (s and r) Ligand-metal catalyst complexes Relative binding energies Volcano plots Enhanced data efficiency in computational ligand tuning Identification of novel catalyst candidates Prediction of relative binding energies for catalyst complexes

### Conditions
- Not specified.

### Mechanisms
- Linear free energy relationships partitioning systems into fragments
- Combination rules for estimating thermodynamic properties of mixtures
- D-machine learning for residual learning and data needs mitigation

### Outcomes
- Enhanced data efficiency in computational ligand tuning
- Identification of novel catalyst candidates
- Prediction of relative binding energies for catalyst complexes

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Chemistry

### Reasoning Motifs
- Partitioning → Complexity Reduction
- Combination → Property Estimation

### General Principles
- Simplicity Enables Efficiency
- Decomposition Enhances Predictability

## Failure Paths / Caveats
- No explicit failure path available in CSV/cross-SDL extraction.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_320cac94a8b2.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper presents a structured approach to catalyst discovery using computational methods, with clear hypotheses, methods, and outcomes. However, some details on the failure modes or alternative approaches considered were not explicitly discussed, leading to a moderate extraction quality score.
