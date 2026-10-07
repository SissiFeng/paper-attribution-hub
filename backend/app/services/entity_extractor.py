"""Typed entity extraction for cross-SDL knowledge transfer.

Scans each paper's title, abstract, and full-text chunks for vocabulary terms
from data/sdl_entities.yaml (methods / materials / instruments / software).
Matching is case-insensitive with word boundaries via text_utils.find_term_hits,
so "ML" never fires inside another word and "polymer" doesn't fire inside
"polymerization". Aliases shorter than MIN_TERM_LEN characters are skipped.

Confidence per entity = max over evidence locations:
  0.9 chunk hit (evidence_chunk_id + section recorded)
  0.7 abstract hit
  0.6 title-only hit

For method entities the containing sentence of the hit is kept as
`usage_snippet` (≤250 chars) and matched against the pipeline-stage keyword
stems in data/method_stages.yaml to set `stage`. Stage priority is the order
stages appear in that file; the first stage whose keywords match the sentence
wins. When a method is mentioned in several places, the hit that HAS a stage
is preferred, then higher confidence (as before). Non-method entity types get
stage = usage_snippet = NULL.

Extraction is idempotent: each run replaces a paper's existing rows.
"""
from __future__ import annotations

import csv
import re
import uuid
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Paper, PaperChunk, PaperEntity
from app.services.normalization_service import (
    normalize_institution,
    normalize_name,
    strip_diacritics,
)
from app.services.text_utils import find_term_hits

# yaml section name → PaperEntity.entity_type
_SECTION_TO_TYPE = {
    "methods": "method",
    "materials": "material",
    "instruments": "instrument",
    "software": "software",
}

MIN_TERM_LEN = 3

CONFIDENCE_CHUNK = 0.9
CONFIDENCE_ABSTRACT = 0.7
CONFIDENCE_TITLE = 0.6

USAGE_SNIPPET_MAX_CHARS = 250

AFFILIATION_CONFIDENCE_ALIAS = 0.95
AFFILIATION_CONFIDENCE_PATTERN = 0.8
AFFILIATION_FRONTMATTER_MAX_CHARS = 12_000

_AFFILIATION_MARKER_RE = re.compile(
    r"\b("
    r"universit(?:y|é|ät|à|a)|"
    r"institute|institut|"
    r"laborator(?:y|ies)|"
    r"college|academy|"
    r"research\s+cent(?:er|re)"
    r")\b",
    re.IGNORECASE,
)
_AFFILIATION_LINE_SPLIT_RE = re.compile(
    r"(?:\s*[;,|•]\s*|\.\s+(?=[A-ZÀ-ÖØ-Þ]))"
)
_AFFILIATION_PREFIX_RE = re.compile(
    r"^\s*(?:[\d¹²³⁴⁵⁶⁷⁸⁹⁰*†‡§#]+\s*)+"
)
_AFFILIATION_LINE_START_RE = re.compile(
    r"^(?:[\d¹²³⁴⁵⁶⁷⁸⁹⁰*†‡§#]+\s*)?(?:"
    r"Department|Faculty|School|Division|Cent(?:er|re)|"
    r"(?:[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’&.*\-]*\s+){0,5}"
    r"(?:University|Institute|Institut|Laboratory|College|Academy)"
    r")\b"
)
_AFFILIATION_PATTERNS = (
    re.compile(
        r"\b[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’&.*\-]*(?:\s+(?:[A-ZÀ-ÖØ-Þ]"
        r"[A-Za-zÀ-ÖØ-öø-ÿ'’&.*\-]*|of|the|and|&)){0,5}\s+"
        r"Academy\s+of\s+[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’&.*\-]*"
        r"(?:\s+(?:[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’&.*\-]*|"
        r"of|the|and|&)){0,5}",
    ),
    re.compile(
        r"\b[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’&.*\-]*(?:\s+(?:[A-ZÀ-ÖØ-Þ]"
        r"[A-Za-zÀ-ÖØ-öø-ÿ'’&.*\-]*|of|the|and|&)){0,6}\s+"
        r"(?:Institute|Institut)\s+(?:of|for|für|de)\s+"
        r"[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’&.*\-]*(?:\s+(?:[A-ZÀ-ÖØ-Þ]"
        r"[A-Za-zÀ-ÖØ-öø-ÿ'’&.*\-]*|of|the|and|&)){0,7}",
    ),
    re.compile(
        r"\b[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’&.*\-]*(?:\s+(?:[A-ZÀ-ÖØ-Þ]"
        r"[A-Za-zÀ-ÖØ-öø-ÿ'’&.*\-]*|of|the|and)){0,6}\s+University"
        r"(?:\s+(?:of|at)\s+[A-ZÀ-ÖØ-Þ]"
        r"[A-Za-zÀ-ÖØ-öø-ÿ'’&.*\-]*(?:\s+(?:[A-ZÀ-ÖØ-Þ]"
        r"[A-Za-zÀ-ÖØ-öø-ÿ'’&.*\-]*|of|the|and|at|&)){0,6})?",
    ),
    re.compile(
        r"\b(?:University of|Université de|Universität(?: der)?|"
        r"Universidade (?:de|do|da)|Università (?:di|degli Studi di))\s+"
        r"[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’&.\-]*(?:\s+(?:[A-ZÀ-ÖØ-Þ]"
        r"[A-Za-zÀ-ÖØ-öø-ÿ'’&.\-]*|of|the|and|at|de|do|da|di)){0,7}",
    ),
    re.compile(
        r"\b[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’&.\-]*(?:\s+(?:[A-ZÀ-ÖØ-Þ]"
        r"[A-Za-zÀ-ÖØ-öø-ÿ'’&.\-]*|of|the|and|&)){0,8}\s+"
        r"(?:University|Institute of Technology|Institute|Laboratory|"
        r"College|Academy)\b",
    ),
    re.compile(
        r"\b(?:Institute|Institut)\s+(?:of|for|für|de)\s+"
        r"[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’&.*\-]*(?:\s+(?:[A-ZÀ-ÖØ-Þ]"
        r"[A-Za-zÀ-ÖØ-öø-ÿ'’&.*\-]*|of|the|and|&)){0,7}",
    ),
)
_AFFILIATION_FALSE_POSITIVES = {
    "autonomous laboratory",
    "china academy",
    "chinese academy",
    "computer college",
    "deemed university",
    "huazhong university of science",
    "key laboratory",
    "national academy",
    "national key laboratory",
    "state key laboratory",
    "supporting information",
    "supplementary information",
    "the state key laboratory",
    "university of science and technology",
    "national institutes of health",
}
_AFFILIATION_BIOGRAPHY_RE = re.compile(
    r"\b(?:received|obtained|earned|holds?)\s+(?:the|his|her|a)?\s*"
    r"(?:B\.?S\.?|M\.?S\.?|Ph\.?D\.?|degree|degrees)\b|"
    r"\b(?:research interests|member,\s*IEEE|was born|graduated from)\b",
    re.IGNORECASE,
)
_AFFILIATION_ORG_UNIT_RE = re.compile(
    r"\b(?:Department|Faculty|School|Division)\b",
    re.IGNORECASE,
)
_AFFILIATION_GRANT_CONTEXT_RE = re.compile(
    r"^(?:open foundation|project|major key project|fund|grant)\s+of\b",
    re.IGNORECASE,
)
_CORRESPONDING_AUTHOR_RE = re.compile(
    r"\bcorresponding\s+author(?:s)?\b",
    re.IGNORECASE,
)
_CORRESPONDING_AUTHOR_WINDOW_BEFORE = 350
_CORRESPONDING_AUTHOR_WINDOW_AFTER = 500


@lru_cache(maxsize=1)
def load_sdl_entities(path: str | Path | None = None) -> dict[str, dict[str, str]]:
    """Return {entity_type: {matchable term: canonical name}}.

    Terms include the canonical name itself plus every alias of length
    >= MIN_TERM_LEN.
    """
    from app.config import settings

    p = Path(path or settings.sdl_entities_yaml)
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    vocab: dict[str, dict[str, str]] = {}
    for section, entity_type in _SECTION_TO_TYPE.items():
        terms: dict[str, str] = {}
        for entry in raw.get(section) or []:
            canonical = str(entry["name"]).strip()
            surfaces = [canonical, *(str(a).strip() for a in entry.get("aliases") or [])]
            for surface in surfaces:
                if len(surface) < MIN_TERM_LEN:
                    continue
                terms[surface] = canonical
        vocab[entity_type] = terms
    return vocab


@lru_cache(maxsize=1)
def load_sdl_entity_meta(
    path: str | Path | None = None,
) -> dict[str, dict[str, dict]]:
    """Return {entity_type: {canonical name: {"category": str | None}}}."""
    from app.config import settings

    p = Path(path or settings.sdl_entities_yaml)
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    meta: dict[str, dict[str, dict]] = {}
    for section, entity_type in _SECTION_TO_TYPE.items():
        meta[entity_type] = {
            str(entry["name"]).strip(): {"category": entry.get("category")}
            for entry in raw.get(section) or []
        }
    return meta


@lru_cache(maxsize=1)
def load_method_stages(path: str | Path | None = None) -> dict[str, list[str]]:
    """Return {stage_id: [keyword stems]}, in file order = priority order."""
    from app.config import settings

    p = Path(path or settings.method_stages_yaml)
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {
        stage_id: [str(k).lower() for k in (spec.get("keywords") or [])]
        for stage_id, spec in (raw.get("stages") or {}).items()
    }


def reset_sdl_entities_cache() -> None:
    load_sdl_entities.cache_clear()
    load_sdl_entity_meta.cache_clear()
    load_method_stages.cache_clear()
    load_institution_aliases.cache_clear()


@lru_cache(maxsize=1)
def load_institution_aliases(
    path: str | Path | None = None,
) -> tuple[tuple[str, str], ...]:
    """Return normalized alias/canonical pairs for affiliation normalization."""
    from app.config import settings

    csv_path = Path(path or settings.institutions_csv)
    aliases: dict[str, str] = {}
    with csv_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            canonical = str(row.get("canonical_name") or "").strip()
            if not canonical:
                continue
            surfaces = [
                canonical,
                *[
                    part.strip()
                    for part in str(row.get("aliases") or "").split(";")
                    if part.strip()
                ],
            ]
            for surface in surfaces:
                normalized = normalize_institution(surface)
                if normalized:
                    aliases.setdefault(normalized, canonical)
    return tuple(
        sorted(
            aliases.items(),
            key=lambda item: (-len(item[0]), item[0]),
        )
    )


def _clean_affiliation_text(text: str) -> str:
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"[*_`#]", "", clean)
    clean = _AFFILIATION_PREFIX_RE.sub("", clean)
    return re.sub(r"\s+", " ", clean).strip(" .:-")


def _has_adjacent_repeated_phrase(
    normalized: str,
    *,
    min_width: int = 1,
) -> bool:
    tokens = normalized.split()
    for width in range(min_width, len(tokens) // 2 + 1):
        for start in range(0, len(tokens) - 2 * width + 1):
            if (
                tokens[start : start + width]
                == tokens[start + width : start + 2 * width]
            ):
                return True
    return False


def _is_valid_affiliation_candidate(candidate: str) -> bool:
    normalized = normalize_institution(candidate)
    words = candidate.split()
    if (
        len(words) < 2
        or len(words) > 12
        or normalized in _AFFILIATION_FALSE_POSITIVES
        or "key laboratory" in normalized
        or _AFFILIATION_ORG_UNIT_RE.search(candidate)
        or _AFFILIATION_GRANT_CONTEXT_RE.search(candidate)
        or _has_adjacent_repeated_phrase(normalized)
    ):
        return False
    marker_count = len(_AFFILIATION_MARKER_RE.findall(candidate))
    if marker_count != 1:
        return False
    if re.search(r"\band\s+the\b", candidate, re.IGNORECASE):
        return False
    if re.search(r"\bAcademy\b", candidate, re.IGNORECASE) and not re.search(
        r"\bAcademy\s+of\b", candidate, re.IGNORECASE
    ):
        return False
    return True


def _alias_affiliations(text: str) -> list[tuple[str, str]]:
    """Return (surface, canonical) known institutions mentioned in one line."""
    normalized_text = normalize_institution(text)
    matches: list[tuple[str, str]] = []
    seen: set[str] = set()
    for alias, canonical in load_institution_aliases():
        pattern = re.compile(
            rf"(?<!\w){re.escape(alias)}(?!\w)",
            re.IGNORECASE | re.UNICODE,
        )
        hit = pattern.search(normalized_text)
        if hit is None or canonical in seen:
            continue
        seen.add(canonical)
        matches.append((canonical, canonical))
    return matches


def _pattern_affiliations(text: str) -> list[str]:
    candidates: list[str] = []
    for segment in _AFFILIATION_LINE_SPLIT_RE.split(text):
        cleaned = _clean_affiliation_text(segment)
        if not cleaned or len(cleaned) > 180:
            continue
        for pattern in _AFFILIATION_PATTERNS:
            for match in pattern.finditer(cleaned):
                candidate = _clean_affiliation_text(match.group(0))
                candidate = re.sub(
                    r"^The\s+(?=University|Institute|Institut)",
                    "",
                    candidate,
                )
                if not _is_valid_affiliation_candidate(candidate):
                    continue
                candidates.append(candidate)
    return list(dict.fromkeys(candidates))


def _frontmatter_institutions(
    chunks: list[PaperChunk],
) -> dict[str, dict]:
    """Extract paper-level affiliation mentions from front matter only."""
    found: dict[str, dict] = {}
    scanned = 0
    for chunk in chunks:
        if chunk.section_type != "unknown":
            continue
        remaining = AFFILIATION_FRONTMATTER_MAX_CHARS - scanned
        if remaining <= 0:
            break
        text = chunk.chunk_text[:remaining]
        scanned += len(text)
        for raw_line in text.splitlines():
            line = _clean_affiliation_text(raw_line)
            if not line or len(line) > 5_000:
                continue
            if (
                _AFFILIATION_BIOGRAPHY_RE.search(line)
                or _has_adjacent_repeated_phrase(
                    normalize_institution(line),
                    min_width=2,
                )
            ):
                continue
            alias_matches = _alias_affiliations(line)
            marker_count = len(_AFFILIATION_MARKER_RE.findall(line))
            has_marker = marker_count > 0
            if not alias_matches and not has_marker:
                continue
            exact_known_alias = normalize_institution(line) in {
                alias for alias, _canonical in load_institution_aliases()
            }
            has_affiliation_segment = any(
                _AFFILIATION_LINE_START_RE.search(
                    _clean_affiliation_text(segment)
                )
                is not None
                for segment in _AFFILIATION_LINE_SPLIT_RE.split(line)
            )
            if (
                marker_count < 2
                and (
                    not has_affiliation_segment
                    or "," not in line
                )
                and not exact_known_alias
            ):
                continue
            known_canonicals = {canonical for _, canonical in alias_matches}
            for surface, canonical in alias_matches:
                found[canonical] = {
                    "name": surface,
                    "confidence": AFFILIATION_CONFIDENCE_ALIAS,
                    "chunk_id": chunk.id,
                    "section": chunk.section_type,
                    "usage_snippet": line[:USAGE_SNIPPET_MAX_CHARS],
                    "extractor": "frontmatter_affiliation_v2",
                }
            for candidate in (
                _pattern_affiliations(line) if has_marker else []
            ):
                normalized = normalize_institution(candidate)
                canonical = next(
                    (
                        known
                        for known in known_canonicals
                        if normalize_institution(known) in normalized
                        or normalized in normalize_institution(known)
                    ),
                    candidate,
                )
                found.setdefault(
                    canonical,
                    {
                        "name": candidate,
                        "confidence": AFFILIATION_CONFIDENCE_PATTERN,
                        "chunk_id": chunk.id,
                        "section": chunk.section_type,
                        "usage_snippet": line[:USAGE_SNIPPET_MAX_CHARS],
                        "extractor": "frontmatter_affiliation_v2",
                    },
                )
    for candidate in list(found):
        info = found[candidate]
        if info["confidence"] > AFFILIATION_CONFIDENCE_PATTERN:
            continue
        normalized = normalize_institution(candidate)
        if any(
            other != candidate
            and normalized
            and normalized in normalize_institution(other)
            and len(normalize_institution(other)) > len(normalized) + 3
            for other in found
        ):
            del found[candidate]
    return found


def _normalized_evidence_text(value: str) -> str:
    normalized = strip_diacritics(value).lower()
    normalized = re.sub(r"[^\w\s\-]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _extract_corresponding_author_evidence(
    paper: Paper,
    chunks: list[PaperChunk],
) -> dict:
    """Confirm corresponding authors only from explicit PDF text evidence."""
    authors = sorted(
        paper.authors,
        key=lambda paper_author: (
            paper_author.author_order,
            paper_author.author_id,
        ),
    )
    author_names = {
        paper_author.author_id: normalize_name(
            paper_author.author.canonical_name
        )
        for paper_author in authors
    }
    surname_counts: dict[str, int] = {}
    for normalized_name in author_names.values():
        surname = normalized_name.split()[-1] if normalized_name else ""
        if len(surname) >= 3:
            surname_counts[surname] = surname_counts.get(surname, 0) + 1

    evidence_by_author: dict[str, dict] = {}
    scanned = 0
    for chunk in chunks:
        if chunk.section_type != "unknown":
            continue
        remaining = AFFILIATION_FRONTMATTER_MAX_CHARS - scanned
        if remaining <= 0:
            break
        text = chunk.chunk_text[:remaining]
        scanned += len(text)
        for marker in _CORRESPONDING_AUTHOR_RE.finditer(text):
            start = max(0, marker.start() - _CORRESPONDING_AUTHOR_WINDOW_BEFORE)
            end = min(
                len(text),
                marker.end() + _CORRESPONDING_AUTHOR_WINDOW_AFTER,
            )
            window = text[start:end]
            normalized_window = _normalized_evidence_text(window)
            normalized_marker_position = len(
                _normalized_evidence_text(text[start : marker.start()])
            )
            normalized_marker_end_position = len(
                _normalized_evidence_text(text[start : marker.end()])
            )
            full_matches: list[tuple[int, int, str]] = []
            for author_id, normalized_name in author_names.items():
                if not normalized_name:
                    continue
                name_matches = list(re.finditer(
                    rf"(?<!\w){re.escape(normalized_name)}(?!\w)",
                    normalized_window,
                ))
                if not name_matches:
                    continue
                full_matches.append(
                    (
                        0
                        if any(
                            name_match.start()
                            >= normalized_marker_end_position
                            for name_match in name_matches
                        )
                        else 1,
                        min(
                            min(
                                abs(
                                    name_match.start()
                                    - normalized_marker_position
                                ),
                                abs(
                                    name_match.end()
                                    - normalized_marker_position
                                ),
                            )
                            for name_match in name_matches
                        ),
                        author_id,
                    )
                )
            matched_author_ids = (
                [min(full_matches)[2]] if full_matches else []
            )
            if not matched_author_ids:
                surname_matches: list[tuple[int, int, str]] = []
                for author_id, normalized_name in author_names.items():
                    if not normalized_name:
                        continue
                    surname = normalized_name.split()[-1]
                    surname_matches_for_author = list(re.finditer(
                        rf"(?<!\w){re.escape(surname)}(?!\w)",
                        normalized_window,
                    ))
                    if (
                        surname_counts.get(surname) == 1
                        and surname_matches_for_author
                    ):
                        surname_matches.append(
                            (
                                0
                                if any(
                                    surname_match.start()
                                    >= normalized_marker_end_position
                                    for surname_match in (
                                        surname_matches_for_author
                                    )
                                )
                                else 1,
                                min(
                                    min(
                                        abs(
                                            surname_match.start()
                                            - normalized_marker_position
                                        ),
                                        abs(
                                            surname_match.end()
                                            - normalized_marker_position
                                        ),
                                    )
                                    for surname_match in (
                                        surname_matches_for_author
                                    )
                                ),
                                author_id,
                            )
                        )
                if surname_matches:
                    matched_author_ids = [min(surname_matches)[2]]
            for author_id in matched_author_ids:
                paper_author = next(
                    candidate
                    for candidate in authors
                    if candidate.author_id == author_id
                )
                evidence_by_author.setdefault(
                    author_id,
                    {
                        "author_id": author_id,
                        "author_name": paper_author.author.canonical_name,
                        "author_order": paper_author.author_order,
                        "evidence_chunk_id": chunk.id,
                        "evidence_snippet": re.sub(
                            r"\s+",
                            " ",
                            window,
                        ).strip()[:USAGE_SNIPPET_MAX_CHARS],
                    },
                )
    return {
        "extractor": "pdf_frontmatter_corresponding_author_v1",
        "evidence_available": bool(evidence_by_author),
        "authors": sorted(
            evidence_by_author.values(),
            key=lambda item: (item["author_order"], item["author_id"]),
        ),
    }


def _sentence_around(text: str, start: int, end: int) -> str:
    """The sentence containing text[start:end], split naively on '. '."""
    s = text.rfind(". ", 0, start)
    s = s + 2 if s != -1 else 0
    e = text.find(". ", end)
    e = e + 1 if e != -1 else len(text)
    return text[s:e].strip()


def _detect_stage(sentence: str) -> str | None:
    """First stage (in method_stages.yaml priority order) whose keyword stems
    appear in the sentence, case-insensitive substring; None if no match."""
    low = sentence.lower()
    for stage_id, keywords in load_method_stages().items():
        if any(k in low for k in keywords):
            return stage_id
    return None


def extract_entities_for_paper(session: Session, paper: Paper) -> list[PaperEntity]:
    """Replace and return the typed entities for one paper."""
    vocab = load_sdl_entities()
    # (entity_type, canonical) → best evidence so far
    best: dict[tuple[str, str], dict] = {}

    def scan(
        text: str | None,
        confidence: float,
        chunk_id: str | None = None,
        section: str | None = None,
    ) -> None:
        if not text:
            return
        for entity_type, terms in vocab.items():
            for term, canonical in terms.items():
                hits = find_term_hits(text, term)
                if not hits:
                    continue
                stage = None
                snippet = None
                hit = hits[0]
                if entity_type == "method":
                    # Among this text's hits, prefer one whose sentence
                    # matches a stage; keep the first hit's sentence otherwise.
                    snippet = _sentence_around(text, hit.start, hit.end)
                    for h in hits:
                        sentence = _sentence_around(text, h.start, h.end)
                        h_stage = _detect_stage(sentence)
                        if h_stage is not None:
                            hit, stage, snippet = h, h_stage, sentence
                            break
                    snippet = snippet[:USAGE_SNIPPET_MAX_CHARS]
                key = (entity_type, canonical)
                current = best.get(key)
                rank = (stage is not None, confidence)
                if current is None or rank > current["rank"]:
                    best[key] = {
                        "name": text[hit.start : hit.end],
                        "confidence": confidence,
                        "chunk_id": chunk_id,
                        "section": section,
                        "stage": stage,
                        "usage_snippet": snippet,
                        "rank": rank,
                    }

    scan(paper.title, CONFIDENCE_TITLE)
    scan(paper.abstract, CONFIDENCE_ABSTRACT)
    chunks = session.execute(
        select(PaperChunk).where(PaperChunk.paper_id == paper.id)
    ).scalars().all()
    for chunk in chunks:
        scan(
            chunk.chunk_text,
            CONFIDENCE_CHUNK,
            chunk_id=chunk.id,
            section=chunk.section_type,
        )

    for canonical, info in _frontmatter_institutions(chunks).items():
        best[("institution", canonical)] = {
            **info,
            "stage": None,
            "rank": (False, info["confidence"]),
        }

    raw_metadata = dict(paper.raw_metadata or {})
    raw_metadata["corresponding_author_evidence"] = (
        _extract_corresponding_author_evidence(paper, chunks)
    )
    paper.raw_metadata = raw_metadata

    session.execute(
        PaperEntity.__table__.delete().where(PaperEntity.paper_id == paper.id)
    )
    rows = [
        PaperEntity(
            id=f"ent_{uuid.uuid4().hex[:12]}",
            paper_id=paper.id,
            entity_type=entity_type,
            name=info["name"],
            normalized_name=canonical,
            evidence_chunk_id=info["chunk_id"],
            section=info["section"],
            confidence=info["confidence"],
            extractor=info.get("extractor", "vocabulary"),
            stage=info["stage"],
            usage_snippet=info["usage_snippet"],
        )
        for (entity_type, canonical), info in sorted(best.items())
    ]
    session.add_all(rows)
    session.flush()
    from app.services.jev_advisory_service import graph_advice
    graph_advice(session, paper, rows)
    return rows


def run_entity_extraction(
    session: Session,
    paper_ids: list[str] | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> dict:
    """Extract entities for all (or the given) papers. Returns summary counts.

    `limit`/`offset` slice the corpus ordered by paper id, so large runs can be
    chunked into successive batches.
    """
    stmt = select(Paper)
    if paper_ids:
        stmt = stmt.where(Paper.id.in_(paper_ids))
    if limit is not None or offset is not None:
        stmt = stmt.order_by(Paper.id).offset(offset).limit(limit)
    papers = list(session.execute(stmt).scalars())

    by_type: dict[str, int] = {}
    total = 0
    for paper in papers:
        rows = extract_entities_for_paper(session, paper)
        total += len(rows)
        for row in rows:
            by_type[row.entity_type] = by_type.get(row.entity_type, 0) + 1
    return {
        "papers_processed": len(papers),
        "entities": total,
        "by_type": by_type,
    }
