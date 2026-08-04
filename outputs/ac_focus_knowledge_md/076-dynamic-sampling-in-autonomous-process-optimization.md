# Dynamic sampling in autonomous process optimization

## Metadata
- Paper ID: `acfocus_afb5e9167b38`
- Cross-SDL ID: `acgold_f8bcbc240246`
- DOI: 10.1039/d3sc06884f
- URL: https://pubs.rsc.org/en/content/articlelanding/2024/sc/d3sc06884f
- Year: 2024
- Authors: Christensen M.; Xu Y.; Kwan E.E.; Di Maso M.J.; Ji Y.; Reibarkh M.; Sun A.C.; Liaw A.; Fier P.S.; Grosser S.; Hein J.E.
- Venue: Chemical Science
- Category: Article
- Peer reviewed: Peer Reviewed
- AC members: Jason Hein
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.79
- Missing: source_summary, materials, measurements
- Notes: No validation notes.

## Source Summary
Not specified in CSV.

## Abstract
Dynamic sampling in autonomous process
optimization†
Melodie Christensen,
*ab Yuting Xu,b Eugene E. Kwan,b Michael J. Di Maso,
b
Yining Ji,
b Mikhail Reibarkh,b Alexandra C. Sun,b Andy Liaw,b Patrick S. Fier,
b
Shane Grosser
b and Jason E. Hein
*acd
Autonomous process optimization (APO) is a technology that has recently found utility in a multitude of
process optimization challenges. In contrast to most APO examples in microﬂow reactor systems, we
recently presented a system capable of optimization in high-throughput batch reactor systems. The
drawback of APO in a high-throughput batch reactor system is the reliance on reaction sampling at
a predetermined static timepoint rather than a dynamic endpoint. Static timepoint sampling can lead to
the inconsistent capture of the process performance under each process parameter permutation. This is
important because critical process behaviors such as rate acceleration accompanied by decomposition
could be missed entirely. To address this drawback, we implemented a dynamic reaction endpoint
determination strategy to capture the product purity once the process stream stabilized. We
accomplished this through the incorporation of a real-time plateau detection algorithm into the APO
workﬂow to measure and report the product purity at the dynamically determined reaction endpoint. We
then applied this strategy to the autonomous optimization of a photobromination reaction towards the
synthesis of a pharmaceutically relevant intermediate. In doing so, we not only uncovered process
conditions to access the desired monohalogenation product in 85 UPLC area % purity with minimal
decomposition risk, but also measured the eﬀect of each parameter on the process performance. Our
results highlight the advantage of incorporating dynamic sampling in APO workﬂows to drive
optimization toward a stable and high-performing process.
Introduction
Articial
intelligence (AI)
has
multiple denitions, but
perhaps the most comprehensive description was 

## Scientific Elements
### Hardware / Physical System
- Incorporation of a real-time plateau detection algorithm into the APO workflow to measure and report the product purity at the dynamically determined reaction endpoint, applied to the autonomous optimization of a photobromination reaction.

### Method
- Incorporation of a real-time plateau detection algorithm into the APO workflow to measure and report the product purity at the dynamically determined reaction endpoint, applied to the autonomous optimization of a photobromination reaction.

### Problem
- The reliance on reaction sampling at a predetermined static timepoint rather than a dynamic endpoint in high-throughput batch reactor systems for autonomous process optimization (APO).

### Hypothesis
- Implementing a dynamic reaction endpoint determination strategy to capture the product purity once the process stream stabilized would improve APO.

### Evidence
- Uncovered process conditions to access the desired monohalogenation product in 85 UPLC area % purity with minimal decomposition risk, and measured the effect of each parameter on the process performance.

### Conclusion
- Incorporating dynamic sampling in APO workflows drives optimization toward a stable and high-performing process.

## Scientific Objects And Mechanisms
### Entities
- photobromination reaction
- real-time plateau detection algorithm
- product purity
- process stream stability

### Materials / Systems
- Not specified.

### Properties
- photobromination reaction real-time plateau detection algorithm product purity process stream stability improved process optimization accurate capture of process performance minimized decomposition risk

### Measurements
- Not specified.

### Conditions
- Dynamic sampling in autonomous process optimization Incorporation of a real-time plateau detection algorithm into the APO workflow to measure and report the product purity at the dynamically determined reaction endpoint, applied to the autonomous optimization of a photobromination reaction.
- Uncovered process conditions to access the desired monohalogenation product in 85 UPLC area % purity with minimal decomposition risk, and measured the effect of each parameter on the process performance.
- photobromination reaction real-time plateau detection algorithm product purity process stream stability improved process optimization accurate capture of process performance minimized decomposition risk

### Mechanisms
- dynamic reaction endpoint determination
- real-time plateau detection
- product purity measurement

### Outcomes
- improved process optimization
- accurate capture of process performance
- minimized decomposition risk

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Chemistry
- Chemical Engineering

### Reasoning Motifs
- Rate Acceleration → Decomposition Risk
- Stability → Process Performance
- Parameter Variation → Outcome Distribution

### General Principles
- Optimization Through Dynamic Endpoints
- Stability-Performance Tradeoff
- Multi-parametric Process Control

## Failure Paths / Caveats
- failure: Initial attempts at optimization without dynamic sampling, which led to inconsistent capture of process performance. Evidence: Static timepoint sampling could miss critical process behaviors such as rate acceleration accompanied by decomposition.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_f8bcbc240246.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper provides a clear structure for the problem, hypothesis, method, evidence, and conclusion, facilitating a reliable extraction. However, some inferences were necessary to fill in the reasoning structure, particularly in identifying the underlying mechanisms and outcomes without explicit statements in the paper.
