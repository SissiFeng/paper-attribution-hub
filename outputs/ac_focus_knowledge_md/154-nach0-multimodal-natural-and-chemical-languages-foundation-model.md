# nach0: multimodal natural and chemical languages foundation model

## Metadata
- Paper ID: `acfocus_09fa4853cf0f`
- Cross-SDL ID: `acgold_27d0a79680ac`
- DOI: 10.1039/d4sc00966e
- URL: https://pubs.rsc.org/en/content/articlelanding/2024/sc/d4sc00966e
- Year: 2024
- Authors: Livne M, Miftahutdinov Z, Tutubalina E, Kuznetsov M, Polykovskiy D, Brundyn A, Jhunjhunwala A, Costa A, Aliper A, Aspuru-Guzik A, Zhavoronkov A
- Venue: Chemical Science
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Alán Aspuru-Guzik
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.86
- Missing: hardware, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
The paper presents nach0, a multi-domain, multi-task encoder-decoder large language model pre-trained on scientific texts and molecule strings, which, through instruction tuning and the NeMo framework, achieves state-of-the-art performance across various chemical and biological tasks, including molecular generation and biomedical question answering.

## Abstract
Large Language Models (LLMs) have substantially driven scientific progress in various domains, and many papers have demonstrated their ability to tackle complex problems with creative solutions. Our paper introduces a new foundation model, nach0, capable of solving various chemical and biological tasks: biomedical question answering, named entity recognition, molecular generation, molecular synthesis, attributes prediction, and others. nach0 is a multi-domain and multi-task encoder-decoder LLM pre-trained on unlabeled text from scientific literature, patents, and molecule strings to incorporate a range of chemical and linguistic knowledge. We employed instruction tuning, where specific task-related instructions are utilized to fine-tune nach0 for the final set of tasks. To train nach0 effectively, we leverage the NeMo framework, enabling efficient parallel optimization of both base and large model versions. Extensive experiments demonstrate that our model outperforms state-of-the-art baselines on single-domain and cross-domain tasks. Furthermore, it can generate high-quality outputs in molecular and textual formats, showcasing its effectiveness in multi-domain setups.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Pre-training the model 'nach0' on a diverse dataset comprising chemical SMILES data and textual data from scientific articles and patents, followed by fine-tuning on a variety of tasks using instruction tuning.

### Problem
- Developing a foundation model capable of solving various chemical and biological tasks including biomedical question answering, named entity recognition, molecular generation, molecular synthesis, attributes prediction, etc.

### Hypothesis
- A multi-domain and multi-task encoder-decoder Large Language Model (LLM) pre-trained on unlabeled text from scientific literature, patents, and molecule strings can incorporate a range of chemical and linguistic knowledge and perform well on diverse chemical and biological tasks.

### Evidence
- The model demonstrated superior performance over state-of-the-art baselines on both single-domain and cross-domain tasks as shown in extensive experiments and benchmark dataset evaluations.

### Conclusion
- The model 'nach0' is effective in handling multi-domain setups, showcasing its capabilities in translating between natural language and chemical language for various tasks in chemical research and drug design.

## Scientific Objects And Mechanisms
### Entities
- Large Language Model (LLM)
- Chemical SMILES data
- Textual data from scientific articles and patents

### Materials / Systems
- nach0: multimodal natural and chemical languages foundation model The paper presents nach0, a multi-domain, multi-task encoder-decoder large language model pre-trained on scientific texts and molecule strings, which, through instruction tuning and the NeMo framework, achieves state-of-the-art performance across various chemical and biological tasks, including molecular generation and biomedical question answering.
- nach0 is a multi-domain and multi-task encoder-decoder LLM pre-trained on unlabeled text from scientific literature, patents, and molecule strings to incorporate a range of chemical and linguistic knowledge.

### Properties
- Large Language Model (LLM) Chemical SMILES data Textual data from scientific articles and patents Improved performance on a range of chemical and biological tasks including NLP problems and molecular property prediction

### Measurements
- The model demonstrated superior performance over state-of-the-art baselines on both single-domain and cross-domain tasks as shown in extensive experiments and benchmark dataset evaluations.

### Conditions
- Not specified.

### Mechanisms
- Pre-training on unlabeled multi-domain data to incorporate chemical and linguistic knowledge
- Instruction tuning for fine-tuning the pre-trained model on specific tasks

### Outcomes
- Improved performance on a range of chemical and biological tasks including NLP problems and molecular property prediction

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Chemistry

### Reasoning Motifs
- Diverse Data Integration → Enhanced Model Generalization
- Task-specific Fine-tuning → Improved Performance

### General Principles
- Data-driven Model Enrichment
- Adaptability Through Modular Training

## Failure Paths / Caveats
- partial: Replacing all 42 generative models in Chemistry42 platform with nach0 for molecule generation. Evidence: Nach0 discovered 8 molecules satisfying all the 2D and 3D requirements within 45 minutes, although the quality was worse than 72-hour generations in Chemistry42.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_27d0a79680ac.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper provides a structured approach to introducing the model, its training, and evaluation. However, some inferences were necessary to fill in details regarding the underlying mechanisms and broader motifs due to the paper's focus on the model's application in chemical and biological tasks.
