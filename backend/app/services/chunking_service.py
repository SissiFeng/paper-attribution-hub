"""Section-aware semantic chunking + contextual chunk prefixing (parse.md §3).

Policy (per rag.md):
- abstract, acknowledgements, figure_caption, references: do not chunk —
  these are short and meaning-load is concentrated.
- methods: adaptive semantic chunks around 350-600 tokens.
- introduction / discussion / results: adaptive semantic chunks around 300-500 tokens.
- everything else: adaptive semantic chunks around 350-600 tokens.

Contextual chunking (v0.4):
  Each chunk is given a one-line context prefix before BM25 / embedding so
  retrieval queries that don't share keywords with the chunk body still
  hit it ("This platform was used to optimize…" alone is meaningless; with
  context, "From <title> (2024), methods" disambiguates it).

Parent-child indexing:
  The database stores child chunks only, but each child carries its semantic
  parent window in metadata. `indexed_text` can then include a compact parent
  context while retrieval still returns the precise child text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.pdf_parser import ParsedSection


@dataclass
class Chunk:
    text: str
    section_type: str
    section_title: str | None
    order_index: int
    char_start: int
    char_end: int
    token_count: int
    parent_id: str | None = None
    parent_text: str | None = None
    parent_char_start: int = 0
    parent_char_end: int = 0
    parent_token_count: int = 0
    split_strategy: str = "semantic_adaptive"


_DEFAULT_POLICY = {"max_tokens": 600, "overlap": 80, "split": True}

POLICY_BY_SECTION: dict[str, dict] = {
    "abstract": {"max_tokens": 0, "overlap": 0, "split": False},
    "acknowledgements": {"max_tokens": 0, "overlap": 0, "split": False},
    "figure_caption": {"max_tokens": 0, "overlap": 0, "split": False},
    "references": {"max_tokens": 0, "overlap": 0, "split": False},
    "supplementary": {"max_tokens": 800, "overlap": 100, "split": True},
    "methods": {"max_tokens": 600, "overlap": 100, "split": True},
    "introduction": {"max_tokens": 500, "overlap": 80, "split": True},
    "results": {"max_tokens": 500, "overlap": 80, "split": True},
    "discussion": {"max_tokens": 500, "overlap": 80, "split": True},
    "unknown": {"max_tokens": 600, "overlap": 80, "split": True},
}


_WHITESPACE = re.compile(r"\s+")
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
_SEMANTIC_BREAK_THRESHOLD = 0.12
_PARENT_TEXT_LIMIT = 4000


def _tokenize(text: str) -> list[str]:
    return [w for w in _WHITESPACE.split(text.strip()) if w]


@dataclass
class _Segment:
    text: str
    char_start: int
    char_end: int
    tokens: list[str]


@dataclass
class _ParentWindow:
    text: str
    char_start: int
    char_end: int
    token_count: int
    segments: list[_Segment]


def _semantic_tokens(text: str) -> set[str]:
    return {
        tok.lower().strip(".,;:()[]{}")
        for tok in _tokenize(text)
        if len(tok.strip(".,;:()[]{}")) > 2
    }


def _semantic_similarity(left: str, right: str) -> float:
    a = _semantic_tokens(left)
    b = _semantic_tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _segments_with_offsets(text: str) -> list[_Segment]:
    segments: list[_Segment] = []
    cursor = 0
    paragraphs: list[tuple[str, int, int]] = []
    for part in _PARAGRAPH_SPLIT.split(text):
        if not part.strip():
            cursor += len(part)
            continue
        start = text.find(part, cursor)
        if start < 0:
            start = cursor
        end = start + len(part)
        paragraphs.append((part, start, end))
        cursor = end

    if not paragraphs and text.strip():
        stripped = text.strip()
        start = text.find(stripped)
        paragraphs = [(stripped, start, start + len(stripped))]

    for para, para_start, _para_end in paragraphs:
        sentences = _SENTENCE_SPLIT.split(para.strip())
        if len(sentences) <= 1:
            raw_segments = [para.strip()]
        else:
            raw_segments = [s.strip() for s in sentences if s.strip()]
        local_cursor = para_start
        for raw in raw_segments:
            start = text.find(raw, local_cursor)
            if start < 0:
                start = local_cursor
            end = start + len(raw)
            toks = _tokenize(raw)
            if toks:
                segments.append(_Segment(raw, start, end, toks))
            local_cursor = end
    return segments


def _policy_limits(policy: dict, token_count: int) -> tuple[int, int, int]:
    max_tokens = int(policy["max_tokens"])
    overlap = int(policy["overlap"])
    # Adaptive target: short sections get fewer, tighter chunks; long technical
    # sections retain the policy maximum to keep evidence windows readable.
    if token_count < max_tokens * 2:
        max_tokens = max(220, int(max_tokens * 0.75))
        overlap = min(overlap, 60)
    min_tokens = max(80, int(max_tokens * 0.45))
    return min_tokens, max_tokens, overlap


def _window_text(segments: list[_Segment]) -> str:
    return "\n\n".join(s.text for s in segments).strip()


def _semantic_parent_windows(section: ParsedSection, policy: dict) -> list[_ParentWindow]:
    segments = _segments_with_offsets(section.text)
    if not segments:
        return []

    total_tokens = sum(len(seg.tokens) for seg in segments)
    min_tokens, max_tokens, _overlap = _policy_limits(policy, total_tokens)
    windows: list[_ParentWindow] = []
    current: list[_Segment] = []
    current_tokens = 0

    def flush() -> None:
        nonlocal current, current_tokens
        if not current:
            return
        text = _window_text(current)
        windows.append(
            _ParentWindow(
                text=text,
                char_start=current[0].char_start,
                char_end=current[-1].char_end,
                token_count=current_tokens,
                segments=list(current),
            )
        )
        current = []
        current_tokens = 0

    for seg in segments:
        seg_tokens = len(seg.tokens)
        if current:
            sim = _semantic_similarity(current[-1].text, seg.text)
            would_exceed = current_tokens + seg_tokens > max_tokens
            semantic_break = (
                sim < _SEMANTIC_BREAK_THRESHOLD and current_tokens >= min_tokens
            )
            if would_exceed or semantic_break:
                flush()
        current.append(seg)
        current_tokens += seg_tokens
    flush()
    return windows


def _sliding_token_chunks(
    *,
    text: str,
    tokens: list[str],
    section: ParsedSection,
    start_order: int,
    max_tokens: int,
    overlap: int,
    parent_id: str | None = None,
    parent_text: str | None = None,
    parent_char_start: int = 0,
    parent_char_end: int = 0,
    parent_token_count: int = 0,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    step = max(max_tokens - overlap, 1)
    cursor = 0
    order = start_order
    search_from = 0
    while cursor < len(tokens):
        window = tokens[cursor : cursor + max_tokens]
        chunk_text = " ".join(window)
        char_start = text.find(window[0], search_from) if window else 0
        if char_start < 0:
            char_start = 0
        char_end = char_start + len(chunk_text)
        absolute_start = parent_char_start + char_start
        absolute_end = parent_char_start + char_end
        chunks.append(
            Chunk(
                text=chunk_text,
                section_type=section.section_type,
                section_title=section.title,
                order_index=order,
                char_start=absolute_start,
                char_end=absolute_end,
                token_count=len(window),
                parent_id=parent_id,
                parent_text=parent_text,
                parent_char_start=parent_char_start,
                parent_char_end=parent_char_end,
                parent_token_count=parent_token_count,
                split_strategy="sliding_fallback",
            )
        )
        order += 1
        cursor += step
        search_from = char_start
    return chunks


def chunk_section(section: ParsedSection, start_order: int = 0) -> list[Chunk]:
    policy = POLICY_BY_SECTION.get(section.section_type, _DEFAULT_POLICY)
    tokens = _tokenize(section.text)
    if not tokens:
        return []

    if not policy["split"] or policy["max_tokens"] <= 0:
        return [
            Chunk(
                text=section.text.strip(),
                section_type=section.section_type,
                section_title=section.title,
                order_index=start_order,
                char_start=0,
                char_end=len(section.text),
                token_count=len(tokens),
                parent_id=f"{section.section_type}:0",
                parent_text=section.text.strip()[:_PARENT_TEXT_LIMIT],
                parent_char_start=0,
                parent_char_end=len(section.text),
                parent_token_count=len(tokens),
                split_strategy="unsplit",
            )
        ]

    chunks: list[Chunk] = []
    _min_tokens, max_tokens, overlap = _policy_limits(policy, len(tokens))
    for parent_index, parent in enumerate(_semantic_parent_windows(section, policy)):
        parent_id = f"{section.section_type}:{parent_index}"
        parent_text = parent.text[:_PARENT_TEXT_LIMIT]
        if parent.token_count <= max_tokens:
            chunks.append(
                Chunk(
                    text=parent.text,
                    section_type=section.section_type,
                    section_title=section.title,
                    order_index=start_order + len(chunks),
                    char_start=parent.char_start,
                    char_end=parent.char_end,
                    token_count=parent.token_count,
                    parent_id=parent_id,
                    parent_text=parent_text,
                    parent_char_start=parent.char_start,
                    parent_char_end=parent.char_end,
                    parent_token_count=parent.token_count,
                    split_strategy="semantic_adaptive",
                )
            )
            continue
        chunks.extend(
            _sliding_token_chunks(
                text=parent.text,
                tokens=_tokenize(parent.text),
                section=section,
                start_order=start_order + len(chunks),
                max_tokens=max_tokens,
                overlap=overlap,
                parent_id=parent_id,
                parent_text=parent_text,
                parent_char_start=parent.char_start,
                parent_char_end=parent.char_end,
                parent_token_count=parent.token_count,
            )
        )
    return chunks


def chunk_sections(sections: list[ParsedSection]) -> list[Chunk]:
    out: list[Chunk] = []
    for sec in sections:
        out.extend(chunk_section(sec, start_order=len(out)))
    return out


def contextual_prefix(
    *,
    title: str | None,
    year: int | None,
    section_type: str,
    section_title: str | None,
) -> str:
    """Build the one-line context prefix used for BM25 / embeddings.

    Format: `Context: From "<title>" (<year>), <section_type>[ — <section_title>].`
    Falls back gracefully when any field is missing.
    """
    parts: list[str] = []
    if title:
        if year is not None:
            parts.append(f'From "{title}" ({year})')
        else:
            parts.append(f'From "{title}"')
    elif year is not None:
        parts.append(f"({year})")

    section_label = section_type.replace("_", " ")
    if section_title and section_title.strip().lower() != section_type.replace("_", " "):
        parts.append(f"{section_label}: {section_title.strip()}")
    else:
        parts.append(section_label)

    return "Context: " + ", ".join(parts).strip() + "."


def with_context(chunk_text: str, prefix: str) -> str:
    """Compose the indexed-text used by BM25 + embeddings."""
    return f"{prefix}\n\n{chunk_text}"


def with_parent_context(
    chunk_text: str,
    prefix: str,
    parent_text: str | None,
) -> str:
    """Compose indexed text for child chunks with compact parent context."""
    if not parent_text or parent_text.strip() == chunk_text.strip():
        return with_context(chunk_text, prefix)
    parent = parent_text.strip()
    return f"{prefix}\n\nParent context:\n{parent}\n\nChild chunk:\n{chunk_text}"
