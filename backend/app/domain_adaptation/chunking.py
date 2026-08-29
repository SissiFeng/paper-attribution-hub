"""Structure-first, evidence-preserving chunks shared by domain packages."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from app.domain_adaptation.extractors import (
    is_high_information_chunk,
    scientific_content,
)
from app.domain_adaptation.models import (
    ScientificChunk,
    ScientificChunkSegment,
    ScientificSemanticRole,
    SourceChunk,
    SourcePaper,
)


SCIENTIFIC_CHUNK_SCHEMA = "domain-adapter-scientific-chunk-v0.1"

_HIGH_INFORMATION_SECTIONS = {
    "methods",
    "method",
    "experimental",
    "experimental methods",
    "materials and methods",
    "results",
    "results and discussion",
    "computational details",
    "supplementary",
}
_ACTION_RE = re.compile(
    r"\b(?:add(?:ed)?|anneal(?:ed)?|calcine(?:d)?|collect(?:ed)?|"
    r"deposit(?:ed)?|dispers(?:ed)?|dissolv(?:ed)?|dry|dried|heat(?:ed)?|"
    r"measure(?:d)?|mix(?:ed)?|prepare(?:d)?|record(?:ed)?|scan(?:ned)?|"
    r"sonicat(?:ed)?|stir(?:red)?|test(?:ed)?)\b",
    re.IGNORECASE,
)
_CONDITION_RE = re.compile(
    r"\b\d+(?:\.\d+)?(?:\s*(?:to|[-–−])\s*\d+(?:\.\d+)?)?\s*"
    r"(?:°C|K|h|min|s|mL|μL|uL|L|mg|g|mol|mmol|M|mM|V|mV|A|mA|"
    r"Hz|nm|μm|um|cm|mm|%|degrees?)\b",
    re.IGNORECASE,
)
_CHARACTERIZATION_RE = re.compile(
    r"\b(?:characteri[sz]|spectroscop|microscop|diffract|voltamm|"
    r"XRD|XPS|SEM|TEM|STEM|Raman|FTIR|ICP-(?:MS|OES)|XAS|EIS|LSV|CV)\b",
    re.IGNORECASE,
)
_COMPUTATION_RE = re.compile(
    r"\b(?:computational|calculation|simulat|density functional theory|"
    r"DFT|molecular dynamics|finite element|VASP|Quantum ESPRESSO|COMSOL)\b",
    re.IGNORECASE,
)
_RESULT_RE = re.compile(
    r"\b(?:result|observed|obtained|yield|selectivity|activity|performance|"
    r"overpotential|Tafel slope|stability|accuracy|error)\b",
    re.IGNORECASE,
)
_CAVEAT_RE = re.compile(
    r"\b(?:however|limitation|limited by|failed|failure|degradation|"
    r"unstable|instability|caution|careful|must be)\b",
    re.IGNORECASE,
)
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _stable_id(prefix: str, *parts: str) -> str:
    return f"{prefix}_{_sha256(chr(0).join(parts))[:16]}"


@dataclass(frozen=True)
class ScientificChunkingPolicy:
    """Structural boundaries first; character length is only a safety limit."""

    max_chars: int = 6000
    min_merge_chars: int = 800
    schema_version: str = SCIENTIFIC_CHUNK_SCHEMA

    def __post_init__(self) -> None:
        if self.max_chars < 1:
            raise ValueError("max_chars must be positive")
        if self.min_merge_chars < 0:
            raise ValueError("min_merge_chars cannot be negative")
        if self.min_merge_chars > self.max_chars:
            raise ValueError("min_merge_chars cannot exceed max_chars")

    def manifest(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "strategy": "structure_first_semantic",
            "max_chars_safety_limit": self.max_chars,
            "min_merge_chars": self.min_merge_chars,
            "source_blocks_immutable": True,
            "exact_source_segment_provenance": True,
        }


@dataclass(frozen=True)
class _Candidate:
    source_chunk: SourceChunk
    parent_section_id: str
    char_start: int
    char_end: int
    semantic_roles: tuple[ScientificSemanticRole, ...]

    @property
    def text(self) -> str:
        return self.source_chunk.text[self.char_start : self.char_end]


def _is_scientific_source_chunk(chunk: SourceChunk) -> bool:
    label = f"{chunk.section_type} {chunk.section_title or ''}".casefold()
    if "reference" in label or "acknowledg" in label:
        return False
    text = scientific_content(chunk.text)
    if not text.strip():
        return False
    section = (chunk.section_type or "unknown").strip().casefold()
    if section in _HIGH_INFORMATION_SECTIONS and len(text.strip()) >= 40:
        return True
    return is_high_information_chunk(chunk)


def _semantic_roles(
    text: str, section_type: str
) -> tuple[ScientificSemanticRole, ...]:
    roles: list[ScientificSemanticRole] = []
    section = section_type.strip().casefold()
    action = bool(_ACTION_RE.search(text))
    condition = bool(_CONDITION_RE.search(text))
    if (action and condition) or (
        section in {"methods", "method", "experimental", "experimental methods"}
        and action
    ):
        roles.append("protocol")
    if _CHARACTERIZATION_RE.search(text):
        roles.append("characterization")
    if _COMPUTATION_RE.search(text) or "computational" in section:
        roles.append("computation")
    if _RESULT_RE.search(text) or section in {"results", "results and discussion"}:
        roles.append("result")
    if _CAVEAT_RE.search(text):
        roles.append("caveat")
    if not roles:
        roles.append("scientific_context")
    return tuple(roles)


def _hard_split(text: str, start: int, end: int, max_chars: int) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    cursor = start
    while end - cursor > max_chars:
        proposed = cursor + max_chars
        split_at = text.rfind("\n", cursor, proposed + 1)
        if split_at <= cursor:
            split_at = text.rfind(" ", cursor, proposed + 1)
        if split_at <= cursor:
            split_at = proposed
        spans.append((cursor, split_at))
        cursor = split_at
        while cursor < end and text[cursor].isspace():
            cursor += 1
    if cursor < end:
        spans.append((cursor, end))
    return spans


def _bounded_spans(text: str, max_chars: int) -> list[tuple[int, int]]:
    if len(text) <= max_chars:
        return [(0, len(text))]
    sentences: list[tuple[int, int]] = []
    start = 0
    for boundary in list(_SENTENCE_BOUNDARY_RE.finditer(text)) + [None]:
        end = boundary.start() if boundary is not None else len(text)
        if end > start:
            sentences.extend(
                _hard_split(text, start, end, max_chars)
                if end - start > max_chars
                else [(start, end)]
            )
        start = boundary.end() if boundary is not None else len(text)

    groups: list[tuple[int, int]] = []
    group_start: int | None = None
    group_end: int | None = None
    for sentence_start, sentence_end in sentences:
        if group_start is None:
            group_start, group_end = sentence_start, sentence_end
            continue
        if sentence_end - group_start <= max_chars:
            group_end = sentence_end
            continue
        groups.append((group_start, group_end or sentence_start))
        group_start, group_end = sentence_start, sentence_end
    if group_start is not None and group_end is not None:
        groups.append((group_start, group_end))
    return groups


def _section_signature(chunk: SourceChunk) -> str:
    return "\0".join(
        [chunk.section_type, chunk.section_title or "", *chunk.section_path]
    )


def _candidates(
    paper: SourcePaper, policy: ScientificChunkingPolicy
) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    previous_section: str | None = None
    section_ordinal = -1
    parent_section_id = ""
    for source_chunk in paper.chunks:
        if not _is_scientific_source_chunk(source_chunk):
            continue
        section_signature = _section_signature(source_chunk)
        if section_signature != previous_section:
            section_ordinal += 1
            parent_section_id = _stable_id(
                "scisec",
                paper.paper_id,
                str(section_ordinal),
                section_signature,
            )
            previous_section = section_signature
        content = scientific_content(source_chunk.text)
        for start, end in _bounded_spans(content, policy.max_chars):
            candidate_text = source_chunk.text[start:end]
            candidates.append(
                _Candidate(
                    source_chunk=source_chunk,
                    parent_section_id=parent_section_id,
                    char_start=start,
                    char_end=end,
                    semantic_roles=_semantic_roles(
                        candidate_text, source_chunk.section_type
                    ),
                )
            )
    return candidates


def _can_merge(
    current: list[_Candidate], candidate: _Candidate, policy: ScientificChunkingPolicy
) -> bool:
    if not current or current[-1].parent_section_id != candidate.parent_section_id:
        return False
    combined_length = sum(len(item.text) for item in current) + 2 * len(current)
    combined_length += len(candidate.text)
    if combined_length > policy.max_chars:
        return False
    current_roles = {role for item in current for role in item.semantic_roles}
    return (
        sum(len(item.text) for item in current) < policy.min_merge_chars
        or len(candidate.text) < policy.min_merge_chars
        or bool(current_roles.intersection(candidate.semantic_roles))
    )


def _to_scientific_chunk(
    paper: SourcePaper, ordinal: int, candidates: list[_Candidate]
) -> ScientificChunk:
    first = candidates[0]
    segments = [
        ScientificChunkSegment(
            source_chunk_id=item.source_chunk.chunk_id,
            char_start=item.char_start,
            char_end=item.char_end,
            document_char_start=(
                item.source_chunk.document_char_start + item.char_start
                if item.source_chunk.document_char_start is not None
                else None
            ),
            document_char_end=(
                item.source_chunk.document_char_start + item.char_end
                if item.source_chunk.document_char_start is not None
                else None
            ),
            source_sha256=_sha256(item.source_chunk.text),
        )
        for item in candidates
    ]
    text = "\n\n".join(item.text for item in candidates)
    source_chunk_ids = list(
        dict.fromkeys(item.source_chunk.chunk_id for item in candidates)
    )
    content_sha256 = _sha256(text)
    scientific_chunk_id = _stable_id(
        "scichk",
        paper.paper_id,
        first.parent_section_id,
        "\0".join(
            f"{item.source_chunk.chunk_id}:{item.char_start}:{item.char_end}"
            for item in candidates
        ),
        content_sha256,
    )
    role_order: tuple[ScientificSemanticRole, ...] = (
        "protocol",
        "characterization",
        "computation",
        "result",
        "caveat",
        "scientific_context",
    )
    observed_roles = {role for item in candidates for role in item.semantic_roles}
    return ScientificChunk(
        scientific_chunk_id=scientific_chunk_id,
        paper_id=paper.paper_id,
        ordinal=ordinal,
        parent_section_id=first.parent_section_id,
        section_type=first.source_chunk.section_type,
        section_title=first.source_chunk.section_title,
        section_path=first.source_chunk.section_path,
        semantic_roles=[role for role in role_order if role in observed_roles],
        source_chunk_ids=source_chunk_ids,
        segments=segments,
        text=text,
        content_sha256=content_sha256,
    )


def build_scientific_chunks(
    paper: SourcePaper,
    *,
    policy: ScientificChunkingPolicy | None = None,
) -> list[ScientificChunk]:
    """Build semantic chunks without losing exact source-block provenance."""
    active_policy = policy or ScientificChunkingPolicy()
    groups: list[list[_Candidate]] = []
    for candidate in _candidates(paper, active_policy):
        if groups and _can_merge(groups[-1], candidate, active_policy):
            groups[-1].append(candidate)
        else:
            groups.append([candidate])
    return [
        _to_scientific_chunk(paper, ordinal, group)
        for ordinal, group in enumerate(groups)
    ]


def validate_scientific_chunk(
    chunk: ScientificChunk, paper: SourcePaper
) -> list[str]:
    """Verify every semantic chunk can be reconstructed from source blocks."""
    violations: list[str] = []
    if chunk.paper_id != paper.paper_id:
        violations.append("paper_id does not match source paper")
    source_by_id = {item.chunk_id: item for item in paper.chunks}
    reconstructed: list[str] = []
    reconstructed_ids: list[str] = []
    for segment in chunk.segments:
        source = source_by_id.get(segment.source_chunk_id)
        if source is None:
            violations.append(f"missing source chunk: {segment.source_chunk_id}")
            continue
        if segment.char_end > len(source.text) or segment.char_start >= segment.char_end:
            violations.append(f"invalid source offsets: {segment.source_chunk_id}")
            continue
        if segment.source_sha256 != _sha256(source.text):
            violations.append(f"source hash mismatch: {segment.source_chunk_id}")
        reconstructed.append(source.text[segment.char_start : segment.char_end])
        if segment.source_chunk_id not in reconstructed_ids:
            reconstructed_ids.append(segment.source_chunk_id)
    reconstructed_text = "\n\n".join(reconstructed)
    if reconstructed_text != chunk.text:
        violations.append("text is not exactly reconstructable from source segments")
    if reconstructed_ids != chunk.source_chunk_ids:
        violations.append("source_chunk_ids do not match segment order")
    if _sha256(chunk.text) != chunk.content_sha256:
        violations.append("content hash does not match chunk text")
    return violations
