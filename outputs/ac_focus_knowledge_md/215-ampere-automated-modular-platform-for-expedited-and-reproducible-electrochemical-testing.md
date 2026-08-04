# AMPERE: automated modular platform for expedited and reproducible electrochemical testing

## Metadata
- Paper ID: `acfocus_e13d0d1981cb`
- Cross-SDL ID: `acgold_bd55574990ed`
- DOI: 10.1039/d4dd00203b
- URL: https://pubs.rsc.org/en/content/articlelanding/2024/dd/d4dd00203b
- Year: 2024
- Authors: Abed J, Bai Y, Persaud D, Kim J, Witt J, Hattrick-Simpers J, Sargent EH
- Venue: Digital Discovery
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Yang Bai, Jason Hattrick-Simpers, Daniel Persaud
- AC programs: Not specified
- AC membership status: AC Staff, AC Full Member, AC Governance, AC Trainee
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=blank

## Validation
- Score: 1.0
- Missing: none
- Notes: No validation notes.

## Source Summary
The paper presents AMPERE, an automated and modular platform that streamlines and accelerates large-scale, reproducible electrochemical catalyst screening and optimization, enabling rapid investigation of catalyst ink formulations and their effects on oxygen evolution reaction performance.

## Abstract
Rapid and reliable electrochemical screening is critical to accelerate the development of catalysts for sustainable energy generation and storage. This paper introduces an automated and modular platform for expedited and reproducible electrochemical testing (AMPERE), designed to enhance the efficiency and reliability of multivariate optimization. The platform integrates a liquid-handling robot with custom-made modular array reactors, offering sample preparation and electrochemical testing in the same platform. Additionally, we use offline inductively coupled plasma optical emission spectroscopy (ICP-OES) to measure metal concentrations in the electrolyte after the reaction, which serves as a proxy for assessing the electrochemical stability. We use the platform to conduct 168 experiments continuously in less than 40 hours to examine the influence of catalyst ink formulation on the performance of Ir, Ru, IrO2, and RuO2 for the oxygen evolution reaction (OER) in acid. We specifically investigate the role of solvent type and concentration, catalyst concentration, and binder content on the performance. We find that Ru/RuO2 catalysts show improvements in activity that are not directly linked to improvements in the electrochemical surface area or inversely correlated to Ru dissolution. This suggests a complex interplay between the catalytic performance of the drop-casted catalyst film and ink formulation. AMPERE simplifies catalyst preparation and testing at large scale, making it faster, more reliable, and accessible for widespread use.

## Scientific Elements
### Hardware / Physical System
- The paper presents AMPERE, an automated and modular platform that streamlines and accelerates large-scale, reproducible electrochemical catalyst screening and optimization, enabling rapid investigation of catalyst ink formulations and their effects on oxygen evolution reaction performance.
- This paper introduces an automated and modular platform for expedited and reproducible electrochemical testing (AMPERE), designed to enhance the efficiency and reliability of multivariate optimization.
- The platform integrates a liquid-handling robot with custom-made modular array reactors, offering sample preparation and electrochemical testing in the same platform.
- Additionally, we use offline inductively coupled plasma optical emission spectroscopy (ICP-OES) to measure metal concentrations in the electrolyte after the reaction, which serves as a proxy for assessing the electrochemical stability.

### Method
- Development and implementation of AMPERE, integrating a liquid-handling robot with custom-made modular array reactors for sample preparation and electrochemical testing.

### Problem
- Rapid and reliable electrochemical screening to accelerate the development of catalysts for sustainable energy generation and storage.

### Hypothesis
- An automated and modular platform for expedited and reproducible electrochemical testing can enhance efficiency and reliability in multivariate optimization of catalyst ink formulations.

### Evidence
- AMPERE conducted 168 experiments in less than 40 hours, examining the influence of catalyst ink formulation on the performance of Ir, Ru, IrO2, and RuO2 for the oxygen evolution reaction (OER) in acid.

### Conclusion
- AMPERE simplifies catalyst preparation and testing at large scale, making it faster, more reliable, and accessible for widespread use.

## Scientific Objects And Mechanisms
### Entities
- Ir, Ru, IrO2, and RuO2 catalysts
- Catalyst ink formulation
- Electrochemical surface area (ECSA)
- Metal dissolution

### Materials / Systems
- Ir, Ru, IrO2, and RuO2 catalysts
- Catalyst ink formulation
- Metal dissolution
- AMPERE: automated modular platform for expedited and reproducible electrochemical testing The paper presents AMPERE, an automated and modular platform that streamlines and accelerates large-scale, reproducible electrochemical catalyst screening and optimization, enabling rapid investigation of catalyst ink formulations and their effects on oxygen evolution reaction performance.
- Rapid and reliable electrochemical screening is critical to accelerate the development of catalysts for sustainable energy generation and storage.
- Additionally, we use offline inductively coupled plasma optical emission spectroscopy (ICP-OES) to measure metal concentrations in the electrolyte after the reaction, which serves as a proxy for assessing the electrochemical stability.

### Properties
- Rapid and reliable electrochemical screening is critical to accelerate the development of catalysts for sustainable energy generation and storage.
- Additionally, we use offline inductively coupled plasma optical emission spectroscopy (ICP-OES) to measure metal concentrations in the electrolyte after the reaction, which serves as a proxy for assessing the electrochemical stability.
- We find that Ru/RuO2 catalysts show improvements in activity that are not directly linked to improvements in the electrochemical surface area or inversely correlated to Ru dissolution.
- Ir, Ru, IrO2, and RuO2 catalysts Catalyst ink formulation Electrochemical surface area (ECSA) Metal dissolution Improved activity and stability of catalysts Enhanced efficiency and reproducibility in electrochemical testing Streamlined sample preparation and testing process

### Measurements
- Additionally, we use offline inductively coupled plasma optical emission spectroscopy (ICP-OES) to measure metal concentrations in the electrolyte after the reaction, which serves as a proxy for assessing the electrochemical stability.

### Conditions
- We specifically investigate the role of solvent type and concentration, catalyst concentration, and binder content on the performance.

### Mechanisms
- Optimization of catalyst ink formulation for enhanced electrochemical performance
- Assessment of electrochemical stability via metal dissolution measurement
- Determination of ECSA to estimate the number of active sites available for the reaction

### Outcomes
- Improved activity and stability of catalysts
- Enhanced efficiency and reproducibility in electrochemical testing
- Streamlined sample preparation and testing process

## Cross-SDL Transfer
### SDL / Domain Tags
- SDL 1 - Inorganic
- Automation and Robotics
- Materials Science
- Catalysis

### Reasoning Motifs
- Formulation Optimization → Enhanced Performance
- Stability Assessment → Material Selection
- Surface Area Estimation → Activity Prediction

### General Principles
- Control Through Optimization
- Measurement Precision → Outcome Fidelity
- Surface Area → Catalytic Activity

## Failure Paths / Caveats
- failure: Use of FTO glass as a substrate for drop-casted films. Evidence: FTO glass resulted in erroneous measurements lowering the success rate due to detachment of the catalyst layer during electrochemical testing.
- failure: Use of glassy carbon as a substrate for standard testing and ECSA measurement. Evidence: Glassy carbon introduced significant measurement errors due to excessive oxygen bubbling at high current densities and was not entirely inert under high current densities.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_bd55574990ed.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper provides a clear structure of the problem, hypothesis, method, evidence, and conclusion. However, the reasoning behind the choice of specific ink formulation parameters and their expected impact on catalyst performance is not explicitly stated, requiring some inference.
