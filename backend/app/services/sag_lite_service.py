"""SAG-lite derived event view over the existing KB tables.

The upstream SAG shape is event/entity centered. This first local slice keeps
that shape read-only: it derives event nodes from PaperEntity rows and links
them to same-paper entities without adding a migration.
"""
from __future__ import annotations

import re
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Paper,
    PaperChunk,
    PaperEntity,
    PaperEntityExtractionState,
    PaperLabLink,
)
from app.services.entity_extractor import (
    CATALYST_EXTRACTOR_VERSION,
    extraction_config_fingerprint,
)
from app.services.ontology_service import load_ontology

_EVENT_LIMIT = 12
_SNIPPET_CHARS = 260


def _event_id(paper_id: str, entity_type: str, normalized_name: str) -> str:
    raw = f"{paper_id}:{entity_type}:{normalized_name}".lower()
    return "sag_" + re.sub(r"[^a-z0-9]+", "-", raw).strip("-")[:120]


def _compact(text: str | None, limit: int = _SNIPPET_CHARS) -> str:
    value = " ".join((text or "").split())
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "..."


def entity_event_trail(
    session: Session,
    entity_type: str,
    normalized_name: str,
    limit: int = _EVENT_LIMIT,
) -> list[dict]:
    """Return paper-level events for one normalized entity.

    Each event is a derived, deterministic view:
    entity mention -> paper event -> same-paper entity links. It gives the KB a
    SAG-style traversal path without persisting new event tables yet.
    """
    rows = session.execute(
        select(PaperEntity, Paper)
        .join(
            PaperEntityExtractionState,
            PaperEntityExtractionState.paper_id == PaperEntity.paper_id,
        )
        .join(Paper, Paper.id == PaperEntity.paper_id)
        .where(
            PaperEntity.entity_type == entity_type,
            PaperEntity.normalized_name == normalized_name,
            PaperEntityExtractionState.ontology_version
            == load_ontology()["ontology_version"],
            PaperEntityExtractionState.extractor_version
            == CATALYST_EXTRACTOR_VERSION,
            PaperEntityExtractionState.config_fingerprint
            == extraction_config_fingerprint(),
            Paper.updated_at <= PaperEntityExtractionState.extracted_at,
        )
        .order_by(Paper.year, Paper.id)
        .limit(limit)
    ).all()
    if not rows:
        return []

    paper_ids = [paper.id for _, paper in rows]
    chunk_ids = [
        entity.evidence_chunk_id for entity, _ in rows if entity.evidence_chunk_id
    ]

    paper_labs: dict[str, list[str]] = defaultdict(list)
    for paper_id, lab_id in session.execute(
        select(PaperLabLink.paper_id, PaperLabLink.lab_id)
        .where(PaperLabLink.paper_id.in_(paper_ids))
        .order_by(PaperLabLink.lab_id)
    ):
        paper_labs[paper_id].append(lab_id)

    chunks = {}
    if chunk_ids:
        chunks = {
            chunk.id: chunk
            for chunk in session.execute(
                select(PaperChunk).where(PaperChunk.id.in_(chunk_ids))
            ).scalars()
        }

    related: dict[str, list[dict]] = defaultdict(list)
    for entity in session.execute(
        select(PaperEntity)
        .join(
            PaperEntityExtractionState,
            PaperEntityExtractionState.paper_id == PaperEntity.paper_id,
        )
        .join(Paper, Paper.id == PaperEntity.paper_id)
        .where(
            PaperEntity.paper_id.in_(paper_ids),
            PaperEntityExtractionState.ontology_version
            == load_ontology()["ontology_version"],
            PaperEntityExtractionState.extractor_version
            == CATALYST_EXTRACTOR_VERSION,
            PaperEntityExtractionState.config_fingerprint
            == extraction_config_fingerprint(),
            Paper.updated_at <= PaperEntityExtractionState.extracted_at,
        )
        .order_by(PaperEntity.entity_type, PaperEntity.normalized_name)
    ).scalars():
        if (
            entity.entity_type == entity_type
            and entity.normalized_name == normalized_name
        ):
            continue
        item = {
            "entity_type": entity.entity_type,
            "name": entity.normalized_name,
        }
        if item not in related[entity.paper_id]:
            related[entity.paper_id].append(item)

    events: list[dict] = []
    for entity, paper in rows:
        chunk = chunks.get(entity.evidence_chunk_id)
        snippet = _compact(
            entity.usage_snippet
            or (chunk.chunk_text if chunk is not None else None)
            or paper.abstract
            or paper.title
        )
        events.append(
            {
                "id": _event_id(paper.id, entity_type, normalized_name),
                "event_type": (
                    f"stage:{entity.stage}" if entity.stage else "entity_mention"
                ),
                "paper_id": paper.id,
                "paper_title": paper.title,
                "year": paper.year,
                "labs": paper_labs.get(paper.id, []),
                "entity_type": entity_type,
                "entity": normalized_name,
                "stage": entity.stage,
                "source_chunk_id": entity.evidence_chunk_id,
                "snippet": snippet,
                "related_entities": related.get(paper.id, []),
            }
        )
    return events
