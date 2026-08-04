# Variational autoencoder for design of synthetic viral vector serotypes

## Metadata
- Paper ID: `acfocus_b1a12363f3ec`
- Cross-SDL ID: `not matched`
- DOI: 10.1038/s42256-023-00787-2
- URL: https://www.nature.com/articles/s42256-023-00787-2
- Year: 2024
- Authors: Lyu S, Sowlati-Hashjin S, Garton M
- Venue: Nature Machine Intelligence
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Michael Garton
- AC programs: Not specified
- AC membership status: AC Full Member
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=checked

## Validation
- Score: 0.44
- Missing: hardware, evidence, materials, measurements, conditions, mechanisms, outcomes, cross_sdl_match
- Notes: No cross-SDL extraction matched this paper; fields are derived from CSV only.; Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
ProteinVAE is a compact generative model that efficiently creates synthetic viral vector protein sequences—lacking pre-existing antibody epitopes—using limited data, potentially overcoming immune barriers in gene therapy and enabling the design of large, therapeutically valuable proteins.

## Abstract
Recent, rapid advances in deep generative models for protein design have focused on small proteins with lots of data. Such models perform poorly on large proteins with limited natural sequences, for instance, the capsid protein of adenoviruses and adeno-associated virus, which are common delivery vehicles for gene therapy. Generating synthetic viral vector serotypes could overcome the potent pre-existing immune responses that most gene therapy recipients exhibit—a consequence of previous environmental exposure. We present a variational autoencoder (ProteinVAE) that can generate synthetic viral vector serotypes without epitopes for pre-existing neutralizing antibodies. A pre-trained protein language model was incorporated into the encoder to improve data efficiency, and deconvolution-based upsampling was used for decoding to avoid degenerate repetition seen in long protein sequence generation. ProteinVAE is a compact generative model with just 12.4 million parameters and was efficiently trained on the limited natural sequences. Viral protein sequences generated were used to produce structures with thermodynamic stability and viral assembly capability indistinguishable from natural vector counterparts. ProteinVAE can be used to generate a broad range of synthetic serotype sequences without epitopes for pre-existing neutralizing antibodies in the human population, effectively addressing one of the major challenges of gene therapy. It could be used more broadly to generate different types of viral vector, and any large, therapeutically valuable proteins, where available data are sparse.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- ProteinVAE is a compact generative model that efficiently creates synthetic viral vector protein sequences—lacking pre-existing antibody epitopes—using limited data, potentially overcoming immune barriers in gene therapy and enabling the design of large, therapeutically valuable proteins.

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

### Materials / Systems
- Not specified.

### Properties
- Viral protein sequences generated were used to produce structures with thermodynamic stability and viral assembly capability indistinguishable from natural vector counterparts.

### Measurements
- Not specified.

### Conditions
- Not specified.

### Mechanisms
- Not specified.

### Outcomes
- Not specified.

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Biology

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
