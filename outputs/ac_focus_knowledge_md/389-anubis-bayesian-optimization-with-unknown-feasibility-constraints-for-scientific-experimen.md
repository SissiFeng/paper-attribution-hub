# Anubis: Bayesian optimization with unknown feasibility constraints for scientific experimentation

## Metadata
- Paper ID: `acfocus_40c6a79482d0`
- Cross-SDL ID: `not matched`
- DOI: 10.1039/d5dd00018a
- URL: https://pubs.rsc.org/en/content/articlelanding/2025/dd/d5dd00018a
- Year: 2025
- Authors: R. J. Hickman; G. Tom; Y. Zou; M. Aldeghi; A. Aspuru-Guzik
- Venue: Digital Discovery
- Category: Journal Article
- Peer reviewed: Peer Reviewed
- AC members: Alán Aspuru-Guzik, Yu Zou
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance, AC Full Member
- Flags: acknowledges_ac=checked, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.67
- Missing: evidence, conditions, mechanisms, outcomes, cross_sdl_match
- Notes: No cross-SDL extraction matched this paper; fields are derived from CSV only.

## Source Summary
This work presents Anubis, a comprehensive benchmark and discussion of Bayesian optimization strategies for handling unknown constraints in self-driving laboratories, demonstrating that feasibility-aware approaches using variational Gaussian process classifiers outperform naive methods in autonomous scientific experimentation, with all strategies implemented in the open-source Atlas Python library.

## Abstract
Model-based optimization strategies, such as Bayesian optimization (BO), have been deployed across the natural sciences in design and discovery campaigns due to their sample efficiency and flexibility. The combination of such strategies with automated laboratory equipment and/or high-performance computing in a suggest-make-measure closed-loop constitutes a self-driving laboratory (SDL), which has been endorsed as a next-generation technology for autonomous scientific experimentation. Despite the promise of early SDL prototypes, a lack of flexible experiment planning algorithms prevents certain prevalent optimization problem types from being addressed. For instance, many experiment planning algorithms are unable to intelligently deal with failed measurements resulting from a priori unknown constraints on the parameter space. Such constraint functions are pervasive in chemistry and materials science research, stemming from unexpected equipment failures, failed/abandoned syntheses, or unstable molecules or materials. In Anubis, we provide a comprehensive discussion and benchmark of BO strategies to handle a priori unknown constraints, characterized by learning the constraint function on-the-fly using a variational Gaussian process classifier and combining its predictions with the typical BO regression surrogate to parameterize feasibility-aware acquisition functions. These acquisition functions balance sampling parameter space regions deemed to be promising in terms of optimization objectives with avoidance of regions predicted to be infeasible. In addition to benchmarking feasibility-aware acquisition functions on analytic optimization benchmark surfaces, we conduct two realistic optimization benchmarks derived from previously reported studies: inverse design of hybrid organic-inorganic halide perovskite materials with unknown stability constraints, and the design of BCR-Abl kinase inhibitors with unknown synthetic accessibility constraints. We deliver intuitive recommendations to readers on which strategies work best for various scenarios. Our results show that feasibility-aware strategies with balanced risk, on average, outperform commonly adopted naive strategies, producing more valid experiments and finding the optima at least as fast. In tasks with smaller regions of infeasibility, we find that naïve strategies can perform competitively. Overall, this work contributes to advancing the practicality and efficiency of autonomous experimentation in SDLs. All strategies introduced in this work are implemented as part of the open-source Atlas Python library.

## Scientific Elements
### Hardware / Physical System
- This work presents Anubis, a comprehensive benchmark and discussion of Bayesian optimization strategies for handling unknown constraints in self-driving laboratories, demonstrating that feasibility-aware approaches using variational Gaussian process classifiers outperform naive methods in autonomous scientific experimentation, with all strategies implemented in the open-source Atlas Python library.
- The combination of such strategies with automated laboratory equipment and/or high-performance computing in a suggest-make-measure closed-loop constitutes a self-driving laboratory (SDL), which has been endorsed as a next-generation technology for autonomous scientific experimentation.
- Overall, this work contributes to advancing the practicality and efficiency of autonomous experimentation in SDLs.

### Method
- This work presents Anubis, a comprehensive benchmark and discussion of Bayesian optimization strategies for handling unknown constraints in self-driving laboratories, demonstrating that feasibility-aware approaches using variational Gaussian process classifiers outperform naive methods in autonomous scientific experimentation, with all strategies implemented in the open-source Atlas Python library.

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
- Automation and Robotics
- Artificial Intelligence & Data Science
- Chemistry

### Materials / Systems
- Such constraint functions are pervasive in chemistry and materials science research, stemming from unexpected equipment failures, failed/abandoned syntheses, or unstable molecules or materials.
- In addition to benchmarking feasibility-aware acquisition functions on analytic optimization benchmark surfaces, we conduct two realistic optimization benchmarks derived from previously reported studies: inverse design of hybrid organic-inorganic halide perovskite materials with unknown stability constraints, and the design of BCR-Abl kinase inhibitors with unknown synthetic accessibility constraints.

### Properties
- In addition to benchmarking feasibility-aware acquisition functions on analytic optimization benchmark surfaces, we conduct two realistic optimization benchmarks derived from previously reported studies: inverse design of hybrid organic-inorganic halide perovskite materials with unknown stability constraints, and the design of BCR-Abl kinase inhibitors with unknown synthetic accessibility constraints.

### Measurements
- Anubis: Bayesian optimization with unknown feasibility constraints for scientific experimentation This work presents Anubis, a comprehensive benchmark and discussion of Bayesian optimization strategies for handling unknown constraints in self-driving laboratories, demonstrating that feasibility-aware approaches using variational Gaussian process classifiers outperform naive methods in autonomous scientific experimentation, with all strategies implemented in the open-source Atlas Python library.
- For instance, many experiment planning algorithms are unable to intelligently deal with failed measurements resulting from a priori unknown constraints on the parameter space.
- In Anubis, we provide a comprehensive discussion and benchmark of BO strategies to handle a priori unknown constraints, characterized by learning the constraint function on-the-fly using a variational Gaussian process classifier and combining its predictions with the typical BO regression surrogate to parameterize feasibility-aware acquisition functions.
- In addition to benchmarking feasibility-aware acquisition functions on analytic optimization benchmark surfaces, we conduct two realistic optimization benchmarks derived from previously reported studies: inverse design of hybrid organic-inorganic halide perovskite materials with unknown stability constraints, and the design of BCR-Abl kinase inhibitors with unknown synthetic accessibility constraints.

### Conditions
- Not specified.

### Mechanisms
- Not specified.

### Outcomes
- Not specified.

## Cross-SDL Transfer
### SDL / Domain Tags
- Automation and Robotics
- Artificial Intelligence & Data Science
- Chemistry

### Reasoning Motifs
- Not specified by cross-SDL extraction.

### General Principles
- Not specified by cross-SDL extraction.

## Failure Paths / Caveats
- No explicit failure path available in CSV/cross-SDL extraction.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `not available`
- Cross-SDL extraction quality: not available
- Notes: No additional notes.
