# Accelerated high-throughput imaging and phenotyping system for small organisms

## Metadata
- Paper ID: `acfocus_7e0391106169`
- Cross-SDL ID: `acgold_96a2e57fb2f9`
- DOI: 10.1371/journal.pone.0287739
- URL: https://dx.plos.org/10.1371/journal.pone.0287739
- Year: 2023
- Authors: Kose, Talha; Lins, Tiago F.; Wang, Jessie; O’Brien, Anna M.; Sinton, David; Frederickson, Megan E.
- Venue: PLOS ONE
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: David Sinton
- AC programs: Not specified
- AC membership status: AC Full Member, AC Governance
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.8
- Missing: materials, properties, measurements
- Notes: No validation notes.

## Source Summary
We developed an automated high-throughput experimentation system for duckweeds that enables large-scale, efficient studies of plant-microbe interactions, demonstrated by analyzing 6,000 experimental units across 2,000 treatments, and capable of scaling to 11,520 units for broader applications.

## Abstract
Studying the complex web of interactions in biological communities requires large multifactorial experiments with sufficient statistical power. Automation tools reduce the time and labor associated with setup, data collection, and analysis in experiments that untangle these webs. We developed tools for high-throughput experimentation (HTE) in duckweeds, small aquatic plants that are amenable to autonomous experimental preparation and image-based phenotyping. We showcase the abilities of our HTE system in a study with 6,000 experimental units grown across 2,000 treatments. These automated tools facilitated the collection and analysis of time-resolved growth data, which revealed finer dynamics of plant-microbe interactions across environmental gradients. Altogether, our HTE system can run experiments with up to 11,520 experimental units and can be adapted for other small organisms.

## Scientific Elements
### Hardware / Physical System
- We developed an automated high-throughput experimentation system for duckweeds that enables large-scale, efficient studies of plant-microbe interactions, demonstrated by analyzing 6,000 experimental units across 2,000 treatments, and capable of scaling to 11,520 units for broader applications.
- We developed tools for high-throughput experimentation (HTE) in duckweeds, small aquatic plants that are amenable to autonomous experimental preparation and image-based phenotyping.
- These automated tools facilitated the collection and analysis of time-resolved growth data, which revealed finer dynamics of plant-microbe interactions across environmental gradients.
- The researchers developed an automated system for high-throughput experimentation in duckweeds, integrating a liquid-handling robot for loading duckweeds into multi-well plates, an autonomous imaging system for time-resolved growth data, and a user interface for image-phenotyping.

### Method
- The researchers developed an automated system for high-throughput experimentation in duckweeds, integrating a liquid-handling robot for loading duckweeds into multi-well plates, an autonomous imaging system for time-resolved growth data, and a user interface for image-phenotyping.

### Problem
- The need for large multifactorial experiments with sufficient statistical power to study complex interactions in biological communities and the challenges in adapting existing experimentation methods to novel automated systems.

### Hypothesis
- The development of high-throughput experimentation (HTE) tools for small aquatic plants like duckweeds can facilitate autonomous experimental preparation and image-based phenotyping, allowing for large databases necessary for AI and ML.

### Evidence
- The HTE system successfully ran an experiment with 6,000 duckweed units across 2,000 treatments, capturing time-resolved growth data and revealing finer dynamics of plant-microbe interactions across environmental gradients.

### Conclusion
- The HTE system can run experiments with up to 11,520 experimental units and can be adapted for other small organisms, substantially advancing scientific research by enabling large-scale, multifactorial studies.

## Scientific Objects And Mechanisms
### Entities
- Duckweeds
- Liquid-handling robot
- Autonomous imaging system
- User interface for image-phenotyping

### Materials / Systems
- Not specified.

### Properties
- Not specified.

### Measurements
- Not specified.

### Conditions
- Automation tools reduce the time and labor associated with setup, data collection, and analysis in experiments that untangle these webs.
- These automated tools facilitated the collection and analysis of time-resolved growth data, which revealed finer dynamics of plant-microbe interactions across environmental gradients.
- The researchers developed an automated system for high-throughput experimentation in duckweeds, integrating a liquid-handling robot for loading duckweeds into multi-well plates, an autonomous imaging system for time-resolved growth data, and a user interface for image-phenotyping.
- The HTE system successfully ran an experiment with 6,000 duckweed units across 2,000 treatments, capturing time-resolved growth data and revealing finer dynamics of plant-microbe interactions across environmental gradients.
- Duckweeds Liquid-handling robot Autonomous imaging system User interface for image-phenotyping Reduction in manual labor and time for experimental setup Collection and analysis of large datasets for AI and ML training Enhanced understanding of complex interactions in biological communities

### Mechanisms
- Automated loading of duckweeds into multi-well plates
- Time-resolved growth data collection via automated imaging
- Image-phenotyping using color-thresholding

### Outcomes
- Reduction in manual labor and time for experimental setup
- Collection and analysis of large datasets for AI and ML training
- Enhanced understanding of complex interactions in biological communities

## Cross-SDL Transfer
### SDL / Domain Tags
- Biology
- Automation and Robotics
- Environmental Remediation

### Reasoning Motifs
- Automation → Efficiency
- Data Collection → Knowledge Generation
- Adaptability → Broad Applicability

### General Principles
- Enhanced Throughput Enables Complex Interaction Analysis
- Automation Reduces Human Error and Increases Reproducibility

## Failure Paths / Caveats
- success: The development of an automated duckweed loading system to reduce manual labor in HTE. Evidence: The system achieved an average fill rate of 75% and reduced the setup time significantly.
- success: The implementation of an autonomous imaging system to capture time-resolved growth data. Evidence: The system successfully tracked plant growth through time, capturing detailed growth dynamics.
- success: The use of a user interface for image-phenotyping to extract specific phenotypes. Evidence: The tool smoothly extracted data in most cases, with some optimization needed for color thresholding limits.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_96a2e57fb2f9.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper provides a clear structure of the problem, hypothesis, method, evidence, and conclusion, making the extraction process relatively straightforward. However, some details on the specific algorithms used for image-phenotyping and the exact nature of the optimizations would have improved the extraction quality.
