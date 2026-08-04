---
type: method
name: GPT
category: large language model
aliases:
- GPT-3
- GPT-4
- ChatGPT
used_by_labs:
- aspuru-guzik-lab
- goldfarb-lab
- hein-lab
- moosavi-lab
- seferos-lab
paper_count: 33
stages:
  optimization: 4
  automation_orchestration: 4
  generative_design: 8
  characterization_analysis: 3
  data_extraction: 1
  property_prediction: 3
generated: '2026-06-11'
---

# GPT

- Type: method
- Category: [[wiki/concepts/large-language-model|Large Language Model]]
- Aliases: GPT-3, GPT-4, ChatGPT
- Papers: 33 (2021–2026)

## Labs

| Lab | First year | Papers |
| --- | --- | --- |
| [[wiki/labs/aspuru-guzik-lab|Alán Aspuru-Guzik Group]] | 2024 | 1 |
| [[wiki/labs/goldfarb-lab|Avi Goldfarb Group]] | 2023 | 1 |
| [[wiki/labs/hein-lab|Jason Hein Group]] | 2024 | 1 |
| [[wiki/labs/moosavi-lab|Mohamad Moosavi Group]] | 2024 | 1 |
| [[wiki/labs/seferos-lab|Dwight Seferos Group]] | 2026 | 1 |

## Stages

- Generative design: 8
- Automation & orchestration: 4
- Optimization: 4
- Characterization & analysis: 3
- Property prediction: 3
- Data extraction: 1

## Usage

- (2021): "PipeDream-2BW can accelerate the training of large GPT and BERT language models by up to 20× with similar final model accuracy."
- (2021, Optimization): "Scalable training of large models (like BERT and GPT-3) requires careful optimization rooted in model design, architecture, and system capabilities."
- [[wiki/labs/goldfarb-lab|Avi Goldfarb Group]] (2023): "We describe an approach that uses data from online job ads to rank emerging technologies on their GPT likelihood."
- (2023): "Using ChatGPT as an example, we present some limitations of this approach to dialogue systems."
- (2023, Automation & orchestration): "We show how the artificial intelligence (AI) language model ChatGPT can automatically formulate reaction arrays for these common reactions based on the literature corpus it was trained on."
- (2023, Automation & orchestration): "However, most existing social robotics platforms are operated based on embedded computers, which limits the robot’s capabilities to access advanced AI-based platforms available online and which are required for sophisticated physical human–robot inte"
- [[wiki/labs/moosavi-lab|Mohamad Moosavi Group]] (2024): "We studied the performance of fine-tuning three open-source LLMs (GPT-J-6B, Llama-3.1-8B, and Mistral-7B) for a range of different chemical questions."
- [[wiki/labs/aspuru-guzik-lab|Alán Aspuru-Guzik Group]] (2024, Generative design): "Here, we develop a transformer-based implementation, which we name the generative pre-trained transformer-based (GPT) quantum eigensolver (GPT-QE), leveraging both pre-training on existing datasets and training without any prior knowledge."
- [[wiki/labs/hein-lab|Jason Hein Group]] (2024): "Leveraging GPT-4 to transform chemistry from paper to practice"
- (2024, Generative design): "Two generative AI web applications, ChatGPT-4 (OpenAI) and Infranodus (Nodus Labs), were used to create knowledge graphs and perform text network analysis, including 3D visualization."
- (2024, Generative design): "Language models, such as the GPT models, offer promising applications in automating literature reviews, generating research hypotheses, and aiding in interpreting complex biological data."
- (2024, Characterization & analysis): "Against this backdrop, this paper presents a detailed comparative analysis of four different AI platforms, namely ChatGPT, Gemini, Blackbox, and Microsoft Copilot, in addressing key challenges within the realm of computer science, spanning natural la"
- (2024, Automation & orchestration): "This paper presents a design and implementation of the humanoid robotic platform Adam, consisting of a motorized human-like head with precise movements of the eyes, jaw, and neck, together with capabilities of face tracking and vocal conversation usi"
- (2024): "Additionally, we address gaps identified in generic chatbots like ChatGPT, such as partial profile consideration and inconsistent recommendations."
- (2024, Data extraction): "However, it is very much known, that ChatGPT and other like platforms, such as Llama, or large GNNs, suffer from a series of black-box drawbacks out of which the”factual accuracy”,”halucinations”,”overgeneralization” and others open loop LLMs were re"

## Adoption

- Origin: [[wiki/labs/goldfarb-lab|Avi Goldfarb Group]] (2023)
- [[wiki/labs/aspuru-guzik-lab|Alán Aspuru-Guzik Group]]: first mention 2024 (+1y)
- [[wiki/labs/hein-lab|Jason Hein Group]]: first mention 2024 (+1y)
- [[wiki/labs/moosavi-lab|Mohamad Moosavi Group]]: first mention 2024 (+1y)
- [[wiki/labs/seferos-lab|Dwight Seferos Group]]: first mention 2026 (+3y)

## Papers

- Memory-Efficient Pipeline-Parallel DNN Training (2021) — `EXCLUDE`
- 1-bit Adam: Communication Efficient Large-Scale Training with Adam's Convergence Speed (2021) — `EXCLUDE`
- Could machine learning be a general purpose technology? A comparison of emerging technologies using data from online job postings (2023) — labs: [[wiki/labs/goldfarb-lab|Avi Goldfarb Group]] — `RELATED_RELEVANT`
- Understanding computational dialogue understanding (2023) — `ADJACENT`
- Designing Chemical Reaction Arrays Using Phactor and ChatGPT (2023) — `UNCERTAIN`
- Revolutionizing Social Robotics: A Cloud-Based Framework for Enhancing the Intelligence and Autonomy of Social Robots † (2023) — `EXCLUDE`
- Assessment of fine-tuned large language models for real-world chemistry and material science applications (2024) — labs: [[wiki/labs/moosavi-lab|Mohamad Moosavi Group]] — `CORE_RELEVANT`
- The generative quantum eigensolver (GQE) and its application for ground state search (2024) — labs: [[wiki/labs/aspuru-guzik-lab|Alán Aspuru-Guzik Group]] — `CORE_RELEVANT`
- Leveraging GPT-4 to transform chemistry from paper to practice (2024) — labs: [[wiki/labs/hein-lab|Jason Hein Group]] — `CORE_RELEVANT`
- Generative AI-based knowledge graphs for the illustration and development of mHealth self-management content (2024) — `EXCLUDE`
- Computer-aided drug discovery: From traditional simulation methods to language models and quantum computing (2024) — `EXCLUDE`
- Performance Comparison of AI Platforms in Solving Computer Science Problems (2024) — `EXCLUDE`
- Design and Implementation of Adam: A Humanoid Robotic Head with Social Interaction Capabilities (2024) — `UNCERTAIN`
- University Recommendation System using Neural Collaborative Filtering (2024) — `ADJACENT`
- A Real Time Self-Generating Control for AI Platforms (2024) — `ADJACENT`
- Artificial Intelligence and the Transformation of Higher Education Institutions: A Systems Approach (2024) — `EXCLUDE`
- AI and Robotic Technology in Materials and Chemistry Research (2024) — `ADJACENT`
- ChatGPT Helped Me Build a Chemistry App, and Here’s How You Can Make One Also (2024) — `EXCLUDE`
- OCTOPUS: operation control system for task optimization and job parallelization via a user-optimal scheduler (2024) — `EXCLUDE`
- RLpMIEC: High-Affinity Peptide Generation Targeting Major Histocompatibility Complex-I Guided and Interpreted by Interaction Spectrum-Navigated Reinforcement Learning (2024) — `ADJACENT`
- ...and 13 more
