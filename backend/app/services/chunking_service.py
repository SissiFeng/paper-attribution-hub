"""Section-aware chunking + contextual chunk prefixing (parse.md §3).

Policy (per rag.md):
- abstract, acknowledgements, figure_caption, references: do not chunk —
  these are short and meaning-load is concentrated.
- methods: ~600 tokens, 100 overlap (technical density).
- introduction / discussion / results: ~500 tokens, 80 overlap.
- everything else: 600 tokens, 80 overlap.

Contextual chunking (v0.4):
  Each chunk is given a one-line context prefix before BM25 / embedding so
  retrieval queries that don't share keywords with the chunk body still
  hit it ("This platform was used to optimize…" alone is meaningless; with
  context, "From <title> (2024), methods" disambiguates it).
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


def _tokenize(text: str) -> list[str]:
    return [w for w in _WHITESPACE.split(text.strip()) if w]


def chunk_section(section: ParsedSection, start_order: int = 0) -> list[Chunk]:
    policy = POLICY_BY_SECTION.get(section.section_type, _DEFAULT_POLICY)
    tokens = _tokenize(section.text)
    if not tokens:
        return []

    if not policy["split"] or policy["max_tokens"] <= 0 or len(tokens) <= policy["max_tokens"]:
        return [
            Chunk(
                text=section.text.strip(),
                section_type=section.section_type,
                section_title=section.title,
                order_index=start_order,
                char_start=0,
                char_end=len(section.text),
                token_count=len(tokens),
            )
        ]

    chunks: list[Chunk] = []
    max_tokens = policy["max_tokens"]
    overlap = policy["overlap"]
    step = max(max_tokens - overlap, 1)

    cursor = 0
    order = start_order
    text = section.text
    while cursor < len(tokens):
        window = tokens[cursor : cursor + max_tokens]
        chunk_text = " ".join(window)
        char_start = text.find(window[0]) if window else 0
        char_end = char_start + len(chunk_text)
        chunks.append(
            Chunk(
                text=chunk_text,
                section_type=section.section_type,
                section_title=section.title,
                order_index=order,
                char_start=max(char_start, 0),
                char_end=char_end,
                token_count=len(window),
            )
        )
        order += 1
        cursor += step
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
