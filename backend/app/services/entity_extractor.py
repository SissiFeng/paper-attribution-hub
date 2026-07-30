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

The catalyst pilot additionally uses the versioned SDL ontology to preserve
specific catalyst subtypes, source-relative mention offsets, sentence evidence,
and conservative proposed reaction/composition relations. ``PaperEntity``
remains the compatibility roll-up.

Extraction is idempotent. Compatibility roll-ups are replaced, while reviewed
or manually maintained relation evidence is retained across source changes.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Paper,
    PaperChunk,
    PaperEntity,
    PaperEntityExtractionState,
    PaperEntityMention,
    PaperEntityRelation,
)
from app.services.ontology_service import (
    concept,
    concept_ancestors,
    load_ontology,
    match_ontology_concepts,
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

CATALYST_ROOT_CONCEPT_ID = "material:catalyst"
CATALYST_EXTRACTOR_VERSION = "catalyst-pilot/1.0"

_FORMULA_TOKEN_RE = re.compile(r"(?<![A-Za-z])[A-Z][A-Za-z0-9().,+/\-]{1,49}")
_NON_CATALYST_FORMULAS = {
    "CH4",
    "CO",
    "CO2",
    "H2",
    "H2O",
    "N2",
    "NH3",
    "NO",
    "NO2",
    "O2",
}
_ELEMENT_SYMBOLS = {
    "Ac", "Ag", "Al", "Am", "Ar", "As", "At", "Au", "B", "Ba", "Be", "Bh",
    "Bi", "Bk", "Br", "C", "Ca", "Cd", "Ce", "Cf", "Cl", "Cm", "Cn", "Co",
    "Cr", "Cs", "Cu", "Db", "Ds", "Dy", "Er", "Es", "Eu", "F", "Fe", "Fl",
    "Fm", "Fr", "Ga", "Gd", "Ge", "H", "He", "Hf", "Hg", "Ho", "Hs", "I",
    "In", "Ir", "K", "Kr", "La", "Li", "Lr", "Lu", "Lv", "Mc", "Md", "Mg",
    "Mn", "Mo", "Mt", "N", "Na", "Nb", "Nd", "Ne", "Nh", "Ni", "No", "Np",
    "O", "Og", "Os", "P", "Pa", "Pb", "Pd", "Pm", "Po", "Pr", "Pt", "Pu",
    "Ra", "Rb", "Re", "Rf", "Rg", "Rh", "Rn", "Ru", "S", "Sb", "Sc", "Se",
    "Sg", "Si", "Sm", "Sn", "Sr", "Ta", "Tb", "Tc", "Te", "Th", "Ti", "Tl",
    "Tm", "Ts", "U", "V", "W", "Xe", "Y", "Yb", "Zn", "Zr",
}


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
    _catalyst_canonical_names.cache_clear()
    extraction_config_fingerprint.cache_clear()


def _sentence_around(text: str, start: int, end: int) -> str:
    """The sentence containing text[start:end]."""
    sentence, _, _ = _sentence_bounds(text, start, end)
    return sentence


def _sentence_bounds(text: str, start: int, end: int) -> tuple[str, int, int]:
    """Return stripped sentence text and its source-relative bounds."""
    s = text.rfind(". ", 0, start)
    s = s + 2 if s != -1 else 0
    e = text.find(". ", end)
    e = e + 1 if e != -1 else len(text)
    while s < e and text[s].isspace():
        s += 1
    while e > s and text[e - 1].isspace():
        e -= 1
    return text[s:e], s, e


def _detect_stage(sentence: str) -> str | None:
    """First stage (in method_stages.yaml priority order) whose keyword stems
    appear in the sentence, case-insensitive substring; None if no match."""
    low = sentence.lower()
    for stage_id, keywords in load_method_stages().items():
        if any(k in low for k in keywords):
            return stage_id
    return None


def _stable_id(prefix: str, *parts: object) -> str:
    identity = "|".join("" if part is None else str(part) for part in parts)
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}_{digest}"


@lru_cache(maxsize=1)
def extraction_config_fingerprint() -> str:
    """Hash non-ontology configuration that changes compatibility entities."""
    from app.config import settings

    digest = hashlib.sha256()
    for name, path in (
        ("sdl_entities", settings.sdl_entities_yaml),
        ("method_stages", settings.method_stages_yaml),
    ):
        digest.update(name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def paper_source_fingerprint(
    paper: Paper,
    chunks: list[PaperChunk],
) -> str:
    """Hash paper sources plus every config that determines extraction."""
    digest = hashlib.sha256()
    values = [
        extraction_config_fingerprint(),
        paper.title or "",
        paper.abstract or "",
    ]
    for chunk in sorted(chunks, key=lambda item: item.id):
        values.extend(
            [
                chunk.id,
                chunk.section_type or "",
                chunk.chunk_text or "",
            ]
        )
    for value in values:
        encoded = value.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def stale_paper_ids(session: Session) -> list[str]:
    """Return papers whose source fingerprint or extraction version is stale."""
    papers = list(session.execute(select(Paper).order_by(Paper.id)).scalars())
    states = {
        state.paper_id: state
        for state in session.execute(select(PaperEntityExtractionState)).scalars()
    }
    chunks_by_paper: dict[str, list[PaperChunk]] = defaultdict(list)
    for chunk in session.execute(
        select(PaperChunk).order_by(PaperChunk.paper_id, PaperChunk.id)
    ).scalars():
        chunks_by_paper[chunk.paper_id].append(chunk)
    ontology_version = load_ontology()["ontology_version"]
    stale: list[str] = []
    for paper in papers:
        state = states.get(paper.id)
        fingerprint = paper_source_fingerprint(
            paper,
            chunks_by_paper.get(paper.id, []),
        )
        if (
            state is None
            or state.ontology_version != ontology_version
            or state.extractor_version != CATALYST_EXTRACTOR_VERSION
            or state.config_fingerprint != extraction_config_fingerprint()
            or state.source_fingerprint != fingerprint
        ):
            stale.append(paper.id)
    return stale


def _is_catalyst_concept(concept_id: str) -> bool:
    return concept_id == CATALYST_ROOT_CONCEPT_ID or (
        CATALYST_ROOT_CONCEPT_ID in concept_ancestors(concept_id)
    )


@lru_cache(maxsize=1)
def _catalyst_canonical_names() -> frozenset[str]:
    return frozenset(
        spec["name"]
        for concept_id, spec in load_ontology()["concepts"].items()
        if _is_catalyst_concept(concept_id)
    )


def _parse_formula_elements(raw: str) -> list[str] | None:
    """Parse only explicit chemical symbols; never infer stoichiometry."""
    if raw in _NON_CATALYST_FORMULAS:
        return None
    elements: list[str] = []
    index = 0
    while index < len(raw):
        char = raw[index]
        if char.isupper():
            two = raw[index : index + 2]
            if len(two) == 2 and two in _ELEMENT_SYMBOLS:
                symbol = two
                index += 2
            elif char in _ELEMENT_SYMBOLS:
                symbol = char
                index += 1
            else:
                return None
            if symbol not in elements:
                elements.append(symbol)
            continue
        if char.isdigit() or char in ".(),+/-xyz":
            index += 1
            continue
        return None
    return elements if len(elements) >= 2 else None


def _composition_before(text: str, mention_start: int) -> dict | None:
    """Return the nearest valid formula immediately preceding a catalyst."""
    window_start = max(0, mention_start - 80)
    prefix = text[window_start:mention_start]
    for match in reversed(list(_FORMULA_TOKEN_RE.finditer(prefix))):
        between = prefix[match.end() :]
        if len(between) > 35 or not re.fullmatch(
            r"[\s,;:()\-]*(?:based|supported)?[\s,;:()\-]*",
            between,
            flags=re.IGNORECASE,
        ):
            continue
        raw = match.group(0).rstrip(".,;:")
        elements = _parse_formula_elements(raw)
        if elements:
            return {"raw": raw, "elements": elements}
    return None


def _span_distance(
    first_start: int,
    first_end: int,
    second_start: int,
    second_end: int,
) -> int:
    if first_end <= second_start:
        return second_start - first_end
    if second_end <= first_start:
        return first_start - second_end
    return 0


def extract_entities_for_paper(session: Session, paper: Paper) -> list[PaperEntity]:
    """Replace and return the typed entities for one paper."""
    vocab = load_sdl_entities()
    ontology_version = load_ontology()["ontology_version"]
    existing_mentions = {
        mention.id: mention
        for mention in session.execute(
            select(PaperEntityMention).where(
                PaperEntityMention.paper_id == paper.id
            )
        ).scalars()
    }
    existing_relations = {
        relation.id: relation
        for relation in session.execute(
            select(PaperEntityRelation)
            .join(
                PaperEntityMention,
                PaperEntityMention.id == PaperEntityRelation.subject_mention_id,
            )
            .where(PaperEntityMention.paper_id == paper.id)
        ).scalars()
    }
    existing_relation_statuses = {
        relation_id: relation.status
        for relation_id, relation in existing_relations.items()
    }
    # (entity_type, canonical) → best evidence so far
    best: dict[tuple[str, str], dict] = {}
    mentions: dict[str, PaperEntityMention] = {}
    relations: dict[str, PaperEntityRelation] = {}

    def scan(
        text: str | None,
        confidence: float,
        source_kind: str,
        chunk_id: str | None = None,
        section: str | None = None,
    ) -> None:
        if not text:
            return
        catalyst_matches = [
            match
            for match in match_ontology_concepts(text, "material")
            if not match["negated"] and _is_catalyst_concept(match["concept_id"])
        ]
        for entity_type, terms in vocab.items():
            for term, canonical in terms.items():
                if (
                    entity_type == "material"
                    and canonical in _catalyst_canonical_names()
                ):
                    continue
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

        for match in catalyst_matches:
            concept_id = match["concept_id"]
            concept_spec = concept(concept_id)
            if concept_spec is None:
                continue
            sentence, sentence_start, sentence_end = _sentence_bounds(
                text,
                match["start"],
                match["end"],
            )
            mention_id = _stable_id(
                "mention",
                paper.id,
                source_kind,
                chunk_id,
                ontology_version,
                concept_id,
                match["start"],
                match["end"],
                sentence,
            )
            specificity = (
                "generic"
                if concept_id == CATALYST_ROOT_CONCEPT_ID
                else "subtype"
            )
            mentions[mention_id] = PaperEntityMention(
                id=mention_id,
                paper_id=paper.id,
                entity_type="material",
                concept_id=concept_id,
                normalized_name=concept_spec["name"],
                surface_form=match["surface"],
                source_kind=source_kind,
                evidence_chunk_id=chunk_id,
                section=section,
                start_char=match["start"],
                end_char=match["end"],
                evidence_text=sentence,
                confidence=confidence,
                specificity=specificity,
                extractor="ontology_longest_match",
                extractor_version=CATALYST_EXTRACTOR_VERSION,
                ontology_version=ontology_version,
            )
            key = ("material", concept_spec["name"])
            current = best.get(key)
            rank = (specificity == "subtype", confidence)
            if current is None or rank > current["rank"]:
                best[key] = {
                    "name": match["surface"],
                    "confidence": confidence,
                    "chunk_id": chunk_id,
                    "section": section,
                    "stage": None,
                    "usage_snippet": None,
                    "rank": rank,
                }

            for reaction in match_ontology_concepts(sentence, "reaction"):
                if reaction["negated"]:
                    continue
                reaction_start = sentence_start + reaction["start"]
                reaction_end = sentence_start + reaction["end"]
                nearby_catalysts = [
                    candidate
                    for candidate in catalyst_matches
                    if sentence_start <= candidate["start"] < sentence_end
                ]
                distances = [
                    (
                        _span_distance(
                            candidate["start"],
                            candidate["end"],
                            reaction_start,
                            reaction_end,
                        ),
                        candidate,
                    )
                    for candidate in nearby_catalysts
                ]
                nearest_distance = min(distance for distance, _ in distances)
                nearest = [
                    candidate
                    for distance, candidate in distances
                    if distance == nearest_distance
                ]
                if len(nearest) != 1 or nearest[0] is not match:
                    continue
                relation_id = _stable_id(
                    "relation",
                    mention_id,
                    "catalyzes",
                    reaction["concept_id"],
                )
                relations[relation_id] = PaperEntityRelation(
                    id=relation_id,
                    subject_mention_id=mention_id,
                    predicate="catalyzes",
                    object_concept_id=reaction["concept_id"],
                    object_value=None,
                    object_metadata={
                        "surface_form": reaction["surface"],
                        "sentence_start_char": sentence_start,
                        "sentence_end_char": sentence_end,
                    },
                    confidence=confidence,
                    status=existing_relation_statuses.get(
                        relation_id,
                        "proposed",
                    ),
                    extractor="ontology_nearest_relation",
                    extractor_version=CATALYST_EXTRACTOR_VERSION,
                    ontology_version=ontology_version,
                )

            composition = _composition_before(text, match["start"])
            if composition is not None:
                relation_id = _stable_id(
                    "relation",
                    mention_id,
                    "has_composition",
                    composition["raw"],
                )
                relations[relation_id] = PaperEntityRelation(
                    id=relation_id,
                    subject_mention_id=mention_id,
                    predicate="has_composition",
                    object_concept_id=None,
                    object_value=composition["raw"],
                    object_metadata={"elements": composition["elements"]},
                    confidence=confidence,
                    status=existing_relation_statuses.get(
                        relation_id,
                        "proposed",
                    ),
                    extractor="ontology_nearest_relation",
                    extractor_version=CATALYST_EXTRACTOR_VERSION,
                    ontology_version=ontology_version,
                )

    scan(paper.title, CONFIDENCE_TITLE, "title")
    scan(paper.abstract, CONFIDENCE_ABSTRACT, "abstract")
    chunks = list(
        session.execute(
            select(PaperChunk)
            .where(PaperChunk.paper_id == paper.id)
            .order_by(PaperChunk.id)
        ).scalars()
    )
    for chunk in chunks:
        scan(
            chunk.chunk_text,
            CONFIDENCE_CHUNK,
            "chunk",
            chunk_id=chunk.id,
            section=chunk.section_type,
        )

    retained_mention_ids = set(mentions)
    for relation_id, relation in existing_relations.items():
        if relation_id in relations:
            continue
        if (
            relation.extractor == "ontology_nearest_relation"
            and relation.status == "proposed"
        ):
            session.delete(relation)
        else:
            retained_mention_ids.add(relation.subject_mention_id)
    for mention_id, mention in existing_mentions.items():
        if mention_id not in retained_mention_ids:
            session.delete(mention)

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
    for mention in mentions.values():
        session.merge(mention)
    for relation in relations.values():
        session.merge(relation)
    session.merge(
        PaperEntityExtractionState(
            paper_id=paper.id,
            ontology_version=ontology_version,
            extractor_version=CATALYST_EXTRACTOR_VERSION,
            config_fingerprint=extraction_config_fingerprint(),
            source_fingerprint=paper_source_fingerprint(paper, chunks),
            extracted_at=datetime.now(UTC),
        )
    )
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
