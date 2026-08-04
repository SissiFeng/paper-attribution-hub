# Application of established computational techniques to identify potential SARS-CoV-2 Nsp14-MTase inhibitors in low data regimes

## Metadata
- Paper ID: `acfocus_c60b322ec003`
- Cross-SDL ID: `acgold_6effd6630f1e`
- DOI: 10.1039/d4dd00006d
- URL: https://pubs.rsc.org/en/content/articlelanding/2024/dd/d4dd00006d
- Year: 2024
- Authors: Nigam AK, Hurley MFD, Li F, Konkoľova E, Klima M, Trylcova J, Pollice R, Cinaroglu SS, Levin-Konigsberg R, Handjaya J, Schapira M, Chau I, Perveen S, Ng HL, Kaniskan HU, Han Y, Singh S, Gorgulla C, Kundaje A, Jin J, Voelz VA, Weber J, Nencka R, Boura E, Vedadi M, Aspuru-Guzik A
- Venue: Digital Discovery
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Alán Aspuru-Guzik
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=checked, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.84
- Missing: hardware, measurements
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
This study introduces a computational pipeline that rapidly identifies potential SARS-CoV-2 nsp14 inhibitors from the NCI compound collection, successfully discovering seven candidates—including one with strong binding affinity—and provides new structural insights into nsp14, culminating in the presentation of its crystal structure complexed with a potent inhibitor.

## Abstract
The COVID-19 pandemic, caused by the SARS-CoV-2 virus, has led to significant global morbidity and mortality. A crucial viral protein, the non-structural protein 14 (nsp14), catalyzes the methylation of viral RNA and plays a critical role in viral genome replication and transcription. Due to the low mutation rate in the nsp region among various SARS-CoV-2 variants, nsp14 has emerged as a promising therapeutic target. However, discovering potential inhibitors remains a challenge. In this work, we introduce a computational pipeline for the rapid and efficient identification of potential nsp14 inhibitors by leveraging virtual screening and the NCI open compound collection, which contains 250 000 freely available molecules for researchers worldwide. The introduced pipeline provides a cost-effective and efficient approach for early-stage drug discovery by allowing researchers to evaluate promising molecules without incurring synthesis expenses. Our pipeline successfully identified seven candidates that inhibit the MTase activity of nsp14. Among these, one compound, NSC62033, demonstrated strong binding affinity to nsp14, exhibiting a dissociation constant of 427 ± 84 nM. In addition, we gained new insights into the structure and function of this protein through molecular dynamics simulations. Furthermore, our molecular dynamics simulations suggest potential new conformational states of the protein, with residues Phe367, Tyr368, and Gln354 in the binding pocket potentially playing a role in stabilizing interactions with novel ligands, though further validation is required. Our findings also indicate that metal coordination complexes may be important for the function of the binding pocket. Lastly, we present the solved crystal structure of the nsp14-MTase complexed with SS148 (PDB:8BWU), a potent inhibitor of methyltransferase activity at the nanomolar level (IC50 value of 70 ± 6 nM).

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Virtual screening and molecular docking using the NCI open compound collection combined with molecular dynamics simulations

### Problem
- Discovering potential inhibitors for SARS-CoV-2 nsp14-MTase to combat COVID-19

### Hypothesis
- Computational screening can rapidly and efficiently identify potential nsp14 inhibitors from the NCI open compound collection

### Evidence
- Seven candidates were identified that inhibit MTase activity of nsp14, with NSC620333 showing the strongest binding affinity

### Conclusion
- The computational pipeline successfully identified potential nsp14 inhibitors, contributing to the development of antiviral therapies against SARS-CoV-2

## Scientific Objects And Mechanisms
### Entities
- SARS-CoV-2 nsp14 protein
- NCI open compound collection
- NSC620333 compound

### Materials / Systems
- SARS-CoV-2 nsp14 protein
- NCI open compound collection
- NSC620333 compound
- In this work, we introduce a computational pipeline for the rapid and efficient identification of potential nsp14 inhibitors by leveraging virtual screening and the NCI open compound collection, which contains 250 000 freely available molecules for researchers worldwide.
- The introduced pipeline provides a cost-effective and efficient approach for early-stage drug discovery by allowing researchers to evaluate promising molecules without incurring synthesis expenses.

### Properties
- Our pipeline successfully identified seven candidates that inhibit the MTase activity of nsp14.
- Lastly, we present the solved crystal structure of the nsp14-MTase complexed with SS148 (PDB:8BWU), a potent inhibitor of methyltransferase activity at the nanomolar level (IC50 value of 70 ± 6 nM).
- Virtual screening and molecular docking using the NCI open compound collection combined with molecular dynamics simulations Seven candidates were identified that inhibit MTase activity of nsp14, with NSC620333 showing the strongest binding affinity SARS-CoV-2 nsp14 protein NCI open compound collection NSC620333 compound Identification of potential nsp14 inhibitors Evaluation of binding affinities and inhibitory effects Insights into protein function and potential allosteric modulation

### Measurements
- Not specified.

### Conditions
- Due to the low mutation rate in the nsp region among various SARS-CoV-2 variants, nsp14 has emerged as a promising therapeutic target.

### Mechanisms
- Virtual screening to identify potential inhibitors
- Molecular docking to assess protein-ligand interactions
- Molecular dynamics simulations to study protein conformational dynamics

### Outcomes
- Identification of potential nsp14 inhibitors
- Evaluation of binding affinities and inhibitory effects
- Insights into protein function and potential allosteric modulation

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Biochemistry
- Therapeutics

### Reasoning Motifs
- Library Diversity → Hit Identification
- Binding Affinity → Inhibition Potential
- Protein Flexibility → Allosteric Regulation

### General Principles
- Screening Efficiency
- Binding Specificity
- Conformational Plasticity

## Failure Paths / Caveats
- success: Experimental testing of top 40 compounds identified through virtual screening Evidence: Seven compounds showed inhibitory properties, with NSC620333 and NSC76988 being the most promising
- partial: Surface plasmon resonance (SPR) assays for the top five compounds Evidence: NSC620333 showed strong binding affinity, while the others did not exhibit reliable SPR measurements

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_6effd6630f1e.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper provides a clear structure for the hypothesis, method, and results, but some of the underlying mechanisms and motifs had to be inferred from the described processes. The reasoning structure is well-organized, but the complexity of the system and the multiple layers of analysis make it challenging to distill into a few concise motifs and principles.
