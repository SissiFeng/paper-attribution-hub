# A foundation model for atomistic materials chemistry

## Metadata
- Paper ID: `acfocus_ce537c4010ee`
- Cross-SDL ID: `not matched`
- DOI: 10.1063/5.0297006
- URL: https://watermark02.silverchair.com/184110_1_5.0297006.am.pdf?token=AQECAHi208BE49Ooan9kkhW_Ercy7Dm3ZL_9Cf3qfKAc485ysgAAAuAwggLcBgkqhkiG9w0BBwagggLNMIICyQIBADCCAsIGCSqGSIb3DQEHATAeBglghkgBZQMEAS4wEQQMhEttLy5j29Jhn00fAgEQgIICk8E2WQ7kSazGLqVCwu0P0gh-nBfKWB2GYL1lEQWHI27wI2EQNGlqWR83rGrcBDjHcBdvUzQKi3hKz795SarQ8Tpe4SRVVnun9ijcvFP6-y3D8rkC5hd0ccZWiYdpStBeEx-kg0LaRrg6oR0jhng7woT6XN3ThDwAhBr7l-tUWFi2Bb5_ihGktJ-1iggwmC8rgUHYoyUFK-8MVRRbwxbIPiubdpD7g5mCUG2ye_XCQ3xeXOicfhHtH-VCbjPfJL_bdNFSV0Nro7c5jguv7zMNy1_xoIXa5l6qsl5AsnuNiOcemG0CXb_mokP5LSACaBhbebphByyM59ADSGpJj5GJZvuICIyoF8rkWtsjWeXYsBSgllbFx5fvcOvPyAj_gRORvBS6BKDglEfZUi5Cn-9sr2XaQu0BAMB84ohQ60Laa0yHeqwp8iENn0ydDJD90nlkHNV5eLL3jqsaEYXmHquzJAHLqbUdoqXELuuRdDAhvKX8qfOaDj1r9kPcmdhjoELb7AZRWbLXS8djX0deE4pAqLf0pCnaGskO8Pow9JA75Esx1jRoVLJzEmqyTHXtny_koNI2dzli_NYHyd2IS1OIHI86FAvdTcRTaYpV9tPryzf8k2yB8xzyY4n1ar6Y7ovHp6j7IMFuu0rXYEdISvPVnDqPQyp30RSzUFil79gev2Xa4qgVmRZ3uSt-uYZ220jW31g9ABFpVvd6cg5pXKZSufzWol6_Cx1CcSlX2gVqmp7x_RxkOuzFdqrMzYD-IxCh77NH0ev9BzJA9cblejznlLH_O32j5HwW5Cq9YW7GdBWzb4ipjZZctt0HzPY7qqCzlzPgdRCSUzN4SSVYfRTMaZvany4HWwzZWV9mUu9VJReSTgYu
- Year: 2025
- Authors: I. Batatia; P. Benner; Y. Chiang; A. M. Elena; D. P. Kovács; J. Riebesell; X. R. Advincula; M. Asta; M. Avaylon; W. J. Baldwin; F. Berger; N. Bernstein; A. Bhowmik; F. Bigi; S. M. Blau; V. Cărare; M. Ceriotti; S. Chong; J. P. Darby; S. De; F. Della Pia; V. L. Deringer; R. Elijošius; Z. El-Machachi; E. Fako; F. Falcioni; A. C. A. C. Ferrari; J. L. A. Gardner; M. J. Gawkowski; A. Genreith-Schriever; J. George; R. E. A. Goodall; J. Grandel; C. P. Grey; P. Grigorev; S. Han; W. Handley; H. H. Heenen; K. Hermansson; C. H. Ho; S. Hofmann; C. Holm; J. Jaafar; K. S. Jakob; H. Jung; V. Kapil; A. D. Kaplan; N. Karimitari; J. R. Kermode; P. Kourtis; N. Kroupa; J. Kullgren; M. C. Kuner; D. Kuryla; G. Liepuoniute; C. Lin; J. T. Margraf; I. B. Magdău; A. Michaelides; J. H. Moore; A. A. Naik; S. P. Niblett; S. W. Norwood; N. O’Neill; C. Ortner; K. A. Persson; K. Reuter; A. S. Rosen; L. A. M. Rosset; L. L. Schaaf; C. Schran; B. X. Shi; E. Sivonxay; T. K. Stenczel; C. Sutton; V. Svahn; T. D. Swinburne; J. Tilly; C. van der Oord; S. Vargas; E. Varga-Umbrich; T. Vegge; M. Vondrák; Y. Wang; W. C. Witt; T. Wolf; F. Zills; G. Csányi
- Venue: Journal of Chemical Physics
- Category: Journal Article
- Peer reviewed: Peer Reviewed
- AC members: Chris Sutton
- AC programs: Not specified
- AC membership status: AC Full Member
- Flags: acknowledges_ac=blank, highly_relevant=checked, high_impact=checked

## Validation
- Score: 0.61
- Missing: hardware, evidence, mechanisms, outcomes, cross_sdl_match
- Notes: No cross-SDL extraction matched this paper; fields are derived from CSV only.; Full-text or LLM extraction is needed for reliable hardware/method coverage.

## Source Summary
A general-purpose machine-learned force field model, trained on a moderate public dataset, can accurately and stably simulate a wide range of molecules and materials, fundamentally advancing and democratizing atomistic modeling by reducing the effort and expertise required for high-quality simulations.

## Abstract
Atomistic simulations of matter, especially those that leverage first-principles (ab initio) electronic structure theory, provide a microscopic view of the world, underpinning much of our understanding of chemistry and materials science. Over the last decade or so, machine-learned force fields have transformed atomistic modeling by enabling simulations of ab initio quality over unprecedented time and length scales. However, early machine-learning (ML) force fields have largely been limited by (i) the substantial computational and human effort required to develop and validate potentials for each particular system of interest and (ii) a general lack of transferability from one chemical system to the next. Here, we show that it is possible to create a general-purpose atomistic ML model, trained on a public dataset of moderate size, that is capable of running stable molecular dynamics for a wide range of molecules and materials. We demonstrate the power of the MACE-MP-0 model—and its qualitative and at times quantitative accuracy—on a diverse set of problems in the physical sciences, including properties of solids, liquids, gases, chemical reactions, interfaces, and even the dynamics of a small protein. The model can be applied out of the box as a starting or “foundation” model for any atomistic system of interest and, when desired, can be fine-tuned on just a handful of application-specific data points to reach ab initio accuracy. Establishing that a stable force-field model can cover almost all materials changes atomistic modeling in a fundamental way: experienced users obtain reliable results much faster, and beginners face a lower barrier to entry. Foundation models thus represent a step toward democratizing the revolution in atomic-scale modeling that has been brought about by ML force fields. © 2025 Author(s).

## Scientific Elements
### Hardware / Physical System
- Not specified in the available CSV/cross-SDL text.

### Method
- A general-purpose machine-learned force field model, trained on a moderate public dataset, can accurately and stably simulate a wide range of molecules and materials, fundamentally advancing and democratizing atomistic modeling by reducing the effort and expertise required for high-quality simulations.

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
- Artificial Intelligence & Data Science
- Chemistry
- Materials Science

### Materials / Systems
- A foundation model for atomistic materials chemistry A general-purpose machine-learned force field model, trained on a moderate public dataset, can accurately and stably simulate a wide range of molecules and materials, fundamentally advancing and democratizing atomistic modeling by reducing the effort and expertise required for high-quality simulations.
- Atomistic simulations of matter, especially those that leverage first-principles (ab initio) electronic structure theory, provide a microscopic view of the world, underpinning much of our understanding of chemistry and materials science.
- Here, we show that it is possible to create a general-purpose atomistic ML model, trained on a public dataset of moderate size, that is capable of running stable molecular dynamics for a wide range of molecules and materials.

### Properties
- We demonstrate the power of the MACE-MP-0 model—and its qualitative and at times quantitative accuracy—on a diverse set of problems in the physical sciences, including properties of solids, liquids, gases, chemical reactions, interfaces, and even the dynamics of a small protein.
- The model can be applied out of the box as a starting or “foundation” model for any atomistic system of interest and, when desired, can be fine-tuned on just a handful of application-specific data points to reach ab initio accuracy.

### Measurements
- Atomistic simulations of matter, especially those that leverage first-principles (ab initio) electronic structure theory, provide a microscopic view of the world, underpinning much of our understanding of chemistry and materials science.

### Conditions
- Over the last decade or so, machine-learned force fields have transformed atomistic modeling by enabling simulations of ab initio quality over unprecedented time and length scales.

### Mechanisms
- Not specified.

### Outcomes
- Not specified.

## Cross-SDL Transfer
### SDL / Domain Tags
- Artificial Intelligence & Data Science
- Chemistry
- Materials Science

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
