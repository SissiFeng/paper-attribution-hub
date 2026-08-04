# A tomographic interpretation of structure-property relations for materials discovery

## Metadata
- Paper ID: `acfocus_5181563adecd`
- Cross-SDL ID: `acgold_b0257f02b8d4`
- DOI: 10.48550/arxiv.2501.18163
- URL: https://arxiv.org/abs/2501.18163
- Year: 2025
- Authors: R. Ortega-Ochoa; A. Aspuru-Guzik; T. Vegge; T. Buonassisi
- Venue: arxiv
- Category: Preprint
- Peer reviewed: Non Peer Reviewed
- AC members: Alán Aspuru-Guzik, Tonio Buonassisi
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance, AC Full Member
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.8
- Missing: hardware, measurements, conditions
- Notes: Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
Recent advancements in machine learning for materials show that simple representations like chemical formulas can sometimes predict properties as well as more complex models, prompting this work to propose an information-theoretic framework to better define and understand material representations, properties, and their relationships, which is validated through comprehensive comparisons of property-augmented representations.

## Abstract
Recent advancements in machine learning (ML) for materials have demonstrated that simple" materials representations (e.g., the chemical formula alone without structural information) can sometimes achieve competitive property prediction performance in common-tasks. Our physics-based intuition would suggest that such representations are "incomplete", which indicates a gap in our understanding. This work proposes a tomographic interpretation of structure-property relations of materials to bridge that gap by defining what is a material representation, material properties, the material and the relationships between these three concepts using ideas from information theory. We verify this framework performing an exhaustive comparison of property-augmented representations on a range of material's property prediction objectives, providing insight into how different properties can encode complementary information."

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- The authors propose a tomographic interpretation of structure-property relations of materials, defining material representations, material properties, and the material itself using ideas from information theory, and verify this framework by comparing property-augmented representations on a range of material's property prediction objectives.

### Problem
- The apparent conflict between physical intuition of what constitutes a 'good' material representation and how ML models achieve competitive performance with 'simple' representations in a range of tasks.

### Hypothesis
- The elemental composition and stoichiometry constrain the structure of a material, leading to a near one-to-one correspondence between chemical formula and structure in certain datasets, making the chemical formula sufficient for ML tasks.

### Evidence
- The heatmaps in Figures 4 and 5 illustrate the result of introducing different properties to augment the representation for a range of tasks, showing that including properties generally helped more for composition-restricted than for composition-structure, suggesting these properties encode valuable information for the target properties.

### Conclusion
- The framework sheds light on unexplained and 'surprising' commonly observed results, including the remarkable performance of 'simple' representations, and how ML representations can be augmented by including other related properties to improve predictive performance for some tasks.

## Scientific Objects And Mechanisms
### Entities
- material representation
- material property
- material essence
- mutual information
- partial information decomposition (PID)

### Materials / Systems
- material representation
- material property
- material essence
- A tomographic interpretation of structure-property relations for materials discovery Recent advancements in machine learning for materials show that simple representations like chemical formulas can sometimes predict properties as well as more complex models, prompting this work to propose an information-theoretic framework to better define and understand material representations, properties, and their relationships, which is validated through comprehensive comparisons of property-augmented representations.
- Recent advancements in machine learning (ML) for materials have demonstrated that simple" materials representations (e.g., the chemical formula alone without structural information) can sometimes achieve competitive property prediction performance in common-tasks.
- This work proposes a tomographic interpretation of structure-property relations of materials to bridge that gap by defining what is a material representation, material properties, the material and the relationships between these three concepts using ideas from information theory.

### Properties
- A tomographic interpretation of structure-property relations for materials discovery Recent advancements in machine learning for materials show that simple representations like chemical formulas can sometimes predict properties as well as more complex models, prompting this work to propose an information-theoretic framework to better define and understand material representations, properties, and their relationships, which is validated through comprehensive comparisons of property-augmented representations.
- Recent advancements in machine learning (ML) for materials have demonstrated that simple" materials representations (e.g., the chemical formula alone without structural information) can sometimes achieve competitive property prediction performance in common-tasks.
- This work proposes a tomographic interpretation of structure-property relations of materials to bridge that gap by defining what is a material representation, material properties, the material and the relationships between these three concepts using ideas from information theory.
- We verify this framework performing an exhaustive comparison of property-augmented representations on a range of material's property prediction objectives, providing insight into how different properties can encode complementary information." The authors propose a tomographic interpretation of structure-property relations of materials, defining material representations, material properties, and the material itself using ideas from information theory, and verify this framework by comparing property-augmented representations on a range of material's property prediction objectives.
- The heatmaps in Figures 4 and 5 illustrate the result of introducing different properties to augment the representation for a range of tasks, showing that including properties generally helped more for composition-restricted than for composition-structure, suggesting these properties encode valuable information for the target properties.

### Measurements
- Not specified.

### Conditions
- Not specified.

### Mechanisms
- information content of material representations
- information interactions between multiple variables
- encoding of complementary information in different material projections

### Outcomes
- improved understanding of why 'simple' ML representations perform well
- insight into how different properties can encode complementary information
- justification for augmenting ML representations with additional properties to improve performance on certain tasks

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Chemistry
- Materials Science

### Reasoning Motifs
- Constraint → Stability
- Diversity → Robustness
- Information Content → Predictive Performance

### General Principles
- Control Through Constraints
- Emergent Order

## Failure Paths / Caveats
- No explicit failure path available in CSV/cross-SDL extraction.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_b0257f02b8d4.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper presents a novel conceptual framework for understanding ML representations in materials science, but does not explicitly report any failed attempts or negative results. The reasoning structure had to be inferred from the paper's narrative, which is well-structured but somewhat implicit in its causal claims.
