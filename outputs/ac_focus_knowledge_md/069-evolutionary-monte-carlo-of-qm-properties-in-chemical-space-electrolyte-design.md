# Evolutionary Monte Carlo of QM Properties in Chemical Space: Electrolyte Design

## Metadata
- Paper ID: `acfocus_7120149978ab`
- Cross-SDL ID: `acgold_1e9ddd3dc480`
- DOI: 10.1021/acs.jctc.3c00822
- URL: https://pubs.acs.org/doi/10.1021/acs.jctc.3c00822
- Year: 2023
- Authors: Karandashev, Konstantin; Weinreich, Jan; Heinen, Stefan; Arismendi Arrieta, Daniel Jose; von Rudorff, Guido Falk; Hermansson, Kersti; von Lilienfeld, O. Anatole
- Venue: Journal of Chemical Theory and Computation
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
Evolutionary Monte Carlo of QM properties in
chemical space: Electrolyte design
Konstantin Karandashev,∗,† Jan Weinreich,† Stefan Heinen,‡ Daniel Jose
Arismendi Arrieta,¶ Guido Falk von Rudorff,§,∥Kersti Hermansson,¶ and O.
Anatole von Lilienfeld‡,⊥,#
†University of Vienna, Faculty of Physics, Kolingasse 14-16, AT-1090 Wien, Austria
‡Vector Institute for Artificial Intelligence, Toronto, ON, M5S 1M1, Canada
¶Department of Chemistry-˚
Angstr¨om Laboratory, Uppsala University, Box 538, SE-75121
Uppsala, Sweden
§University Kassel, Department of Chemistry, Heinrich-Plett-Str.40, 34132 Kassel,
Germany
∥Center for Interdisciplinary Nanostructure Science and Technology (CINSaT),
Heinrich-Plett-Straße 40, 34132 Kassel
⊥Departments of Chemistry, Materials Science and Engineering, and Physics, University
of Toronto, St. George Campus, Toronto, ON, Canada
#Machine Learning Group, Technische Universit¨at Berlin and Institute for the
Foundations of Learning and Data, 10587 Berlin, Germany
E-mail: konstantin.karandashev@univie.ac.at
Abstract
Optimizing a target function over the space
of organic molecules is an important problem
appearing in many fields of applied science,
but also a very difficult one due to the vast
number of possible molecular systems.
We
propose an Evolutionary Monte Carlo algo-
rithm for solving such problems which is ca-
pable of straightforwardly tuning both explo-
ration and exploitation characteristics of an op-
timization procedure while retaining favourable
properties of genetic algorithms. The method,
dubbed MOSAiCS (Metropolis Optimization
by Sampling Adaptively in Chemical Space), is
tested on problems related to optimizing com-
ponents of battery electrolytes, namely mini-
mizing solvation energy in water or maximizing
dipole moment while enforcing a lower bound
on the HOMO-LUMO gap; optimization was
done over sets of molecular graphs inspired by
QM9 and Electrolyte Genome Project (EGP)
datasets. MOSAiCS reliably generated molec-
ular candidates wi

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Implementing an Evolutionary Monte Carlo algorithm named MOSAiCS to optimize components of battery electrolytes by minimizing solvation energy in water or maximizing dipole moment while enforcing a lower bound on the HOMO-LUMO gap

### Problem
- Optimizing target functions over chemical space for applications such as lithium battery electrolyte design

### Hypothesis
- An Evolutionary Monte Carlo algorithm can effectively optimize molecular properties within chemical space

### Evidence
- MOSAiCS reliably generated molecular candidates with good target quantity values, which were in most cases better than the ones found in QM9 or EGP

### Conclusion
- MOSAiCS is an effective algorithm for optimization in chemical space with potential applications in battery electrolyte design and other molecular optimization problems

## Scientific Objects And Mechanisms
### Entities
- Molecular graphs
- HOMO-LUMO gap
- Dipole moment
- Solvation energy

### Materials / Systems
- Evolutionary Monte Carlo of QM Properties in Chemical Space: Electrolyte Design Implementing an Evolutionary Monte Carlo algorithm named MOSAiCS to optimize components of battery electrolytes by minimizing solvation energy in water or maximizing dipole moment while enforcing a lower bound on the HOMO-LUMO gap MOSAiCS reliably generated molecular candidates with good target quantity values, which were in most cases better than the ones found in QM9 or EGP Molecular graphs HOMO-LUMO gap Dipole moment Solvation energy Optimized molecular candidates with improved target property values

### Properties
- Evolutionary Monte Carlo of QM Properties in Chemical Space: Electrolyte Design Implementing an Evolutionary Monte Carlo algorithm named MOSAiCS to optimize components of battery electrolytes by minimizing solvation energy in water or maximizing dipole moment while enforcing a lower bound on the HOMO-LUMO gap MOSAiCS reliably generated molecular candidates with good target quantity values, which were in most cases better than the ones found in QM9 or EGP Molecular graphs HOMO-LUMO gap Dipole moment Solvation energy Optimized molecular candidates with improved target property values

### Measurements
- Not specified.

### Conditions
- Not specified.

### Mechanisms
- Metropolis Optimization by Sampling Adaptively in Chemical Space (MOSAiCS)
- Markov chain Monte Carlo simulations
- Elementary mutations and crossover moves to propose new molecular configurations

### Outcomes
- Optimized molecular candidates with improved target property values

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Chemistry
- Clean energy

### Reasoning Motifs
- Diversity → Robustness
- Constraint → Stability
- Feedback → Adaptation

### General Principles
- Multi-scale Coupling
- Control Through Constraints

## Failure Paths / Caveats
- partial: Optimizing dipole moment under strong HOMO-LUMO gap constraint in QM9* Evidence: Simulations agreed less frequently on candidate molecules compared to other optimization problems
- success: Using non-zero αb to increase diversity of molecules encountered during simulations Evidence: Increasing αb tended to increase diversity of molecules encountered during the simulations, but this was mainly done by considering more molecules in regions of chemical space with larger values of solvation energy

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_1e9ddd3dc480.json`
- Cross-SDL extraction quality: 0.7
- Notes: The paper presents a structured approach to optimizing molecular properties using an Evolutionary Monte Carlo algorithm, but some details of the reasoning structure had to be inferred from the experimental setup and results discussion
