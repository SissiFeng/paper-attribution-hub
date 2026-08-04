# Abstract A013: Facilitating AI-Based Hit Discovery through the Development of the AIRCHECK Platform

## Metadata
- Paper ID: `acfocus_7b9375afab99`
- Cross-SDL ID: `not matched`
- DOI: 10.1158/1557-3265.aimachine-a013
- URL: https://aacrjournals.org/clincancerres/article/31/13_Supplement/A013/763272
- Year: 2025
- Authors: N. Bagale; S. Reza; J. Wellnitz; R. M. Couñago; A. Tropsha; B. Haibe-Kains; M. Schapira; C. Arrowsmith; A. Edwards
- Venue: Clinical Cancer Research
- Category: Journal Article
- Peer reviewed: Peer Reviewed
- AC members: Cheryl Arrowsmith
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.63
- Missing: evidence, materials, properties, mechanisms, cross_sdl_match
- Notes: No cross-SDL extraction matched this paper; fields are derived from CSV only.

## Source Summary
The AIRCHECK platform is an open, AI-ready resource that standardizes and shares DEL and ASMS datasets to facilitate robust, transparent, and accessible AI-driven hit discovery in drug development, demonstrated by successful virtual screening and experimental validation of novel compounds.

## Abstract
Abstract Background: Efficient hit discovery is a critical step in drug development, traditionally achieved through high-throughput screening (HTS). Newer methods such as DNA-Encoded Libraries (DEL) and Affinity Selection Mass Spectrometry (ASMS) offer large-scale, cost-effective alternatives. However, they remain limited by synthesis constraints and costly validation steps. To address these challenges, researchers increasingly turn to artificial intelligence (AI) to predict compound bioactivity and virtually screen vast chemical libraries. Although promising, AI performance depends on the quality and diversity of training data and often struggles with generalization. Moreover, most DEL and ASMS datasets are proprietary, hindering transparency and reproducibility. Methods: To tackle the challenges of AI-based hit discovery, we present the Artificial Intelligence Ready CHEmiCal Knowledge-base (AIRCHECK), an open platform designed to make DEL and ASMS datasets accessible and AI-ready. AIRCHECK enables contributors, especially companies working with these technologies, to share data in a standardized format. The datasets are curated, chemical features extracted, and experimental results analyzed to assign proper labels, allowing even those with limited chemistry expertise to build models without additional data processing. Currently, AIRCHECK hosts around 25 AI-ready DEL datasets from three companies, covering billions of compounds, and EAS-MS (Enantioselective Protein ASMS) datasets involving nearly 80 screened proteins. Results: The AIRCHECK platform also offers baseline artificial intelligence models to support the virtual screening of chemical libraries for potential hits, with open-source codes available. The current model is based on a proof-of-concept for fingerprint-based AI-driven hit discovery, implemented as an ensemble of three Light Gradient Boosting Machines (LGBMs), each trained on a different chemical fingerprint: FCFP4, AtomPair, and Topological Torsion. Predictions are averaged across models to enhance robustness. Post-prediction filtering applies multiple chemistry-based rules to prioritize drug-like candidates. To promote chemical diversity, we use fingerprints and the LeaderPicker algorithm to cluster hits and select representative compounds for experimental testing. The model was trained on a subset (∼375,000 compounds) of a 3-billion-member DEL screened against WDR91. It was then used to virtually screen 37 billion compounds from the Enamine REAL Space library. From 48 top-ranked predictions tested experimentally, seven compounds were confirmed to have binding affinities. Significance: These results highlight the effectiveness of AI-driven hit discovery and validate our efforts to expand access to high-quality data, develop robust AI models, and make them openly available. Looking ahead, we plan to grow AIRCHECK into a collaborative framework that enables contributors to build on these resources using open-source tools and cloud platforms to foster transparency, accessibility, and innovation across the biotech and AI communities. Citation Format: Nabin Bagale, Shaghayegh Reza, James Wellnitz, Rafael M. Couñago, Alexander Tropsha, Benjamin Haibe-Kains, Matthieu Schapira, Cheryl Arrowsmith, Aled Edwards. Facilitating AI-Based Hit Discovery through the Development of the AIRCHECK Platform [abstract]. In: Proceedings of the AACR Special Conference in Cancer Research: Artificial Intelligence and Machine Learning; 2025 Jul 10-12; Montreal, QC, Canada. Philadelphia (PA): AACR; Clin Cancer Res 2025;31(13_Suppl):Abstract nr A013.

## Scientific Elements
### Hardware / Physical System
- The AIRCHECK platform is an open, AI-ready resource that standardizes and shares DEL and ASMS datasets to facilitate robust, transparent, and accessible AI-driven hit discovery in drug development, demonstrated by successful virtual screening and experimental validation of novel compounds.
- Abstract Background: Efficient hit discovery is a critical step in drug development, traditionally achieved through high-throughput screening (HTS).
- Methods: To tackle the challenges of AI-based hit discovery, we present the Artificial Intelligence Ready CHEmiCal Knowledge-base (AIRCHECK), an open platform designed to make DEL and ASMS datasets accessible and AI-ready.
- Results: The AIRCHECK platform also offers baseline artificial intelligence models to support the virtual screening of chemical libraries for potential hits, with open-source codes available.

### Method
- The AIRCHECK platform is an open, AI-ready resource that standardizes and shares DEL and ASMS datasets to facilitate robust, transparent, and accessible AI-driven hit discovery in drug development, demonstrated by successful virtual screening and experimental validation of novel compounds.

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
- Biology
- Biochemistry

### Materials / Systems
- Not specified.

### Properties
- Not specified.

### Measurements
- From 48 top-ranked predictions tested experimentally, seven compounds were confirmed to have binding affinities.

### Conditions
- The current model is based on a proof-of-concept for fingerprint-based AI-driven hit discovery, implemented as an ensemble of three Light Gradient Boosting Machines (LGBMs), each trained on a different chemical fingerprint: FCFP4, AtomPair, and Topological Torsion.

### Mechanisms
- Not specified.

### Outcomes
- Therapeutics

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Biology
- Biochemistry
- Therapeutics

### Reasoning Motifs
- Not specified by cross-SDL extraction.

### General Principles
- Not specified by cross-SDL extraction.

## Failure Paths / Caveats
- No explicit failure path available in CSV/cross-SDL extraction.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `not available`
- Cross-SDL extraction quality: not available
- Notes: No additional notes.
