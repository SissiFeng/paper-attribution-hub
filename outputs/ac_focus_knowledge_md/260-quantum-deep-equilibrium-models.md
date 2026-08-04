# Quantum Deep Equilibrium Models

## Metadata
- Paper ID: `acfocus_30120d51ebb3`
- Cross-SDL ID: `acgold_8519012fcd2f`
- DOI: 10.52202/079017-1004
- URL: https://proceedings.neurips.cc/paper_files/paper/2024/hash/386432c7534eec9a1cd7cbeea90d7e9f-Abstract-Conference.html
- Year: 2024
- Authors: Schleich P, Skreta M, Kristensen LB, Vargas-Hernández RA, Aspuru-Guzik A
- Venue: Advances in Neural Information Processing Systems
- Category: Conference
- Peer reviewed: Peer Reviewed
- AC members: Alán Aspuru-Guzik
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=checked

## Validation
- Score: 0.41
- Missing: hardware, evidence, entities, materials, properties, conditions, mechanisms, outcomes
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
This work introduces Quantum Deep Equilibrium Models (QDEQs), a novel training paradigm that leverages deep equilibrium models to optimize parametrized quantum circuits for quantum machine learning, enabling shallower circuits with competitive or superior performance compared to deeper networks, which is crucial for practical use on near-term quantum hardware.

## Abstract
The feasibility of variational quantum algorithms, the most popular correspondent of neural networks on noisy, near-term quantum hardware, is highly impacted by the circuit depth of the involved parametrized quantum circuits (PQCs). Higher depth increases expressivity, but also results in a detrimental accumulation of errors. Furthermore, the number of parameters involved in the PQC significantly influences the performance through the necessary number of measurements to evaluate gradients, which scales linearly with the number of parameters. Motivated by this, we look at deep equilibrium models (DEQs), which mimic an infinite-depth, weight-tied network using a fraction of the memory by employing a root solver to find the fixed points of the network. In this work, we present Quantum Deep Equilibrium Models (QDEQs): a training paradigm that learns parameters of a quantum machine learning model given by a PQC using DEQs. To our knowledge, no work has yet explored the application of DEQs to QML models. We apply QDEQs to find the parameters of a quantum circuit in two settings: the first involves classifying MNIST-4 digits with 4 qubits; the second extends it to 10 classes of MNIST, FashionMNIST and CIFAR. We find that QDEQ is not only competitive with comparable existing baseline models, but also achieves higher performance than a network with 5 times more layers. This demonstrates that the QDEQ paradigm can be used to develop significantly more shallow quantum circuits for a given task, something which is essential for the utility of near-term quantum computers. Our code is available at https://github.com/martaskrt/qdeq.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- This work introduces Quantum Deep Equilibrium Models (QDEQs), a novel training paradigm that leverages deep equilibrium models to optimize parametrized quantum circuits for quantum machine learning, enabling shallower circuits with competitive or superior performance compared to deeper networks, which is crucial for practical use on near-term quantum hardware.

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
- Not specified.

### Materials / Systems
- Not specified.

### Properties
- Not specified.

### Measurements
- Furthermore, the number of parameters involved in the PQC significantly influences the performance through the necessary number of measurements to evaluate gradients, which scales linearly with the number of parameters.

### Conditions
- Not specified.

### Mechanisms
- Not specified.

### Outcomes
- Not specified.

## Cross-SDL Transfer
### SDL / Domain Tags
- Not specified.

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
