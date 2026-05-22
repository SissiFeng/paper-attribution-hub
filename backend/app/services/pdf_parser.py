"""Parse PDFs (or .txt fall-backs) into structured sections.

The parser yields `ParsedDocument(title, abstract, authors, sections, references)`.
v0.2 uses PyMuPDF for PDFs and pure-Python regex section splitting.
v0.4 adds a GROBID adapter (see `grobid_adapter.py`) — when GROBID is
reachable, `parse_any` routes PDF files through it for higher-fidelity
sections, authors, and references; otherwise the PyMuPDF path runs as
before.

The `ParsedDocument` dataclass is the contract between parsers and the
ingestion pipeline. Any new backend (e.g. a Semantic Scholar API adapter)
only needs to emit the same shape.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
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


def parse_any(path: Path, *, prefer_grobid: bool | None = None) -> ParsedDocument:
    """Pick the best available backend for the file.

    - `.pdf`: try GROBID first when `prefer_grobid` is True (or auto when
      `PAS_GROBID_URL` is set and reachable); otherwise PyMuPDF.
    - `.txt` / `.md`: text path (no parser choice).
    """
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in {".txt", ".md", ""}:
        return parse_text_file_as_document(p)
    if suffix == ".pdf":
        from app.config import settings  # local import avoids cyclic init

        want_grobid = prefer_grobid
        if want_grobid is None:
            want_grobid = bool(settings.grobid_url)
        if want_grobid:
            try:
                from app.services.grobid_adapter import parse_pdf_via_grobid

                doc = parse_pdf_via_grobid(p)
                if doc.sections:
                    return doc
            except Exception:
                # Fall through to PyMuPDF so a downed GROBID never blocks ingestion.
                pass
        return parse_pdf_as_document(p)
    raise ValueError(f"Unsupported full-text format: {suffix}")
