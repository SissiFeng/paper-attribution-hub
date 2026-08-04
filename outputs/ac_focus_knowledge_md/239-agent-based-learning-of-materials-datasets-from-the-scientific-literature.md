# Agent-based learning of materials datasets from the scientific literature

## Metadata
- Paper ID: `acfocus_bfdc4bbaec3f`
- Cross-SDL ID: `acgold_8a45b7d7ea32`
- DOI: 10.1039/d4dd00252k
- URL: https://pubs.rsc.org/en/content/articlelanding/2024/dd/d4dd00252k
- Year: 2024
- Authors: Mehrad Ansari, Seyed Mohamad Moosavi
- Venue: Digital Discovery
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Mehrad Gholizadeh Ansari (Deactivated), Mohamad Moosavi
- AC programs: AC PDF_Mohamad Moosavi_2023-24
- AC membership status: AC Trainee, AC Full Member
- Flags: acknowledges_ac=checked, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.96
- Missing: conditions
- Notes: No validation notes.

## Source Summary
The development of Eunomia, an open-source chemist AI agent powered by large language models, enables autonomous extraction and structuring of materials science data from scientific literature, outperforming or matching state-of-the-art methods and simplifying dataset creation for materials discovery.

## Abstract
Advancements in machine learning and artificial intelligence are transforming the discovery of materials. While the vast corpus of scientific literature presents a valuable and rich resource of experimental data that can be used for training machine learning models, the availability and accessibility of these data remains a bottleneck. Accessing these data by manual dataset creation is limited due to issues in maintaining quality and consistency, scalability limitations, and the risk of human error and bias. Therefore, in this work, we develop a chemist AI agent, powered by large language models (LLMs), to overcome these limitations by autonomously creating structured datasets from natural language text, ranging from sentences and paragraphs to extensive scientific research articles and extract guidelines for designing materials with desired properties. Our chemist AI agent, Eunomia, can plan and execute actions by leveraging the existing knowledge from decades of scientific research articles, scientists, the Internet and other tools altogether. We benchmark the performance of our approach in three different information extraction tasks with various levels of complexity, including solid-state impurity doping, metal–organic framework (MOF) chemical formula, and property relationships. Our results demonstrate that our zero-shot agent, with the appropriate tools, is capable of attaining performance that is either superior or comparable to the state-of-the-art fine-tuned material information extraction methods. This approach simplifies compilation of machine learning-ready datasets for the applications of discovery of various materials, and significantly eases the accessibility of advanced natural language processing tools for novice users in natural language. The methodology in this work is developed as open-source software on https://github.com/AI4ChemS/Eunomia.

## Scientific Elements
### Hardware / Physical System
- The development of Eunomia, an open-source chemist AI agent powered by large language models, enables autonomous extraction and structuring of materials science data from scientific literature, outperforming or matching state-of-the-art methods and simplifying dataset creation for materials discovery.

### Method
- Development and benchmarking of a chemist AI agent, Eunomia, powered by large language models (LLMs), against state-of-the-art fine-tuned material information extraction methods.

### Problem
- The unstructured format of chemical knowledge in scientific literature hinders effective utilization for experimental design and comprehension of previous studies.

### Hypothesis
- An AI agent can autonomously create structured datasets from natural language text, extracting guidelines for designing materials with desired properties.

### Evidence
- Eunomia demonstrated superior or comparable performance to fine-tuned methods in information extraction tasks of varying complexity, including named entity recognition, relation extraction, and argument mining.

### Conclusion
- Eunomia simplifies the compilation of machine learning-ready datasets, enhancing accessibility of advanced natural language processing tools for novice users.

## Scientific Objects And Mechanisms
### Entities
- AI agent (Eunomia)
- Large language models (LLMs)
- Natural language text (sentences, paragraphs, articles)
- Structured datasets
- Materials properties (e.g., water stability)

### Materials / Systems
- Materials properties (e.g., water stability)
- Agent-based learning of materials datasets from the scientific literature The development of Eunomia, an open-source chemist AI agent powered by large language models, enables autonomous extraction and structuring of materials science data from scientific literature, outperforming or matching state-of-the-art methods and simplifying dataset creation for materials discovery.
- Advancements in machine learning and artificial intelligence are transforming the discovery of materials.
- Therefore, in this work, we develop a chemist AI agent, powered by large language models (LLMs), to overcome these limitations by autonomously creating structured datasets from natural language text, ranging from sentences and paragraphs to extensive scientific research articles and extract guidelines for designing materials with desired properties.

### Properties
- Therefore, in this work, we develop a chemist AI agent, powered by large language models (LLMs), to overcome these limitations by autonomously creating structured datasets from natural language text, ranging from sentences and paragraphs to extensive scientific research articles and extract guidelines for designing materials with desired properties.
- We benchmark the performance of our approach in three different information extraction tasks with various levels of complexity, including solid-state impurity doping, metal–organic framework (MOF) chemical formula, and property relationships.
- AI agent (Eunomia) Large language models (LLMs) Natural language text (sentences, paragraphs, articles) Structured datasets Materials properties (e.g., water stability) Creation of structured datasets from scientific literature Extraction of material design guidelines Reduction of human error and bias in dataset creation

### Measurements
- We benchmark the performance of our approach in three different information extraction tasks with various levels of complexity, including solid-state impurity doping, metal–organic framework (MOF) chemical formula, and property relationships.
- Development and benchmarking of a chemist AI agent, Eunomia, powered by large language models (LLMs), against state-of-the-art fine-tuned material information extraction methods.

### Conditions
- Not specified.

### Mechanisms
- Information extraction from unstructured text
- Entity recognition and relation extraction
- Zero-shot learning and natural language prompting
- Chain-of-verification for accuracy enhancement

### Outcomes
- Creation of structured datasets from scientific literature
- Extraction of material design guidelines
- Reduction of human error and bias in dataset creation

## Cross-SDL Transfer
### SDL / Domain Tags
- SDL 0 - AI & Automation
- Artificial Intelligence & Data Science
- Chemistry
- Materials Science

### Reasoning Motifs
- Information Extraction → Knowledge Structurization
- Entity Recognition → Data Enrichment
- Iterative Verification → Accuracy

### General Principles
- Data Transformation
- Pattern Recognition
- Quality Assurance

## Failure Paths / Caveats
- partial: Use of Eunomia without chain-of-verification tool for MOF formula and guest species identification. Evidence: Performance was superior for MOF formula extraction but had lower precision for guest species due to exact-word matching metrics.
- failure: Eunomia's initial confusion between water stability and thermal stability in materials research articles. Evidence: The agent initially misclassified a thermally stable MOF as water-stable, which was later corrected by the chain-of-verification process.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_8a45b7d7ea32.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper provides a clear structure for the development and benchmarking of the AI agent, Eunomia. However, some aspects of the reasoning, particularly around the iterative development and refinement of the agent's capabilities, are implicit rather than explicitly stated.
