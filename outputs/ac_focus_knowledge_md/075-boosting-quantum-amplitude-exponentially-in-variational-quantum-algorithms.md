# Boosting quantum amplitude exponentially in variational quantum algorithms

## Metadata
- Paper ID: `acfocus_11e5588c0e48`
- Cross-SDL ID: `acgold_edf3e094adcb`
- DOI: 10.1088/2058-9565/acf4ba
- URL: https://iopscience.iop.org/article/10.1088/2058-9565/acf4ba
- Year: 2024
- Authors: Kyaw TH, Soley MB, Allen B, Bergold P, Sun C, Batista VS, Aspuru-Guzik A
- Venue: Quantum Science and Technology
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Alán Aspuru-Guzik
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.53
- Missing: hardware, evidence, properties, measurements, mechanisms, outcomes
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
The authors introduce quantum iterative power algorithms (QIPAs), a new family of variational quantum algorithms that demonstrate superior performance over quantum imaginary time evolution (QITE) in global optimization tasks—including molecular ground state searches and factorization—by leveraging exponential amplitude amplification and requiring only a polynomial number of queries, thus offering a versatile framework for adapting classical optimization methods to near-term quantum computers.

## Abstract
We introduce a family of variational quantum algorithms, which we coin as quantum iterative power algorithms (QIPAs), and demonstrate their capabilities as applied to global-optimization numerical experiments. Specifically, we demonstrate the QIPA based on a double exponential oracle as applied to ground state optimization of the H 2 molecule, search for the transmon qubit ground-state, and biprime factorization. Our results indicate that QIPA outperforms quantum imaginary time evolution (QITE) and requires a polynomial number of queries to reach convergence even with exponentially small overlap between an initial quantum state and the final desired quantum state, under some circumstances. We analytically show that there exists an exponential amplitude amplification at every step of the variational quantum algorithm, provided the initial wavefunction has non-vanishing probability with the desired state and that the unique maximum of the oracle is given by λ 1 > 0 , while all other values are given by the same value 0 < λ 2 < λ 1 (here λ can be taken as eigenvalues of the problem Hamiltonian). The generality of the global-optimization method presented here invites further application to other problems that currently have not been explored with QITE-based near-term quantum computing algorithms. Such approaches could facilitate identification of reaction pathways and transition states in chemical physics, as well as optimization in a broad range of machine learning applications. The method also provides a general framework for adaptation of a class of classical optimization algorithms to quantum computers to further broaden the range of algorithms amenable to implementation on current noisy intermediate-scale quantum computers.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- The authors introduce quantum iterative power algorithms (QIPAs), a new family of variational quantum algorithms that demonstrate superior performance over quantum imaginary time evolution (QITE) in global optimization tasks—including molecular ground state searches and factorization—by leveraging exponential amplitude amplification and requiring only a polynomial number of queries, thus offering a versatile framework for adapting classical optimization methods to near-term quantum computers.

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
- Quantum

### Materials / Systems
- Specifically, we demonstrate the QIPA based on a double exponential oracle as applied to ground state optimization of the H 2 molecule, search for the transmon qubit ground-state, and biprime factorization.

### Properties
- Not specified.

### Measurements
- Not specified.

### Conditions
- Boosting quantum amplitude exponentially in variational quantum algorithms The authors introduce quantum iterative power algorithms (QIPAs), a new family of variational quantum algorithms that demonstrate superior performance over quantum imaginary time evolution (QITE) in global optimization tasks—including molecular ground state searches and factorization—by leveraging exponential amplitude amplification and requiring only a polynomial number of queries, thus offering a versatile framework for adapting classical optimization methods to near-term quantum computers.
- Our results indicate that QIPA outperforms quantum imaginary time evolution (QITE) and requires a polynomial number of queries to reach convergence even with exponentially small overlap between an initial quantum state and the final desired quantum state, under some circumstances.
- The method also provides a general framework for adaptation of a class of classical optimization algorithms to quantum computers to further broaden the range of algorithms amenable to implementation on current noisy intermediate-scale quantum computers.

### Mechanisms
- Not specified.

### Outcomes
- Not specified.

## Cross-SDL Transfer
### SDL / Domain Tags
- Quantum

### Reasoning Motifs
- Not specified by cross-SDL extraction.

### General Principles
- Not specified by cross-SDL extraction.

## Failure Paths / Caveats
- No explicit failure path available in CSV/cross-SDL extraction.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_edf3e094adcb.json`
- Cross-SDL extraction quality: 0.0
- Notes: Extraction failed — parse error: Expecting ',' delimiter: line 56 column 4 (char 2595)
