# Quantum Deep Equilibrium Models

## Metadata
- Paper ID: `acfocus_545c259fcd82`
- Cross-SDL ID: `acgold_8519012fcd2f`
- DOI: 10.48550/arxiv.2410.23940
- URL: https://arxiv.org/abs/2410.23940
- Year: 2024
- Authors: Schleich P, Skreta M, Kristensen LB, Vargas-Hernández RA, Aspuru-Guzik A
- Venue: arxiv
- Category: Preprint
- Peer reviewed: Non Peer Reviewed
- AC members: Alán Aspuru-Guzik
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.22
- Missing: source_summary, hardware, method, evidence, materials, properties, measurements, conditions, mechanisms, outcomes
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
Not specified in CSV.

## Abstract
Quantum Deep Equilibrium Models
Philipp Schleich∗
Department of Computer Science
University of Toronto
Vector Institute
philipps@cs.toronto.edu
Marta Skreta∗
Department of Computer Science
University of Toronto
Vector Institute
martaskreta@cs.toronto.edu
Lasse B. Kristensen
Department of Computer Science
University of Copenhagen
Rodrigo A. Vargas-Hernández
Department of Chemistry
& Chemical Biology
McMaster University, ON
Alán Aspuru-Guzik
Department of Computer Science
Department of Chemistry
University of Toronto
Vector Institute
Abstract
The feasibility of variational quantum algorithms, the most popular correspondent
of neural networks on noisy, near-term quantum hardware, is highly impacted by
the circuit depth of the involved parametrized quantum circuits (PQCs). Higher
depth increases expressivity, but also results in a detrimental accumulation of
errors. Furthermore, the number of parameters involved in the PQC significantly
influences the performance through the necessary number of measurements to
evaluate gradients, which scales linearly with the number of parameters. Motivated
by this, we look at deep equilibrium models (DEQs), which mimic an infinite-depth,
weight-tied network using a fraction of the memory by employing a root solver
to find the fixed points of the network. In this work, we present Quantum Deep
Equilibrium Models (QDEQs): a training paradigm that learns parameters of a
quantum machine learning model given by a PQC using DEQs. To our knowledge,
no work has yet explored the application of DEQs to QML models. We apply
QDEQs to find the parameters of a quantum circuit in two settings: the first involves
classifying MNIST-4 digits with 4 qubits; the second extends it to 10 classes of
MNIST, FashionMNIST and CIFAR. We find that QDEQ is not only competitive
with comparable existing baseline models, but also achieves higher performance
than a network with 5 times more layers. This demonstrates that the QDEQ
paradigm can be used to develop signif

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Not specified.

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
- Quantum

### Materials / Systems
- Not specified.

### Properties
- Not specified.

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
- Quantum

### Reasoning Motifs
- Not specified by cross-SDL extraction.

### General Principles
- Not specified by cross-SDL extraction.

## Failure Paths / Caveats
- No explicit failure path available in CSV/cross-SDL extraction.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_8519012fcd2f.json`
- Cross-SDL extraction quality: 0.0
- Notes: Extraction failed — parse error: Expecting ',' delimiter: line 51 column 4 (char 3199)
