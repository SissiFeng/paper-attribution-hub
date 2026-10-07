from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from app.services.pdf_parser import (
    ParsedDocument,
    ParsedSection,
    PdfNeedsOcrError,
    convert_file_to_markdown,
    parse_any,
    parse_text_file,
    split_into_sections,
)

FULLTEXT_FIXTURES = Path(__file__).parent / "fixtures" / "fulltexts"


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
    sample = FULLTEXT_FIXTURES / "P001.txt"
    doc = parse_any(sample)
    types = {s.section_type for s in doc.sections}
    assert {"abstract", "methods", "acknowledgements"} <= types
    ack = next(s for s in doc.sections if s.section_type == "acknowledgements")
    assert "acceleration consortium" in ack.text.lower()
    assert doc.source == "txt"


def test_figure_captions_extracted(tmp_path: Path):
    sample = FULLTEXT_FIXTURES / "P001.txt"
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


def test_convert_file_to_markdown_uses_pdf_inspector_with_diagnostics(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setitem(
        sys.modules,
        "pdf_inspector",
        SimpleNamespace(
            process_pdf=lambda _path: SimpleNamespace(
                markdown="# Paper\n\nMethods\nConverted.",
                pdf_type="text_based",
                confidence=0.99,
                page_count=2,
                processing_time_ms=4,
                pages_needing_ocr=[],
                has_encoding_issues=False,
                is_complex_layout=True,
                pages_with_tables=[2],
                pages_with_columns=[1],
            )
        ),
    )
    sample = tmp_path / "paper.pdf"
    sample.write_bytes(b"%PDF-1.4 fake")

    markdown, backend, _, diagnostics = convert_file_to_markdown(sample)

    assert markdown == "# Paper\n\nMethods\nConverted."
    assert backend == "pdf-inspector"
    assert diagnostics == {
        "quality_status": "complete_text",
        "pdf_type": "text_based",
        "confidence": 0.99,
        "page_count": 2,
        "processing_time_ms": 4,
        "pages_needing_ocr": [],
        "has_encoding_issues": False,
        "is_complex_layout": True,
        "pages_with_tables": [2],
        "pages_with_columns": [1],
    }


def test_convert_file_to_markdown_falls_back_when_pdf_inspector_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    import app.services.pdf_parser as pdf_parser

    monkeypatch.setattr(
        pdf_parser,
        "_pdf_inspector_markdown",
        lambda _path: (_ for _ in ()).throw(RuntimeError("failed")),
    )
    monkeypatch.setattr(
        pdf_parser,
        "_markitdown_text",
        lambda _path: "# MarkItDown fallback",
    )
    sample = tmp_path / "paper.pdf"
    sample.write_bytes(b"%PDF-1.4 fake")

    markdown, backend, _, diagnostics = convert_file_to_markdown(sample)

    assert markdown == "# MarkItDown fallback"
    assert backend == "markitdown"
    assert diagnostics["quality_status"] == "unverified_fallback"


def test_convert_file_to_markdown_falls_back_to_rendered_pdf_sections(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    import app.services.pdf_parser as pdf_parser

    monkeypatch.setattr(
        pdf_parser,
        "_pdf_inspector_markdown",
        lambda _path: (_ for _ in ()).throw(RuntimeError("failed")),
    )
    monkeypatch.setattr(
        pdf_parser,
        "_markitdown_text",
        lambda _path: (_ for _ in ()).throw(RuntimeError("failed")),
    )
    monkeypatch.setattr(
        pdf_parser,
        "parse_pdf_as_document",
        lambda _path: ParsedDocument(
            title="Fallback Paper",
            sections=[
                ParsedSection(
                    section_type="methods",
                    title="Methods",
                    text="Fallback body.",
                )
            ],
            source="pymupdf",
        ),
    )
    sample = tmp_path / "paper.pdf"
    sample.write_bytes(b"%PDF-1.4 fake")

    markdown, backend, _, diagnostics = convert_file_to_markdown(sample)

    assert markdown == "# Fallback Paper\n\n## Methods\n\nFallback body."
    assert backend == "pymupdf"
    assert diagnostics["quality_status"] == "unverified_fallback"


def test_convert_file_to_markdown_fails_closed_when_ocr_is_required(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setitem(
        sys.modules,
        "pdf_inspector",
        SimpleNamespace(
            process_pdf=lambda _path: SimpleNamespace(
                markdown="# Partial text",
                pdf_type="mixed",
                confidence=0.95,
                page_count=3,
                processing_time_ms=3,
                pages_needing_ocr=[2],
                has_encoding_issues=False,
                is_complex_layout=False,
                pages_with_tables=[],
                pages_with_columns=[],
            )
        ),
    )
    sample = tmp_path / "paper.pdf"
    sample.write_bytes(b"%PDF-1.4 fake")

    with pytest.raises(ValueError, match="OCR-capable route"):
        convert_file_to_markdown(sample)


def test_convert_file_to_markdown_routes_ocr_to_docling(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    import app.services.pdf_parser as pdf_parser

    monkeypatch.setattr(
        pdf_parser,
        "_pdf_inspector_markdown",
        lambda _path: (_ for _ in ()).throw(
            PdfNeedsOcrError("OCR required")
        ),
    )
    monkeypatch.setattr(
        pdf_parser,
        "_docling_ocr_markdown",
        lambda _path: (
            "# OCR paper\n\nComplete full-page text.",
            {
                "quality_status": "complete_text",
                "ocr_applied": True,
                "ocr_engine": "rapidocr",
            },
        ),
    )
    sample = tmp_path / "paper.pdf"
    sample.write_bytes(b"%PDF-1.4 fake")

    markdown, backend, _, diagnostics = convert_file_to_markdown(
        sample,
        ocr_backend="docling",
    )

    assert markdown.startswith("# OCR paper")
    assert backend == "docling-rapidocr"
    assert diagnostics["quality_status"] == "complete_text"
    assert diagnostics["ocr_applied"] is True


def test_pdf_inspector_extracts_real_native_text_pdf(tmp_path: Path):
    import pymupdf

    sample = tmp_path / "native-text.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Native PDF Title", fontsize=18)
    page.insert_text((72, 110), "Methods", fontsize=14)
    page.insert_text(
        (72, 140),
        "Bayesian optimization selected experiments.",
        fontsize=11,
    )
    document.save(sample)
    document.close()

    markdown, backend, version, diagnostics = convert_file_to_markdown(sample)

    assert "Native PDF Title" in markdown
    assert "Bayesian optimization selected experiments." in markdown
    assert backend == "pdf-inspector"
    assert version == "0.2.6"
    assert diagnostics["quality_status"] == "complete_text"
    assert diagnostics["pages_needing_ocr"] == []


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
