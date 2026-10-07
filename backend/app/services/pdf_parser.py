"""Parse PDFs (or .txt fall-backs) into structured sections.

The parser yields `ParsedDocument(title, abstract, authors, sections, references)`.
v0.2 uses PyMuPDF for PDFs and pure-Python regex section splitting.
v0.4 adds a GROBID adapter (see `grobid_adapter.py`) for higher-fidelity
sections, authors, and references when explicitly requested.
v0.9 adds pdf-inspector as the primary durable PDF-to-Markdown layer, with
quality diagnostics and fail-closed OCR routing. MarkItDown and PyMuPDF remain
fallbacks when the primary parser itself fails.

The `ParsedDocument` dataclass is the contract between parsers and the
ingestion pipeline. Any new backend (e.g. a Semantic Scholar API adapter)
only needs to emit the same shape.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import metadata
from pathlib import Path

# Section header keywords → canonical type.
# Patterns are anchored with `$` so they only match lines that ARE the heading,
# not lines that merely start with the heading word ("Methods" vs "Method body.").
# Trailing punctuation/whitespace and an optional numbering prefix are tolerated.
_TAIL = r"\s*[:.\-]?\s*$"
SECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "acknowledgements",
        re.compile(
            rf"^\s*(\d+[\.\)]?\s*)?(acknowledgements?|acknowledgments?|funding|funding sources?){_TAIL}",
            re.IGNORECASE,
        ),
    ),
    (
        "references",
        re.compile(
            rf"^\s*(\d+[\.\)]?\s*)?(references|bibliography){_TAIL}",
            re.IGNORECASE,
        ),
    ),
    (
        "supplementary",
        re.compile(
            rf"^\s*(\d+[\.\)]?\s*)?(supplementary( information| material| data)?|supporting information){_TAIL}",
            re.IGNORECASE,
        ),
    ),
    (
        "methods",
        re.compile(
            rf"^\s*(\d+[\.\)]?\s*)?(methods?|materials and methods|experimental( section)?){_TAIL}",
            re.IGNORECASE,
        ),
    ),
    (
        "results",
        re.compile(
            rf"^\s*(\d+[\.\)]?\s*)?(results( and discussion)?){_TAIL}",
            re.IGNORECASE,
        ),
    ),
    (
        "discussion",
        re.compile(
            rf"^\s*(\d+[\.\)]?\s*)?(discussion|conclusions?){_TAIL}",
            re.IGNORECASE,
        ),
    ),
    (
        "introduction",
        re.compile(
            rf"^\s*(\d+[\.\)]?\s*)?(introduction|background){_TAIL}",
            re.IGNORECASE,
        ),
    ),
    (
        "abstract",
        re.compile(
            rf"^\s*(\d+[\.\)]?\s*)?(abstract|summary){_TAIL}",
            re.IGNORECASE,
        ),
    ),
    (
        "figure_caption",
        re.compile(r"^\s*figure\s+\d+[\.:]\s", re.IGNORECASE),
    ),
]

SUPPORTED_FULLTEXT_SUFFIXES = {
    ".csv",
    ".docx",
    ".epub",
    ".htm",
    ".html",
    ".json",
    ".md",
    ".pdf",
    ".pptx",
    ".txt",
    ".xls",
    ".xlsx",
    ".xml",
}


@dataclass
class ParsedSection:
    section_type: str
    title: str | None
    text: str
    page_start: int | None = None
    page_end: int | None = None


@dataclass
class ParsedAuthor:
    name: str
    orcid: str | None = None
    affiliations: list[str] = field(default_factory=list)


@dataclass
class ParsedReferenceRecord:
    raw_text: str
    doi: str | None = None
    title: str | None = None
    authors: list[str] = field(default_factory=list)
    year: int | None = None


@dataclass
class ParsedDocument:
    """Backend-agnostic representation of a parsed paper."""

    sections: list[ParsedSection] = field(default_factory=list)
    title: str | None = None
    abstract: str | None = None
    authors: list[ParsedAuthor] = field(default_factory=list)
    affiliations: list[str] = field(default_factory=list)
    references: list[ParsedReferenceRecord] = field(default_factory=list)
    source: str = "txt"  # "grobid" / "pymupdf" / "txt"


def _classify_heading(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or len(stripped) > 80:
        return None
    # Figure captions are detected separately — they can be longer than a heading.
    if SECTION_PATTERNS[-1][1].match(stripped):
        return SECTION_PATTERNS[-1][0]
    # For all other section headers, require the line be ~just the heading
    # (≤6 words), to avoid misclassifying body lines that start with "Methods…".
    if len(stripped.split()) > 6:
        return None
    for label, pattern in SECTION_PATTERNS[:-1]:
        if pattern.match(stripped):
            return label
    return None


def split_into_sections(text: str) -> list[ParsedSection]:
    """Walk a plain-text full paper and split into sections by header heuristics.

    Anything before the first detected header is filed under `unknown` so the
    paper title / front matter still get indexed.
    """
    lines = text.splitlines()
    sections: list[ParsedSection] = []

    current_type = "unknown"
    current_title: str | None = None
    current_buf: list[str] = []

    def flush():
        if current_buf:
            joined = "\n".join(current_buf).strip()
            if joined:
                sections.append(
                    ParsedSection(
                        section_type=current_type,
                        title=current_title,
                        text=joined,
                    )
                )

    for line in lines:
        heading = _classify_heading(line)
        if heading is not None:
            flush()
            current_type = heading
            current_title = line.strip()
            # Figure caption "headings" are usually self-contained ("Figure 2. …"),
            # so the heading line is also its body. For other section types the
            # heading line is a label only.
            current_buf = [line] if heading == "figure_caption" else []
            continue
        current_buf.append(line)
    flush()

    # Figure captions inside other sections: split them out as siblings.
    expanded: list[ParsedSection] = []
    for sec in sections:
        if sec.section_type == "figure_caption":
            expanded.append(sec)
            continue
        chunks = _split_figure_captions(sec.text)
        if len(chunks) == 1:
            expanded.append(sec)
            continue
        body, captions = chunks[0], chunks[1:]
        if body.strip():
            expanded.append(
                ParsedSection(
                    section_type=sec.section_type,
                    title=sec.title,
                    text=body.strip(),
                    page_start=sec.page_start,
                    page_end=sec.page_end,
                )
            )
        for cap in captions:
            expanded.append(
                ParsedSection(section_type="figure_caption", title=None, text=cap.strip())
            )
    return expanded


_FIG_CAP_RE = re.compile(
    r"(?im)(^|\n)(figure\s+\d+[\.:]\s+[^\n]{5,400}(?:\n[^\n]{0,400})?)"
)


def _split_figure_captions(text: str) -> list[str]:
    parts: list[str] = []
    cursor = 0
    for m in _FIG_CAP_RE.finditer(text):
        start = m.start(2)
        end = m.end(2)
        if start > cursor:
            parts.append(text[cursor:start])
        parts.append(text[start:end])
        cursor = end
    parts.append(text[cursor:])
    return [p for p in parts if p.strip()]


def parse_text_file(path: Path) -> list[ParsedSection]:
    raw = Path(path).read_text(encoding="utf-8")
    return split_into_sections(raw)


def parse_text_file_as_document(path: Path) -> ParsedDocument:
    """Wrap the text-file path in a ParsedDocument so callers can treat all
    sources uniformly. References / authors stay empty here; downstream code
    falls back to the regex reference parser when needed."""
    sections = parse_text_file(path)
    abstract = next(
        (s.text for s in sections if s.section_type == "abstract"), None
    )
    # Heuristic: first non-empty line of the file as the title.
    title = None
    raw_first = Path(path).read_text(encoding="utf-8").splitlines()
    for line in raw_first[:20]:
        if line.strip():
            title = line.strip()
            break
    return ParsedDocument(
        sections=sections,
        title=title,
        abstract=abstract,
        source="txt",
    )


def parse_pdf(path: Path) -> list[ParsedSection]:
    """Parse a PDF via PyMuPDF. Imported lazily so the dep is optional."""
    try:
        import pymupdf  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "PyMuPDF is required for PDF parsing. `pip install pymupdf` "
            "or feed the system a .txt full text instead."
        ) from e

    doc = pymupdf.open(path)
    try:
        # Build a flat text stream with page markers so we can backfill page_start/end.
        page_texts: list[str] = []
        for page in doc:
            page_texts.append(page.get_text("text"))
        full_text = "\n".join(page_texts)
        sections = split_into_sections(full_text)
    finally:
        doc.close()

    # Best-effort page attribution: locate each section's text in the original
    # page sequence. Cheap and approximate but enough for v0.2.
    offsets: list[tuple[int, int]] = []
    cursor = 0
    for pt in page_texts:
        offsets.append((cursor, cursor + len(pt)))
        cursor += len(pt) + 1

    flat_lookup = full_text
    for sec in sections:
        idx = flat_lookup.find(sec.text[:80])
        if idx < 0:
            continue
        end_idx = idx + len(sec.text)
        for page_num, (start, stop) in enumerate(offsets, start=1):
            if start <= idx <= stop and sec.page_start is None:
                sec.page_start = page_num
            if start <= end_idx <= stop:
                sec.page_end = page_num
        if sec.page_end is None:
            sec.page_end = sec.page_start
    return sections


def parse_pdf_as_document(path: Path) -> ParsedDocument:
    """Pure PyMuPDF path. Used directly by tests and as the fallback when
    GROBID is unreachable."""
    sections = parse_pdf(path)
    return ParsedDocument(sections=sections, source="pymupdf")


def _markitdown_text(path: Path) -> str:
    """Return MarkItDown's normalized Markdown without persisting the source file."""
    try:
        from markitdown import MarkItDown  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "MarkItDown is required for Markdown-first PDF parsing. "
            "`pip install markitdown` or use the PyMuPDF fallback."
        ) from e

    converter = MarkItDown()
    convert = getattr(converter, "convert_local", converter.convert)
    result = convert(str(path))
    markdown = getattr(result, "text_content", None)
    if markdown is None:
        markdown = getattr(result, "markdown", None)
    if markdown is None:
        markdown = str(result)
    return markdown.strip()


class PdfNeedsOcrError(ValueError):
    """Raised when local text extraction cannot represent every PDF page."""


@lru_cache(maxsize=1)
def _docling_ocr_converter():
    """Build one reusable full-page RapidOCR converter for batch work."""
    try:
        from docling.datamodel.base_models import InputFormat  # type: ignore
        from docling.datamodel.pipeline_options import (  # type: ignore
            OcrMode,
            PdfPipelineOptions,
            RapidOcrOptions,
        )
        from docling.document_converter import (  # type: ignore
            DocumentConverter,
            PdfFormatOption,
        )
    except ImportError as exc:
        raise RuntimeError(
            "Docling OCR is not installed. Install backend/requirements-ocr.txt "
            "in the dedicated OCR worker environment."
        ) from exc

    options = PdfPipelineOptions()
    options.do_ocr = True
    options.ocr_options = RapidOcrOptions(
        mode=OcrMode.FULL_PAGE,
        lang=["english"],
    )
    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=options),
        }
    )


def _docling_ocr_markdown(
    path: Path,
) -> tuple[str, dict[str, object]]:
    """Run full-page OCR and fail closed if any page lacks usable text."""
    converter = _docling_ocr_converter()
    result = converter.convert(Path(path))
    markdown = result.document.export_to_markdown().strip()
    errors = [str(error) for error in (result.errors or [])]
    status = str(result.status)

    page_chars: dict[int, int] = {}
    for item, _level in result.document.iterate_items():
        text = str(getattr(item, "text", "") or "")
        for provenance in getattr(item, "prov", []) or []:
            page_number = int(provenance.page_no)
            page_chars[page_number] = (
                page_chars.get(page_number, 0) + len(text.strip())
            )
    page_numbers = sorted(
        int(number) for number in result.document.pages
    )
    pages_without_substantive_text = [
        page for page in page_numbers if page_chars.get(page, 0) < 20
    ]
    replacement_characters = markdown.count("\ufffd")
    if (
        not status.lower().endswith("success")
        or errors
        or not markdown
        or replacement_characters
        or pages_without_substantive_text
    ):
        raise ValueError(
            "Docling OCR did not pass the complete-text quality gate "
            f"(status={status}, errors={len(errors)}, "
            f"replacement_characters={replacement_characters}, "
            f"pages_without_substantive_text="
            f"{pages_without_substantive_text})"
        )

    return markdown, {
        "quality_status": "complete_text",
        "ocr_applied": True,
        "ocr_engine": "rapidocr",
        "ocr_mode": "full_page",
        "page_count": len(page_numbers),
        "pages_with_text": len(page_chars),
        "minimum_page_characters": min(page_chars.values(), default=0),
        "pages_without_substantive_text": [],
        "replacement_characters": replacement_characters,
        "conversion_status": status,
        "conversion_errors": [],
    }


def _pdf_inspector_markdown(path: Path) -> tuple[str, dict[str, object]]:
    """Extract Markdown and JSON-safe quality diagnostics with pdf-inspector."""
    try:
        import pdf_inspector  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "pdf-inspector is required for primary PDF-to-Markdown extraction."
        ) from e

    result = pdf_inspector.process_pdf(str(path))
    markdown = str(getattr(result, "markdown", "") or "").strip()
    pdf_type = str(getattr(result, "pdf_type", "unknown"))
    pages_needing_ocr = [
        int(page) for page in (getattr(result, "pages_needing_ocr", None) or [])
    ]
    has_encoding_issues = bool(
        getattr(result, "has_encoding_issues", False)
    )
    diagnostics: dict[str, object] = {
        "quality_status": "complete_text",
        "pdf_type": pdf_type,
        "confidence": float(getattr(result, "confidence", 0.0)),
        "page_count": int(getattr(result, "page_count", 0)),
        "processing_time_ms": int(
            getattr(result, "processing_time_ms", 0)
        ),
        "pages_needing_ocr": pages_needing_ocr,
        "has_encoding_issues": has_encoding_issues,
        "is_complex_layout": bool(
            getattr(result, "is_complex_layout", False)
        ),
        "pages_with_tables": [
            int(page)
            for page in (getattr(result, "pages_with_tables", None) or [])
        ],
        "pages_with_columns": [
            int(page)
            for page in (getattr(result, "pages_with_columns", None) or [])
        ],
    }
    if (
        pages_needing_ocr
        or has_encoding_issues
        or pdf_type in {"scanned", "image_based"}
    ):
        reasons: list[str] = []
        if pages_needing_ocr:
            reasons.append(f"pages_needing_ocr={pages_needing_ocr}")
        if has_encoding_issues:
            reasons.append("broken_font_encoding")
        if pdf_type in {"scanned", "image_based"}:
            reasons.append(f"pdf_type={pdf_type}")
        raise PdfNeedsOcrError(
            "pdf-inspector requires an OCR-capable route: " + ", ".join(reasons)
        )
    if not markdown:
        raise ValueError("pdf-inspector returned no Markdown")
    return markdown, diagnostics


def _package_version(package: str) -> str:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return "unknown"


def _render_document_as_markdown(doc: ParsedDocument) -> str:
    parts: list[str] = []
    if doc.title:
        parts.append(f"# {doc.title.strip()}")
    for section in doc.sections:
        text = section.text.strip()
        if not text:
            continue
        if section.section_type == "unknown":
            parts.append(text)
            continue
        title = section.title or section.section_type.replace("_", " ").title()
        parts.append(f"## {title.strip()}\n\n{text}")
    return "\n\n".join(parts).strip()


def convert_file_to_markdown(
    path: Path,
    *,
    ocr_backend: str | None = None,
) -> tuple[str, str, str, dict[str, object]]:
    """Convert a source document to Markdown for durable raw storage.

    Returns ``(markdown, backend, backend_version, diagnostics)``. PDF bytes
    remain only in the caller's temporary directory; this function never
    persists the source. PDFs known to need OCR fail closed rather than
    persisting incomplete text.
    """
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".md":
        markdown = p.read_text(encoding="utf-8").strip()
        backend = "markdown"
        version = "native"
        diagnostics: dict[str, object] = {"quality_status": "native"}
    elif suffix in {".txt", ""}:
        markdown = p.read_text(encoding="utf-8").strip()
        backend = "text"
        version = "native"
        diagnostics = {"quality_status": "native"}
    elif suffix == ".pdf":
        try:
            markdown, diagnostics = _pdf_inspector_markdown(p)
            backend = "pdf-inspector"
            version = _package_version("pdf-inspector")
        except PdfNeedsOcrError:
            if ocr_backend != "docling":
                raise
            markdown, diagnostics = _docling_ocr_markdown(p)
            backend = "docling-rapidocr"
            version = _package_version("docling")
        except Exception as inspector_error:
            diagnostics = {
                "quality_status": "unverified_fallback",
                "pdf_inspector_error": type(inspector_error).__name__,
            }
            try:
                markdown = _markitdown_text(p)
                backend = "markitdown"
                version = _package_version("markitdown")
            except Exception:
                doc = parse_pdf_as_document(p)
                markdown = _render_document_as_markdown(doc)
                backend = doc.source
                version = _package_version("pymupdf")
    else:
        markdown = _markitdown_text(p)
        backend = "markitdown"
        version = _package_version("markitdown")
        diagnostics = {"quality_status": "converted"}
    if not markdown:
        raise ValueError(f"No Markdown extracted from {p}")
    return markdown, backend, version, diagnostics


def parse_via_markitdown(path: Path) -> ParsedDocument:
    """Convert a document to Markdown with MarkItDown, then reuse text heuristics."""
    markdown = _markitdown_text(path)
    if not markdown:
        return ParsedDocument(source="markitdown")

    sections = split_into_sections(markdown)
    abstract = next(
        (s.text for s in sections if s.section_type == "abstract"), None
    )
    title = None
    for line in markdown.splitlines()[:20]:
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            title = stripped
            break
    return ParsedDocument(
        sections=sections,
        title=title,
        abstract=abstract,
        source="markitdown",
    )


def parse_any(path: Path, *, prefer_grobid: bool | None = None) -> ParsedDocument:
    """Pick the best available backend for the file.

    - `.pdf`: use GROBID first only when explicitly requested; otherwise try
      MarkItDown first, then GROBID when configured, then PyMuPDF.
    - Office / HTML / structured text formats: convert through MarkItDown.
    - `.txt` / `.md`: text path (no parser choice).
    """
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in {".txt", ".md", ""}:
        return parse_text_file_as_document(p)
    if suffix == ".pdf":
        from app.config import settings  # local import avoids cyclic init

        if prefer_grobid:
            try:
                from app.services.grobid_adapter import parse_pdf_via_grobid

                doc = parse_pdf_via_grobid(p)
                if doc.sections:
                    return doc
            except Exception:
                # Fall through so a downed GROBID never blocks ingestion.
                pass
        else:
            try:
                doc = parse_via_markitdown(p)
                if doc.sections:
                    return doc
            except Exception:
                pass

            if settings.grobid_url:
                try:
                    from app.services.grobid_adapter import parse_pdf_via_grobid

                    doc = parse_pdf_via_grobid(p)
                    if doc.sections:
                        return doc
                except Exception:
                    pass
        return parse_pdf_as_document(p)
    if suffix in SUPPORTED_FULLTEXT_SUFFIXES:
        return parse_via_markitdown(p)
    raise ValueError(f"Unsupported full-text format: {suffix}")
