from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from app.services.pdf_parser import (
    ParsedDocument,
    ParsedSection,
    parse_any,
    parse_text_file,
    split_into_sections,
)


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


def test_parse_pdf_uses_markitdown_first(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    class FakeMarkItDown:
        def convert(self, path: str):
            return SimpleNamespace(
                text_content="""# Markdown PDF Title

Abstract
Converted abstract.

Methods
Converted methods.
"""
            )

    monkeypatch.setitem(
        sys.modules,
        "markitdown",
        SimpleNamespace(MarkItDown=FakeMarkItDown),
    )

    sample = tmp_path / "paper.pdf"
    sample.write_bytes(b"%PDF-1.4 fake")

    doc = parse_any(sample)

    assert doc.source == "markitdown"
    assert doc.title == "Markdown PDF Title"
    assert {s.section_type for s in doc.sections} >= {"abstract", "methods"}


def test_parse_docx_uses_markitdown(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    class FakeMarkItDown:
        def convert(self, path: str):
            return SimpleNamespace(
                text_content="""Document Title

Abstract
Converted docx abstract.
"""
            )

    monkeypatch.setitem(
        sys.modules,
        "markitdown",
        SimpleNamespace(MarkItDown=FakeMarkItDown),
    )

    sample = tmp_path / "paper.docx"
    sample.write_bytes(b"fake docx")

    doc = parse_any(sample)

    assert doc.source == "markitdown"
    assert doc.title == "Document Title"
    assert [s.section_type for s in doc.sections] == ["unknown", "abstract"]


def test_parse_pdf_falls_back_when_markitdown_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    class BrokenMarkItDown:
        def convert(self, path: str):
            raise RuntimeError("conversion failed")

    def fake_pymupdf(path: Path) -> ParsedDocument:
        return ParsedDocument(
            sections=[
                ParsedSection(
                    section_type="abstract",
                    title="Abstract",
                    text="Fallback.",
                )
            ],
            source="pymupdf",
        )

    from app.config import settings
    import app.services.pdf_parser as pdf_parser

    monkeypatch.setattr(settings, "grobid_url", "")
    monkeypatch.setitem(
        sys.modules,
        "markitdown",
        SimpleNamespace(MarkItDown=BrokenMarkItDown),
    )
    monkeypatch.setattr(pdf_parser, "parse_pdf_as_document", fake_pymupdf)

    sample = tmp_path / "paper.pdf"
    sample.write_bytes(b"%PDF-1.4 fake")

    doc = parse_any(sample)

    assert doc.source == "pymupdf"
    assert doc.sections[0].text == "Fallback."
