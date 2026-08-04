# Machine learning enhanced expert system for detecting heart failure decompensation using patient reported vitals and electronic health records

## Metadata
- Paper ID: `acfocus_e921cdaf319d`
- Cross-SDL ID: `acgold_e497ad52b39d`
- DOI: 10.1038/s41598-025-16376-9
- URL: https://www.nature.com/articles/s41598-025-16376-9
- Year: 2025
- Authors: S. Saha; H. Ross; P. E. Velmovitsky; C. X. Wang; J. K. K. Vishram-Nielsen; C. Manlhiot; B. Wang; J. A. Cafazzo
- Venue: Scientific Reports
- Category: Journal Article
- Peer reviewed: Peer Reviewed
- AC members: Bo Wang
- AC programs: Not specified
- AC membership status: AC Full Member
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.87
- Missing: materials, measurements
- Notes: No validation notes.

## Source Summary
This study enhanced the Medly digital therapeutic for heart failure by integrating machine learning and electronic health record data, resulting in significantly improved accuracy and reduced false positives in predicting decompensation episodes compared to the original rules-based algorithm.

## Abstract
Heart failure (HF) is a condition with periods of stability interrupted by periods of worsening symptoms, known as decompensation episodes. Digital interventions are promising tools to alleviate burdens on HF management through automated alerts at the earliest decompensation sign. To accomplish this, our lab developed Medly, an expert system-enhanced digital therapeutic program for HF patients. Medly’s algorithm is a knowledge-based system that analyzes weight, blood pressure, and heart rate and sends automated alerts to clinicians and patients if deterioration is identified. Rules were set conservatively to account for false negatives. However, reducing false negatives resulted in an increase in false positives, which can lead to unnecessary clinical workload. Further, patients’ electronic health records (EHR) were not used when developing the rules-based algorithm. This study aimed to enhance Medly’s performance with machine learning and include a richer set of data, including EHR, for predicting decompensated HF episodes. We performed a retrospective study using XGBoost for the binary classification of whether the patient needed to be contacted for a possible decompensation episode. Features included blood pressure, weight change, heart rate, and EHR data (e.g., blood work, medication history). We further performed interpretability analysis to investigate the importance of including EHR data in the model. The enhanced algorithm achieved 98.08% accuracy, 95.26% sensitivity, 98.86% specificity, and a PPV of 88.18% – a marked improvement over the 55.8% in the rules-based algorithm. EHR data, mainly B-type natriuretic peptide (BNP) and total cholesterol, was crucial in predicting decompensation and correcting false-positive alerting. © The Author(s) 2025.

## Scientific Elements
### Hardware / Physical System
- Digital interventions are promising tools to alleviate burdens on HF management through automated alerts at the earliest decompensation sign.
- Medly’s algorithm is a knowledge-based system that analyzes weight, blood pressure, and heart rate and sends automated alerts to clinicians and patients if deterioration is identified.

### Method
- Retrospective study using XGBoost for binary classification of patient need for contact due to possible decompensation episode, with features including vitals and EHR data

### Problem
- Detecting heart failure decompensation using patient reported vitals and electronic health records

### Hypothesis
- A machine learning-enhanced expert system can improve prediction of heart failure decompensation episodes by integrating EHR data

### Evidence
- The enhanced algorithm achieved 98.08% accuracy, 95.26% sensitivity, 98.86% specificity, and a PPV of 88.18%, compared to 55.8% PPV in the rules-based algorithm

### Conclusion
- Incorporating EHR data into a machine learning-enhanced expert system improves prediction of heart failure decompensation episodes and reduces false positives

## Scientific Objects And Mechanisms
### Entities
- Weight change
- Blood pressure
- Heart rate
- B-type natriuretic peptide (BNP)
- Total cholesterol

### Materials / Systems
- Not specified.

### Properties
- Machine learning enhanced expert system for detecting heart failure decompensation using patient reported vitals and electronic health records This study enhanced the Medly digital therapeutic for heart failure by integrating machine learning and electronic health record data, resulting in significantly improved accuracy and reduced false positives in predicting decompensation episodes compared to the original rules-based algorithm.
- Heart failure (HF) is a condition with periods of stability interrupted by periods of worsening symptoms, known as decompensation episodes.
- The enhanced algorithm achieved 98.08% accuracy, 95.26% sensitivity, 98.86% specificity, and a PPV of 88.18% – a marked improvement over the 55.8% in the rules-based algorithm.
- Retrospective study using XGBoost for binary classification of patient need for contact due to possible decompensation episode, with features including vitals and EHR data The enhanced algorithm achieved 98.08% accuracy, 95.26% sensitivity, 98.86% specificity, and a PPV of 88.18%, compared to 55.8% PPV in the rules-based algorithm Weight change Blood pressure Heart rate B-type natriuretic peptide (BNP) Total cholesterol Improved prediction of decompensation episodes Reduction in false positive alerts

### Measurements
- Not specified.

### Conditions
- Heart failure (HF) is a condition with periods of stability interrupted by periods of worsening symptoms, known as decompensation episodes.
- Medly’s algorithm is a knowledge-based system that analyzes weight, blood pressure, and heart rate and sends automated alerts to clinicians and patients if deterioration is identified.
- Features included blood pressure, weight change, heart rate, and EHR data (e.g., blood work, medication history).
- Retrospective study using XGBoost for binary classification of patient need for contact due to possible decompensation episode, with features including vitals and EHR data The enhanced algorithm achieved 98.08% accuracy, 95.26% sensitivity, 98.86% specificity, and a PPV of 88.18%, compared to 55.8% PPV in the rules-based algorithm Weight change Blood pressure Heart rate B-type natriuretic peptide (BNP) Total cholesterol Improved prediction of decompensation episodes Reduction in false positive alerts

### Mechanisms
- Vital sign monitoring for early detection of decompensation
- Biomarker analysis for heart failure severity assessment

### Outcomes
- Improved prediction of decompensation episodes
- Reduction in false positive alerts

## Cross-SDL Transfer
### SDL / Domain Tags
- Not specified.

### Reasoning Motifs
- Data integration → Improved prediction
- Feature importance → Reduced false positives

### General Principles
- Information integration enhances predictive accuracy
- Feature selection optimizes model performance

## Failure Paths / Caveats
- success: Retrospective analysis of the original rules-based Medly algorithm Evidence: Achieved 93.6% accuracy but only 55.8% PPV, indicating high false positive rate
- success: Incorporation of EHR data into the XGBoost algorithm Evidence: Significantly improved PPV to 88.18% and reduced false positives

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_e497ad52b39d.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper provides a clear structure of the problem, hypothesis, method, results, and conclusions, facilitating the extraction process. However, some details on the specific steps of the machine learning model training and validation could be more explicit, which would enhance the extraction quality further.
