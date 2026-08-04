# Training-Free Active Learning Framework in Materials Science with Large Language Models

## Metadata
- Paper ID: `acfocus_a6f1570b6cf6`
- Cross-SDL ID: `acgold_0e2801e64f6f`
- DOI: 10.48550/arxiv.2511.19730
- URL: https://arxiv.org/abs/2511.19730
- Year: 2025
- Authors: H. Wang; R. E. CastaÃ±eda; J. R. Werber; Y. Fehlis; E. Kim; J. Hattrick-Simpers
- Venue: arXiv
- Category: Preprint
- Peer reviewed: Non Peer Reviewed
- AC members: Jason Hattrick-Simpers
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.96
- Missing: conditions
- Notes: No validation notes.

## Source Summary
An LLM-based active learning framework (LLM-AL) outperforms traditional machine learning models by leveraging pretrained knowledge and flexible text-based inputs to efficiently and consistently prioritize experiments, reducing the number needed to find top candidates by over 70% across diverse materials science datasets and demonstrating broad generalizability and interpretability.

## Abstract
Active learning (AL) accelerates scientific discovery by prioritizing the most informative experiments, but traditional machine learning (ML) models used in AL suffer from cold-start limitations and domain-specific feature engineering, restricting their generalizability. Large language models (LLMs) offer a new paradigm by leveraging their pretrained knowledge and universal token-based representations to propose experiments directly from text-based descriptions. Here, we introduce an LLM-based active learning framework (LLM-AL) that operates in an iterative few-shot setting and benchmark it against conventional ML models across four diverse materials science datasets. We explored two prompting strategies: one using concise numerical inputs suited for datasets with more compositional and structured features, and another using expanded descriptive text suited for datasets with more experimental and procedural features to provide additional context. Across all datasets, LLM-AL could reduce the number of experiments needed to reach top-performing candidates by over 70% and consistently outperformed traditional ML models. We found that LLM-AL performs broader and more exploratory searches while still reaching the optima with fewer iterations. We further examined the stability boundaries of LLM-AL given the inherent non-determinism of LLMs and found its performance to be broadly consistent across runs, within the variability range typically observed for traditional ML approaches. These results demonstrate that LLM-AL can serve as a generalizable alternative to conventional AL pipelines for more efficient and interpretable experiment selection and potential LLM-driven autonomous discovery.

## Scientific Elements
### Hardware / Physical System
- These results demonstrate that LLM-AL can serve as a generalizable alternative to conventional AL pipelines for more efficient and interpretable experiment selection and potential LLM-driven autonomous discovery.

### Method
- Benchmarking LLM-based active learning framework (LLM-AL) against conventional machine learning models across four diverse materials science datasets

### Problem
- Accelerating scientific discovery in materials science by prioritizing the most informative experiments

### Hypothesis
- Large language models (LLMs) can effectively guide active learning (AL) in materials science by leveraging their pretrained knowledge and universal token-based representations

### Evidence
- LLM-AL reduced the number of experiments needed to reach top-performing candidates by over 70% and consistently outperformed traditional ML models

### Conclusion
- LLM-AL serves as a generalizable alternative to conventional AL pipelines for more efficient and interpretable experiment selection and potential LLM-driven autonomous discovery

## Scientific Objects And Mechanisms
### Entities
- Large language models (LLMs)
- Traditional machine learning models
- Materials science datasets (matbench_steels, P3HT/CNT, Perovskite, Membrane)

### Materials / Systems
- Materials science datasets (matbench_steels, P3HT/CNT, Perovskite, Membrane)
- Training-Free Active Learning Framework in Materials Science with Large Language Models An LLM-based active learning framework (LLM-AL) outperforms traditional machine learning models by leveraging pretrained knowledge and flexible text-based inputs to efficiently and consistently prioritize experiments, reducing the number needed to find top candidates by over 70% across diverse materials science datasets and demonstrating broad generalizability and interpretability.
- Here, we introduce an LLM-based active learning framework (LLM-AL) that operates in an iterative few-shot setting and benchmark it against conventional ML models across four diverse materials science datasets.
- Benchmarking LLM-based active learning framework (LLM-AL) against conventional machine learning models across four diverse materials science datasets LLM-AL reduced the number of experiments needed to reach top-performing candidates by over 70% and consistently outperformed traditional ML models Large language models (LLMs) Traditional machine learning models Materials science datasets (matbench_steels, P3HT/CNT, Perovskite, Membrane) LLM-AL achieves faster convergence and better generalization across diverse scientific domains Reduction in the number of experiments needed to identify optimal material candidates Enhanced data efficiency and interpretability in experimental decision making

### Properties
- We further examined the stability boundaries of LLM-AL given the inherent non-determinism of LLMs and found its performance to be broadly consistent across runs, within the variability range typically observed for traditional ML approaches.

### Measurements
- Here, we introduce an LLM-based active learning framework (LLM-AL) that operates in an iterative few-shot setting and benchmark it against conventional ML models across four diverse materials science datasets.
- Benchmarking LLM-based active learning framework (LLM-AL) against conventional machine learning models across four diverse materials science datasets LLM-AL reduced the number of experiments needed to reach top-performing candidates by over 70% and consistently outperformed traditional ML models Large language models (LLMs) Traditional machine learning models Materials science datasets (matbench_steels, P3HT/CNT, Perovskite, Membrane) LLM-AL achieves faster convergence and better generalization across diverse scientific domains Reduction in the number of experiments needed to identify optimal material candidates Enhanced data efficiency and interpretability in experimental decision making

### Conditions
- Not specified.

### Mechanisms
- Text-based representation and reasoning by LLMs
- Feature engineering and predictive modeling by traditional ML
- Few-shot learning and iterative experiment proposal by LLM-AL

### Outcomes
- LLM-AL achieves faster convergence and better generalization across diverse scientific domains
- Reduction in the number of experiments needed to identify optimal material candidates
- Enhanced data efficiency and interpretability in experimental decision making

## Cross-SDL Transfer
### SDL / Domain Tags
- Materials Science
- Artificial Intelligence & Data Science
- Sustainable Materials

### Reasoning Motifs
- Knowledge → Generalization
- Representation → Efficiency
- Iterative Improvement → Optimality

### General Principles
- Exploiting prior knowledge for efficient exploration
- Leveraging universal representations for cross-domain generalization
- Iterative refinement for optimal solution discovery

## Failure Paths / Caveats
- partial: Applying LLM-AL to datasets with high-dimensional compositional features (matbench_steels) Evidence: LLM-AL underperformed compared to traditional ML models, likely due to the complexity of descriptive text adding unnecessary details
- success: Applying LLM-AL to datasets with rich procedural context (Membrane) Evidence: LLM-AL demonstrated particularly strong performance, suggesting effective extraction of latent contextual information

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_0e2801e64f6f.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper provides a structured comparison of LLM-AL against traditional ML models, but some aspects of the reasoning, such as the exact mechanisms behind LLM-AL's performance, remain implicit and require further interpretation.
