from pathlib import Path

from app.services.pdf_parser import parse_any, parse_text_file, split_into_sections


def test_split_detects_canonical_sections():
    text = """Title of paper

Abstract
Short abstract paragraph here.

Introduction
Some background on the topic.

Methods
We used a Bayesian optimization loop.

Results
Things worked.

Acknowledgements
Funded by the Acceleration Consortium and Vector Institute.

References
1. Foo, B. Bar 2024.
"""
    secs = split_into_sections(text)
    types = [s.section_type for s in secs]
    assert "abstract" in types
    assert "introduction" in types
    assert "methods" in types
    assert "results" in types
    assert "acknowledgements" in types
    assert "references" in types


def test_parse_text_file_reads_sample_p001(tmp_path: Path):
    sample = Path(__file__).resolve().parents[2] / "data" / "fulltexts" / "P001.txt"
    doc = parse_any(sample)
    types = {s.section_type for s in doc.sections}
    assert {"abstract", "methods", "acknowledgements"} <= types
    ack = next(s for s in doc.sections if s.section_type == "acknowledgements")
    assert "acceleration consortium" in ack.text.lower()
    assert doc.source == "txt"


def test_figure_captions_extracted(tmp_path: Path):
    sample = Path(__file__).resolve().parents[2] / "data" / "fulltexts" / "P001.txt"
    secs = parse_text_file(sample)
    figs = [s for s in secs if s.section_type == "figure_caption"]
    assert len(figs) >= 2
    assert any("autonomous" in f.text.lower() for f in figs)


def test_unknown_handles_front_matter():
    text = "Front matter\nMore front matter\n\nMethods\nMethod body."
    secs = split_into_sections(text)
    assert any(s.section_type == "unknown" for s in secs)
    assert any(s.section_type == "methods" for s in secs)
