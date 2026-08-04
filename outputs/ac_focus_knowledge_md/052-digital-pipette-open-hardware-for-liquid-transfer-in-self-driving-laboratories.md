# Digital pipette: open hardware for liquid transfer in self-driving laboratories

## Metadata
- Paper ID: `acfocus_7e86e74325e0`
- Cross-SDL ID: `acgold_5dab18deaebf`
- DOI: 10.1039/d3dd00115f
- URL: https://pubs.rsc.org/en/content/articlehtml/2023/dd/d3dd00115f
- Year: 2023
- Authors: Naruki Yoshikawa, Kourosh Darvish, Mohammad Ghazi Vakili, Animesh Garg and Alán Aspuru-Guzik
- Venue: Digital Discovery
- Category: Journal article
- Peer reviewed: Peer Reviewed
- AC members: Alán Aspuru-Guzik, Kourosh Darvish (Deactivated), Animesh Garg
- AC programs: AC PDF_Florian Shkurti_2022-23, Core Development Grants_Milica Radisic_2023-24
- AC membership status: AC Full Member, AC Governance, AC Trainee, AC Full Member
- Flags: acknowledges_ac=checked, highly_relevant=checked, high_impact=blank

## Validation
- Score: 0.94
- Missing: measurements
- Notes: No validation notes.

## Source Summary
Researchers have developed a low-cost, 3D-printed digital pipette specifically designed for robots in self-driving laboratories, enabling accurate and efficient liquid handling comparable to commercial devices, with assembly in just 10 minutes and a random error of only 0.2% for 10 mL volumes.

## Abstract
Self-driving laboratories are being investigated as a potential means to accelerate the material discovery process. Accurate liquid handling is an essential operation in the context of chemical laboratories, and consequently a self-driving laboratory will require robotic liquid handling and transfer. Although many pipettes are available for human scientists, robots cannot manipulate these pipettes due to the limitations of current robot gripper morphology. We propose an intuitive yet elegant design for a 3D-printed digital pipette designed for robots to carry out chemical experiments. It costs less than 200 USD, and the simple design with three parts enables a new user to assemble one in 10 minutes. We conducted a performance evaluation that closely followed ISO 8655-6. Our results show that robots with the digital pipette could conduct accurate liquid delivery with 0.2% random error for the nominal volume (10 mL). This performance is comparable to commercially available liquid handling devices, whose typical random errors are 0.3%.

## Scientific Elements
### Hardware / Physical System
- Researchers have developed a low-cost, 3D-printed digital pipette specifically designed for robots in self-driving laboratories, enabling accurate and efficient liquid handling comparable to commercial devices, with assembly in just 10 minutes and a random error of only 0.2% for 10 mL volumes.
- Accurate liquid handling is an essential operation in the context of chemical laboratories, and consequently a self-driving laboratory will require robotic liquid handling and transfer.
- Although many pipettes are available for human scientists, robots cannot manipulate these pipettes due to the limitations of current robot gripper morphology.
- We propose an intuitive yet elegant design for a 3D-printed digital pipette designed for robots to carry out chemical experiments.

### Method
- The new design incorporates a 3D-printed syringe compatible with commercial pipette tips, enabling the handling of multiple liquids without cross-contamination.

### Problem
- The initial version of the digital pipette lacked mechanisms to prevent cross-contamination when handling multiple liquids.

### Hypothesis
- An updated design of the digital pipette that allows robotic arms to exchange pipette tips will mitigate contamination risk.

### Evidence
- The digital pipette v2 achieved liquid handling accuracy within the permissible error range defined by ISO 8655-2, supporting a broader range of experiments involving multiple liquids.

### Conclusion
- The digital pipette v2 successfully enables robotic arms to handle multiple liquids without cross-contamination while maintaining accuracy as per international standards.

## Scientific Objects And Mechanisms
### Entities
- digital pipette v2
- 3D-printed syringe
- pipette tips
- linear actuator
- Arduino microcontroller

### Materials / Systems
- Self-driving laboratories are being investigated as a potential means to accelerate the material discovery process.

### Properties
- The digital pipette v2 achieved liquid handling accuracy within the permissible error range defined by ISO 8655-2, supporting a broader range of experiments involving multiple liquids.

### Measurements
- Not specified.

### Conditions
- Although many pipettes are available for human scientists, robots cannot manipulate these pipettes due to the limitations of current robot gripper morphology.

### Mechanisms
- attachment and detachment of pipette tips to prevent cross-contamination
- electrical control of the linear actuator for precise liquid handling
- force-feedback-based positioning system for accurate pipette tip alignment

### Outcomes
- handling multiple liquids without contamination
- precise liquid handling through electrical signals
- reduced calibration effort and improved positioning flexibility

## Cross-SDL Transfer
### SDL / Domain Tags
- Automation and Robotics
- Biology
- Chemistry

### Reasoning Motifs
- Modular Design → Flexibility
- Precision Control → Accuracy
- Feedback → Adaptation

### General Principles
- Control Through Constraints
- Multi-scale Coupling

## Failure Paths / Caveats
- success: Incorporating disposable pipette tips to prevent contamination Evidence: The new design enables the robot to handle multiple liquids without contamination, broadening the range of possible experiments.
- success: Using a force-feedback-based positioning system for attaching pipette tips Evidence: This system reduces the calibration effort and improves positioning flexibility.

## Extraction Provenance
- CSV source: `data/ac_publications_focused_grid_view.csv.gz`
- Cross-SDL reasoning JSON: `/Users/sissifeng/Downloads/cross-sdl_knowledge_transfer_engine/data/reasoning/acgold_5dab18deaebf.json`
- Cross-SDL extraction quality: 0.8
- Notes: The paper provides a clear structure of the problem, hypothesis, method, evidence, and conclusion. However, the reasoning behind the choice of specific technical solutions, such as the force-feedback-based positioning system, is not deeply explained, requiring some inference.
