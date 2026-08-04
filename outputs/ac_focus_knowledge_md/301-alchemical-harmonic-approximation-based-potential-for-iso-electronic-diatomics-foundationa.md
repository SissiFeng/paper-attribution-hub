# Alchemical harmonic approximation based potential for iso-electronic diatomics: Foundational baseline for Δ-machine learning

## Metadata
- Paper ID: `acfocus_5f61a78c3f67`
- Cross-SDL ID: `not matched`
- DOI: 10.1063/5.0241872
- URL: https://pubs.aip.org/aip/jcp/article/162/4/044101/3331936/Alchemical-harmonic-approximation-based-potential
- Year: 2025
- Authors: Krug S.L., Khan D., von Lilienfeld O.A.
- Venue: Journal of Chemical Physics
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Anatole von Lilienfeld
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=checked, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.44
- Missing: hardware, evidence, materials, measurements, conditions, mechanisms, outcomes, cross_sdl_match
- Notes: No cross-SDL extraction matched this paper; fields are derived from CSV only.; Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
The authors introduce the alchemical harmonic approximation (AHA) combined with a novel electronic binding potential ansatz to accurately predict absolute electronic energies of charge-neutral iso-electronic diatomics across varying distances, demonstrating superior predictive power and data efficiency compared to traditional interatomic potentials and baselines.

## Abstract
We introduce the alchemical harmonic approximation (AHA) of the absolute electronic energy for charge-neutral iso-electronic diatomics at fixed interatomic distance d0. To account for variations in distance, we combine AHA with this ansatz for the electronic binding potential, E ( d ) = ( E u − E s ) E c − E s E u − E s d / d 0 + E s , where Eu, Ec, Es correspond to the energies of the united atom, calibration at d0, and the sum of infinitely separated atoms, respectively. Our model covers the two-dimensional electronic potential energy surface spanned by distances of 0.7-2.5 Å and differences in nuclear charge from which only one single point (with elements of nuclear charge Z1, Z2, and distance d0) is drawn to calibrate Ec. Using reference data from pbe0/cc-pVDZ, we present numerical evidence for the electronic ground-state of all neutral diatomics with 8, 10, 12, and 14 electrons. We assess the validity of our model by comparison to legacy interatomic potentials (harmonic oscillator, Lennard-Jones, and Morse) within the most relevant range of binding (0.7-2.5 Å) and find comparable accuracy if restricted to single diatomics and significantly better predictive power when extrapolating to the entire iso-electronic series. We also investigated Δ-learning of the electronic absolute energy using our model as a baseline. This baseline model results in a systematic improvement, effectively reducing training data needed for reaching chemical accuracy by up to an order of magnitude from ∼1000 to ∼100. By contrast, using AHA+Morse as a baseline hardly leads to any improvement and sometimes even deteriorates the predictive power. Inferring the energy of unseen CO converges to a prediction error of ∼0.1 Ha in direct learning and ∼0.04 Ha with our baseline. © 2025 Author(s).

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- The authors introduce the alchemical harmonic approximation (AHA) combined with a novel electronic binding potential ansatz to accurately predict absolute electronic energies of charge-neutral iso-electronic diatomics across varying distances, demonstrating superior predictive power and data efficiency compared to traditional interatomic potentials and baselines.

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
- Not specified.

### Properties
- We introduce the alchemical harmonic approximation (AHA) of the absolute electronic energy for charge-neutral iso-electronic diatomics at fixed interatomic distance d0.
- Our model covers the two-dimensional electronic potential energy surface spanned by distances of 0.7-2.5 Å and differences in nuclear charge from which only one single point (with elements of nuclear charge Z1, Z2, and distance d0) is drawn to calibrate Ec.
- We assess the validity of our model by comparison to legacy interatomic potentials (harmonic oscillator, Lennard-Jones, and Morse) within the most relevant range of binding (0.7-2.5 Å) and find comparable accuracy if restricted to single diatomics and significantly better predictive power when extrapolating to the entire iso-electronic series.
- We also investigated Δ-learning of the electronic absolute energy using our model as a baseline.
- This baseline model results in a systematic improvement, effectively reducing training data needed for reaching chemical accuracy by up to an order of magnitude from ∼1000 to ∼100.

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
- Chemistry

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
