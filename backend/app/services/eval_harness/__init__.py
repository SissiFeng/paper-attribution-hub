"""Evaluation harness: selective-classification metrics, section ablation, and
a natural-missingness benchmark.

Kept separate from the production scorer so the harness only *measures* the
classifier; it never changes how labels are produced.
"""
