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

import uuid
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Paper, PaperChunk, PaperEntity
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
    ).scalars()
    for chunk in chunks:
        scan(
            chunk.chunk_text,
            CONFIDENCE_CHUNK,
            chunk_id=chunk.id,
            section=chunk.section_type,
        )

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
            extractor="vocabulary",
            stage=info["stage"],
            usage_snippet=info["usage_snippet"],
        )
        for (entity_type, canonical), info in sorted(best.items())
    ]
    session.add_all(rows)
    session.flush()
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
