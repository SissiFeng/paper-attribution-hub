# Evaluating the performance and robustness of LLMs in materials science Q&A and property predictions

## Metadata
- Paper ID: `acfocus_6c6699211f4b`
- Cross-SDL ID: `acgold_fb0d5a52678f`
- DOI: 10.1039/d5dd00090d
- URL: https://pubs.rsc.org/en/content/articlelanding/2025/dd/d5dd00090d
- Year: 2025
- Authors: H. Wang; K. Li; S. Ramsay; Y. Fehlis; E. Kim; J. Hattrick-Simpers
- Venue: Digital Discovery
- Category: Journal Article
- Peer reviewed: Peer Reviewed
- AC members: Jason Hattrick-Simpers
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=blank, high_impact=blank

## Validation
- Score: 0.9
- Missing: hardware
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
This study evaluates the performance and robustness of large language models in materials science by testing their ability to answer domain-specific questions and predict material properties under diverse real-world and adversarial conditions, highlighting both their potential and current limitations for practical scientific applications.

## Abstract
Large Language Models (LLMs) have the potential to revolutionize scientific research, yet their robustness and reliability in domain-specific applications remain insufficiently explored. In this study, we evaluate the performance and robustness of LLMs for materials science, focusing on domain-specific question answering and materials property prediction across diverse real-world and adversarial conditions. Three distinct datasets are used in this study: (1) a set of multiple-choice questions from undergraduate-level materials science courses, (2) a dataset including various steel compositions and yield strengths, and (3) a band gap dataset, containing textual descriptions of material crystal structures and band gap values. The performance of LLMs is assessed using various prompting strategies, including zero-shot chain-of-thought, expert prompting, and few-shot in-context learning. The robustness of these models is tested against various forms of “noise”, ranging from realistic disturbances to intentionally adversarial manipulations, to evaluate their resilience and reliability under real-world conditions. Additionally, the study showcases unique phenomena of LLMs during predictive tasks, such as mode collapse behavior when the proximity of prompt examples is altered and performance recovery from train/test mismatch. The findings aim to provide informed skepticism for the broad use of LLMs in materials science and to inspire advancements that enhance their robustness and reliability for practical applications.

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- The study evaluates LLMs using three distinct datasets: (1) multiple-choice questions from materials science courses, (2) steel compositions and yield strengths, and (3) material crystal structures and band gap values. Performance is assessed using prompting strategies like zero-shot chain-of-thought, expert prompting, and few-shot in-context learning.

### Problem
- Evaluating the performance and robustness of Large Language Models (LLMs) in materials science domain-specific question answering and materials property prediction.

### Hypothesis
- LLMs can be adapted to new tasks with few-shot examples via in-context learning, making them cost-effective and rapid to deploy. However, their robustness is a critical factor in practical deployment.

### Evidence
- Newer and larger models outperformed older models in domain-specific Q&A tasks. Prompt engineering improved performance on complex questions. Pretrained LLMs showed adaptability in property prediction using in-context learning, especially with highly proximate few-shot examples.

### Conclusion
- LLMs demonstrate potential as analytical tools in materials science, but their performance is task-dependent and challenged by complex and deceptive conditions. They show promise in low-data settings and active learning applications.

## Scientific Objects And Mechanisms
### Entities
- Large Language Models (LLMs)
- Materials science datasets
- Prompting strategies

### Materials / Systems
- Materials science datasets
- Evaluating the performance and robustness of LLMs in materials science Q&A and property predictions This study evaluates the performance and robustness of large language models in materials science by testing their ability to answer domain-specific questions and predict material properties under diverse real-world and adversarial conditions, highlighting both their potential and current limitations for practical scientific applications.
- In this study, we evaluate the performance and robustness of LLMs for materials science, focusing on domain-specific question answering and materials property prediction across diverse real-world and adversarial conditions.
- Three distinct datasets are used in this study: (1) a set of multiple-choice questions from undergraduate-level materials science courses, (2) a dataset including various steel compositions and yield strengths, and (3) a band gap dataset, containing textual descriptions of material crystal structures and band gap values.

### Properties
- Evaluating the performance and robustness of LLMs in materials science Q&A and property predictions This study evaluates the performance and robustness of large language models in materials science by testing their ability to answer domain-specific questions and predict material properties under diverse real-world and adversarial conditions, highlighting both their potential and current limitations for practical scientific applications.
- In this study, we evaluate the performance and robustness of LLMs for materials science, focusing on domain-specific question answering and materials property prediction across diverse real-world and adversarial conditions.
- Three distinct datasets are used in this study: (1) a set of multiple-choice questions from undergraduate-level materials science courses, (2) a dataset including various steel compositions and yield strengths, and (3) a band gap dataset, containing textual descriptions of material crystal structures and band gap values.
- The study evaluates LLMs using three distinct datasets: (1) multiple-choice questions from materials science courses, (2) steel compositions and yield strengths, and (3) material crystal structures and band gap values.
- Pretrained LLMs showed adaptability in property prediction using in-context learning, especially with highly proximate few-shot examples.

### Measurements
- The robustness of these models is tested against various forms of “noise”, ranging from realistic disturbances to intentionally adversarial manipulations, to evaluate their resilience and reliability under real-world conditions.

### Conditions
- Evaluating the performance and robustness of LLMs in materials science Q&A and property predictions This study evaluates the performance and robustness of large language models in materials science by testing their ability to answer domain-specific questions and predict material properties under diverse real-world and adversarial conditions, highlighting both their potential and current limitations for practical scientific applications.
- In this study, we evaluate the performance and robustness of LLMs for materials science, focusing on domain-specific question answering and materials property prediction across diverse real-world and adversarial conditions.
- The robustness of these models is tested against various forms of “noise”, ranging from realistic disturbances to intentionally adversarial manipulations, to evaluate their resilience and reliability under real-world conditions.

### Mechanisms
- In-context learning (ICL)
- Expert prompting
- Zero-shot chain-of-thought prompting

### Outcomes
- Enhanced performance in materials science Q&A and property prediction tasks
- Improved reasoning and answer accuracy
- Adaptability to new predictive challenges using ICL

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Materials Science

### Reasoning Motifs
- Data Proximity → Prediction Accuracy
- Prompt Quality → Model Performance
- Complexity → Robustness

### General Principles
- Adaptability Through Learning
- Information Relevance → Outcome Quality
- Simplicity in Complex Systems

## Failure Paths / Caveats
- partial: Using pretrained LLMs for property prediction with out-of-distribution data points. Evidence: Providing ineffective few-shot examples can cause the model to default to a memorized response rather than conditioning its output on the provided prompt.
- success: Assessing LLM performance under various forms of 'noise', including unit mixing, sentence reordering, synonym replacement, distractive info, and superfluous info. Evidence: LLMs showed resilience to certain types of noise but significant challenges under more complex and deceptive conditions.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_fb0d5a52678f.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper provides a structured evaluation of LLM performance and robustness in materials science applications, allowing for clear identification of scientific reasoning components. However, some aspects of the reasoning, particularly around model failures and limitations, required inference from the discussion of results.
