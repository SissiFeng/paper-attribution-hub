# Crash testing machine learning force fields for molecules, materials, and interfaces: molecular dynamics in the TEA challenge 2023

## Metadata
- Paper ID: `acfocus_37cb4c6d2251`
- Cross-SDL ID: `acgold_f0e4f82d73ab`
- DOI: 10.1039/d4sc06530a
- URL: https://pubs.rsc.org/en/content/articlepdf/2025/sc/d4sc06530a
- Year: 2025
- Authors: Poltavsky I., Puleva M., Charkin-Gorbulin A., Fonseca G., Batatia I., Browning N.J., Chmiela S., Cui M., Frank J.T., Heinen S., Huang B., Käser S., Kabylda A., Khan D., Müller C., Price A.J.A., Riedmiller K., Töpfer K., Ko T.W., Meuwly M., Rupp M., Csányi G., Anatole von Lilienfeld O., Margraf J.T., Müller K.-R., Tkatchenko A.
- Venue: Chemical Science
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Anatole von Lilienfeld
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=checked, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.72
- Missing: source_summary, hardware, measurements, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
Not specified in CSV.

## Abstract
Crash testing machine learning force ﬁelds for
molecules, materials, and interfaces: model analysis
in the TEA Challenge 2023†
Igor Poltavsky,
*a Anton Charkin-Gorbulin,‡ab Mirela Puleva,‡ac Gr´egory Fonseca,‡a
Ilyes Batatia,d Nicholas J. Browning,e Stefan Chmiela,fg Mengnan Cui,h
J. Thorben Frank,
fg Stefan Heinen,i Bing Huang,j Silvan K¨aser,
k Adil Kabylda,
a
Danish Khan,il Carolin Müller,
m Alastair J. A. Price,no Kai Riedmiller,
p
Kai Töpfer,
k Tsz Wai Ko,q Markus Meuwly,
k Matthias Rupp,
r G´abor Cs´anyi,
d
O. Anatole von Lilienfeld,
fginost Johannes T. Margraf,u Klaus-Robert Müller
fgvwx
and Alexandre Tkatchenko
*ac
Atomistic simulations are routinely employed in academia and industry to study the behavior of molecules,
materials, and their interfaces. Central to these simulations are force ﬁelds (FFs), whose development is
challenged by intricate interatomic interactions at diﬀerent spatio-temporal scales and the vast expanse
of chemical space. Machine learning (ML) FFs, trained on quantum-mechanical energies and forces, have
shown the capacity to achieve sub-kcal (mol−1 Å−1) accuracy while maintaining computational eﬃciency.
The TEA Challenge 2023 rigorously evaluated commonly used MLFFs across diverse applications,
highlighting their strengths and weaknesses. Participants trained their models using provided datasets,
and the results were systematically analyzed to assess the ability of MLFFs to reproduce potential energy
surfaces, handle incomplete reference data, manage multi-component systems, and model complex
periodic structures. This publication describes the datasets, outlines the proposed challenges, and
presents a detailed analysis of the accuracy, stability, and eﬃciency of the MACE, SO3krates, sGDML,
SOAP/GAP, and FCHL19* architectures in molecular dynamics simulations. The models represent the
MLFF developers who participated in the TEA Challenge 2023. All results presented correspond to the
state of the ML architectures as of October 2023. A co

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- The TEA Challenge 2023 evaluated commonly used ML force fields across diverse applications to assess their ability to reproduce potential energy surfaces, handle incomplete reference data, manage multi-component systems, and model complex periodic structures.

### Problem
- Developing effective force fields (FFs) for accurate and reliable computer simulations of chemical systems across broad chemical spaces.

### Hypothesis
- Machine learning (ML) force fields, trained on quantum-mechanical energies and forces, can achieve quantum-chemical accuracy while maintaining computational efficiency.

### Evidence
- The challenge involved training models on provided datasets and systematically analyzing their performance in molecular dynamics simulations. Outcomes included Mean Absolute Errors (MAE), Root Mean Squared Errors (RMSE), and maximum errors in energy and force predictions.

### Conclusion
- ML force fields, particularly those with equivariant neural network architectures, showed significant advancements in accuracy and stability, establishing new standards for force predictions in molecular and materials simulations.

## Scientific Objects And Mechanisms
### Entities
- Machine learning force fields (MLFFs)
- Quantum-mechanical energies and forces
- Potential energy surfaces (PES)
- Molecular dynamics simulations

### Materials / Systems
- Crash testing machine learning force fields for molecules, materials, and interfaces: molecular dynamics in the TEA challenge 2023 The TEA Challenge 2023 evaluated commonly used ML force fields across diverse applications to assess their ability to reproduce potential energy surfaces, handle incomplete reference data, manage multi-component systems, and model complex periodic structures.

### Properties
- Crash testing machine learning force fields for molecules, materials, and interfaces: molecular dynamics in the TEA challenge 2023 The TEA Challenge 2023 evaluated commonly used ML force fields across diverse applications to assess their ability to reproduce potential energy surfaces, handle incomplete reference data, manage multi-component systems, and model complex periodic structures.
- Outcomes included Mean Absolute Errors (MAE), Root Mean Squared Errors (RMSE), and maximum errors in energy and force predictions.
- Machine learning force fields (MLFFs) Quantum-mechanical energies and forces Potential energy surfaces (PES) Molecular dynamics simulations Improved accuracy in predicting potential energy surfaces and forces Reduction in maximum errors and heterogeneity in force predictions Better handling of non-covalent interactions and complex chemical systems Increased stability and efficiency in molecular dynamics simulations

### Measurements
- Not specified.

### Conditions
- Not specified.

### Mechanisms
- Training MLFFs on quantum-mechanical data to achieve high accuracy
- Extrapolating in configurational space to predict unseen data
- Handling incomplete and multi-component systems in MLFFs
- Assessing stability and computational efficiency in MD simulations

### Outcomes
- Improved accuracy in predicting potential energy surfaces and forces
- Reduction in maximum errors and heterogeneity in force predictions
- Better handling of non-covalent interactions and complex chemical systems
- Increased stability and efficiency in molecular dynamics simulations

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Chemistry
- Materials Science

### Reasoning Motifs
- Data Quality → Model Accuracy
- Model Generalization → Prediction Reliability
- Performance Metrics → Simulation Trustworthiness
- Computational Efficiency → Practical Applicability

### General Principles
- Information Quality Dictates Outcome Precision
- Generalization Ability Enhances Model Utility
- Metrics Transparency Ensures Result Credibility
- Efficiency Enables Scalability

## Failure Paths / Caveats
- partial: Training MLFFs on incomplete or partial datasets to assess their ability to predict potential energy surfaces. Evidence: MLFFs showed significant prediction discrepancies and instability, highlighting the importance of comprehensive training datasets.
- success: Comparing the stability of different MLFF architectures in MD simulations at varying temperatures. Evidence: Equivariant neural network architectures like MACE and SO3krates demonstrated better stability in MD simulations.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_f0e4f82d73ab.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper provides a comprehensive evaluation of MLFFs across various challenges, allowing for a structured extraction of scientific reasoning. However, some details on the specific training processes and algorithmic nuances of the MLFFs were not explicitly discussed, requiring inference in some areas.
