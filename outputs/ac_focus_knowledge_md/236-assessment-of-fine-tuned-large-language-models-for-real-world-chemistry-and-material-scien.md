# Assessment of fine-tuned large language models for real-world chemistry and material science applications

## Metadata
- Paper ID: `acfocus_de3a046ef200`
- Cross-SDL ID: `acgold_16689e115340`
- DOI: 10.1039/d4sc04401k
- URL: https://pubs.rsc.org/en/content/articlelanding/2025/sc/d4sc04401k
- Year: 2024
- Authors: Van Herck J, Gil MV, Jablonka KM, Abrudan A, Anker AS, Asgari M, Blaiszik B, Buffo A, Choudhury L, Corminboeuf C, Daglar H, Elahi AM, Foster IT, Garcia S, Garvin M, Godin G, Good LL, Gu J, Xiao Hu N, Jin X, Junkers T, Keskin S, Knowles TPJ, Laplaza R, Lessona M, Majumdar S, Mashhadimoslem H, McIntosh RD, Moosavi SM, Mouriño B, Nerli F, Pevida C, Poudineh N, Rajabi-Kochi M, Saar KL, Hooriabad Saboor F, Sagharichiha M, Schmidt KJ, Shi J, Simone E, Svatunek D, Taddei M, Tetko I, Tolnai D, Vahdatifar S, Whitmer J, Wieland DCF, Willumeit-Römer R, Züttel A, Smit B
- Venue: Chemical Science
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Mohamad Moosavi
- AC programs: Not specified
- AC membership status: AC Full Member
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.9
- Missing: hardware
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
Fine-tuning open-source large language models with natural language data enables them to effectively predict chemical properties, often outperforming traditional machine learning models, and offers a straightforward, accessible approach for chemical research that can reduce unnecessary experiments and computations.

## Abstract
The current generation of large language models (LLMs) has limited chemical knowledge. Recently, it has been shown that these LLMs can learn and predict chemical properties through fine-tuning. Using natural language to train machine learning models opens doors to a wider chemical audience, as field-specific featurization techniques can be omitted. In this work, we explore the potential and limitations of this approach. We studied the performance of fine-tuning three open-source LLMs (GPT-J-6B, Llama-3.1-8B, and Mistral-7B) for a range of different chemical questions. We benchmark their performances against “traditional” machine learning models and find that, in most cases, the fine-tuning approach is superior for a simple classification problem. Depending on the size of the dataset and the type of questions, we also successfully address more sophisticated problems. The most important conclusions of this work are that, for all datasets considered, their conversion into an LLM fine-tuning training set is straightforward and that fine-tuning with even relatively small datasets leads to predictive models. These results suggest that the systematic use of LLMs to guide experiments and simulations will be a powerful technique in any research study, significantly reducing unnecessary experiments or computations.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- Benchmarking the performance of fine-tuned LLMs against traditional machine learning models using 22 datasets from various chemical domains.

### Problem
- Assessing the potential and limitations of fine-tuning large language models (LLMs) for real-world chemistry and material science applications.

### Hypothesis
- Fine-tuning LLMs can create predictive models for chemical properties and reactions without field-specific featurization.

### Evidence
- The fine-tuned LLMs demonstrated predictive performance in most cases, outperforming random guessing and often traditional ML models.

### Conclusion
- LLMs can be systematically used to guide experiments and simulations, reducing unnecessary computations and resources in chemical research.

## Scientific Objects And Mechanisms
### Entities
- Large language models (LLMs)
- Chemical properties
- Reaction outcomes
- Datasets from chemical domains

### Materials / Systems
- Assessment of fine-tuned large language models for real-world chemistry and material science applications Fine-tuning open-source large language models with natural language data enables them to effectively predict chemical properties, often outperforming traditional machine learning models, and offers a straightforward, accessible approach for chemical research that can reduce unnecessary experiments and computations.

### Properties
- Assessment of fine-tuned large language models for real-world chemistry and material science applications Fine-tuning open-source large language models with natural language data enables them to effectively predict chemical properties, often outperforming traditional machine learning models, and offers a straightforward, accessible approach for chemical research that can reduce unnecessary experiments and computations.
- Recently, it has been shown that these LLMs can learn and predict chemical properties through fine-tuning.
- Large language models (LLMs) Chemical properties Reaction outcomes Datasets from chemical domains Improved predictive performance in chemical property and reaction outcome prediction Reduction of computational and experimental resources in chemical research

### Measurements
- We benchmark their performances against “traditional” machine learning models and find that, in most cases, the fine-tuning approach is superior for a simple classification problem.
- Benchmarking the performance of fine-tuned LLMs against traditional machine learning models using 22 datasets from various chemical domains.

### Conditions
- The current generation of large language models (LLMs) has limited chemical knowledge.

### Mechanisms
- Fine-tuning LLMs on domain-specific datasets
- Predicting properties and outcomes from natural language inputs
- Benchmarking against traditional machine learning models

### Outcomes
- Improved predictive performance in chemical property and reaction outcome prediction
- Reduction of computational and experimental resources in chemical research

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Chemistry
- Materials Science

### Reasoning Motifs
- Data-driven improvement → Model accuracy
- Natural language interface → Accessibility
- Benchmarking → Model optimization

### General Principles
- Data Utilization
- Interface Accessibility
- Model Evaluation

## Failure Paths / Caveats
- failure: Predicting the success of MOF synthesis from experimental parameters. Evidence: The fine-tuned models could not recognize the prompt/completion structure and failed to output meaningful predictions.
- partial: Predicting the stability of gas sensors based on dopant material, dosage, and calcination temperature. Evidence: Achieved a predictive accuracy of 71% after optimizing hyperparameters, which was better than random guessing but not satisfactory.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_16689e115340.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper provides a structured exploration of LLMs in chemical applications, allowing for clear extraction of scientific reasoning. However, some details on the specific mechanisms and outcomes could be inferred rather than explicitly stated.
