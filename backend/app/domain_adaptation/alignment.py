"""Deterministic evidence alignment that preserves exact source offsets."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
import re

from app.domain_adaptation.audit import RejectionReason


@dataclass(frozen=True)
class EvidenceAlignment:
    matched: bool
    char_start: int
    char_end: int
    exact_source_span: str | None
    reason: RejectionReason | None
    nearest_source_span: str | None
    repair_attempted: bool
    repair_succeeded: bool


def _collapse_whitespace_with_offsets(text: str) -> tuple[str, list[int]]:
    normalized: list[str] = []
    offsets: list[int] = []
    for index, character in enumerate(text):
        if character.isspace():
            if normalized and normalized[-1] != " ":
                normalized.append(" ")
                offsets.append(index)
            continue
        normalized.append(character)
        offsets.append(index)
    if normalized and normalized[-1] == " ":
        normalized.pop()
        offsets.pop()
    return "".join(normalized), offsets


def _repair_hyphenation_with_offsets(text: str) -> tuple[str, list[int]]:
    repaired: list[str] = []
    repaired_offsets: list[int] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character == "\u00ad":
            index += 1
            continue
        if character == "-" and repaired and repaired[-1].isalnum():
            next_index = index + 1
            saw_line_break = False
            while next_index < len(text) and text[next_index].isspace():
                saw_line_break |= text[next_index] in "\r\n"
                next_index += 1
            if (
                saw_line_break
                and next_index < len(text)
                and text[next_index].isalnum()
            ):
                index = next_index
                continue
        repaired.append(character)
        repaired_offsets.append(index)
        index += 1

    normalized: list[str] = []
    offsets: list[int] = []
    for character, source_offset in zip(repaired, repaired_offsets, strict=True):
        if character.isspace():
            if normalized and normalized[-1] != " ":
                normalized.append(" ")
                offsets.append(source_offset)
            continue
        normalized.append(character)
        offsets.append(source_offset)
    if normalized and normalized[-1] == " ":
        normalized.pop()
        offsets.pop()
    return "".join(normalized), offsets


def _normalize_unicode_with_offsets(text: str) -> tuple[str, list[int]]:
    hyphenated, hyphenated_offsets = _repair_hyphenation_with_offsets(text)
    normalized: list[str] = []
    offsets: list[int] = []
    dash_characters = "‐‑‒–—―−﹘﹣－"
    for character, source_offset in zip(
        hyphenated, hyphenated_offsets, strict=True
    ):
        fragment = unicodedata.normalize("NFKC", character)
        for normalized_character in fragment:
            normalized.append(
                "-" if normalized_character in dash_characters else normalized_character
            )
            offsets.append(source_offset)
    return "".join(normalized), offsets


def _compact_normalized_with_offsets(text: str) -> tuple[str, list[int]]:
    normalized, normalized_offsets = _normalize_unicode_with_offsets(text)
    compact: list[str] = []
    offsets: list[int] = []
    for character, source_offset in zip(
        normalized, normalized_offsets, strict=True
    ):
        if character.isspace():
            continue
        compact.append(character)
        offsets.append(source_offset)
    return "".join(compact), offsets


def _nearest_source_span(source_text: str, cited_span: str) -> str | None:
    candidates = [
        match.group(0).strip()
        for match in re.finditer(r"[^.!?]+[.!?]?", source_text)
        if match.group(0).strip()
    ]
    if not candidates:
        return None
    normalized_citation, _offsets = _compact_normalized_with_offsets(cited_span)
    if not normalized_citation:
        return None
    best_span: str | None = None
    best_score = 0.0
    for candidate in candidates:
        normalized_candidate, _offsets = _compact_normalized_with_offsets(
            candidate
        )
        score = SequenceMatcher(
            None, normalized_citation, normalized_candidate
        ).ratio()
        if score > best_score:
            best_score = score
            best_span = candidate
    return best_span if best_score >= 0.35 else None


def normalized_text_contains(value: str, source_span: str) -> bool:
    """Compare a field value after deterministic scientific-text repairs."""
    normalized_value, _value_offsets = _normalize_unicode_with_offsets(value)
    normalized_source, _source_offsets = _normalize_unicode_with_offsets(
        source_span
    )

    def normalize_units(text: str) -> str:
        text = re.sub(r"\s+", " ", text).strip().casefold()
        return re.sub(r"(?<=\d)\s+(?=[a-zμµ°%])", "", text)

    supported_value = normalize_units(normalized_value)
    return bool(supported_value) and supported_value in normalize_units(
        normalized_source
    )


def align_evidence_span(source_text: str, cited_span: str) -> EvidenceAlignment:
    """Locate a teacher citation and return the exact source substring."""
    exact_start = source_text.find(cited_span)
    if exact_start >= 0:
        exact_end = exact_start + len(cited_span)
        return EvidenceAlignment(
            matched=True,
            char_start=exact_start,
            char_end=exact_end,
            exact_source_span=source_text[exact_start:exact_end],
            reason=None,
            nearest_source_span=None,
            repair_attempted=False,
            repair_succeeded=False,
        )

    normalized_source, source_offsets = _collapse_whitespace_with_offsets(
        source_text
    )
    normalized_quote, _quote_offsets = _collapse_whitespace_with_offsets(
        cited_span
    )
    normalized_start = normalized_source.find(normalized_quote)
    if normalized_quote and normalized_start >= 0:
        source_start = source_offsets[normalized_start]
        source_end = source_offsets[
            normalized_start + len(normalized_quote) - 1
        ] + 1
        return EvidenceAlignment(
            matched=True,
            char_start=source_start,
            char_end=source_end,
            exact_source_span=source_text[source_start:source_end],
            reason=RejectionReason.WHITESPACE_MISMATCH,
            nearest_source_span=None,
            repair_attempted=True,
            repair_succeeded=True,
        )

    hyphenated_source, hyphenated_offsets = _repair_hyphenation_with_offsets(
        source_text
    )
    hyphenated_quote, _quote_offsets = _repair_hyphenation_with_offsets(
        cited_span
    )
    hyphenated_start = hyphenated_source.find(hyphenated_quote)
    if hyphenated_quote and hyphenated_start >= 0:
        source_start = hyphenated_offsets[hyphenated_start]
        source_end = hyphenated_offsets[
            hyphenated_start + len(hyphenated_quote) - 1
        ] + 1
        return EvidenceAlignment(
            matched=True,
            char_start=source_start,
            char_end=source_end,
            exact_source_span=source_text[source_start:source_end],
            reason=RejectionReason.HYPHENATION,
            nearest_source_span=None,
            repair_attempted=True,
            repair_succeeded=True,
        )

    unicode_source, unicode_offsets = _normalize_unicode_with_offsets(source_text)
    unicode_quote, _quote_offsets = _normalize_unicode_with_offsets(cited_span)
    unicode_start = unicode_source.find(unicode_quote)
    if unicode_quote and unicode_start >= 0:
        source_start = unicode_offsets[unicode_start]
        source_end = unicode_offsets[unicode_start + len(unicode_quote) - 1] + 1
        return EvidenceAlignment(
            matched=True,
            char_start=source_start,
            char_end=source_end,
            exact_source_span=source_text[source_start:source_end],
            reason=RejectionReason.NORMALIZATION,
            nearest_source_span=None,
            repair_attempted=True,
            repair_succeeded=True,
        )

    compact_source, compact_offsets = _compact_normalized_with_offsets(
        source_text
    )
    compact_quote, _quote_offsets = _compact_normalized_with_offsets(cited_span)
    compact_start = compact_source.find(compact_quote)
    if compact_quote and compact_start >= 0:
        source_start = compact_offsets[compact_start]
        source_end = compact_offsets[compact_start + len(compact_quote) - 1] + 1
        return EvidenceAlignment(
            matched=True,
            char_start=source_start,
            char_end=source_end,
            exact_source_span=source_text[source_start:source_end],
            reason=RejectionReason.NORMALIZATION,
            nearest_source_span=None,
            repair_attempted=True,
            repair_succeeded=True,
        )

    return EvidenceAlignment(
        matched=False,
        char_start=-1,
        char_end=-1,
        exact_source_span=None,
        reason=RejectionReason.SPAN_NOT_IN_SOURCE,
        nearest_source_span=_nearest_source_span(source_text, cited_span),
        repair_attempted=True,
        repair_succeeded=False,
    )
