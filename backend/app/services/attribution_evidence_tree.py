"""Derive a read-only Attribution Evidence Tree from normalized evidence paths."""

from __future__ import annotations

import hashlib
import json
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.attribution_evidence_contract import ATTRIBUTION_EVIDENCE_METADATA_VERSION
from app.models import Paper, PaperChunk, PaperEvidence, PaperSection
from app.schemas import (
    AttributionEvidencePathOut,
    AttributionEvidenceTreeOut,
    AttributionTreeNodeOut,
)
from app.services.attribution_evidence_scoring import (
    has_ac_funding_in_text,
    score_attribution_evidence,
)

TREE_VERSION = "aet-derived-v0.1"
_CENTRALITY_RANK = {
    "core_contribution": 0,
    "supporting_method": 1,
    "background_only": 2,
    "incidental_mention": 3,
    "unrelated": 4,
}


class _ChunkRef(NamedTuple):
    id: str
    section_id: str | None
    section_type: str


def _display_name(value: str | None, fallback: str) -> str:
    return (value or fallback).replace("_", " ").strip().title()


def _section_title(section: PaperSection) -> str:
    if section.section_title and section.section_title.strip():
        return section.section_title.strip()
    return _display_name(None, section.section_type)


def _extractive_summary(text: str, limit: int = 240) -> str | None:
    normalized = " ".join(text.split())
    if not normalized:
        return None
    return normalized if len(normalized) <= limit else f"{normalized[: limit - 1]}…"


def _page_bounds(sections: list[PaperSection]) -> tuple[int | None, int | None]:
    starts = [
        section.page_start for section in sections if section.page_start is not None
    ]
    ends = [section.page_end for section in sections if section.page_end is not None]
    return (min(starts) if starts else None, max(ends) if ends else None)


def _tree_generation_id(
    paper: Paper,
    sections: list[PaperSection],
    chunks: list[_ChunkRef],
    evidence_rows: list[PaperEvidence],
) -> str:
    """Fingerprint the structural rows used for this ephemeral tree."""
    source_snapshot = {
        "paper": {"id": paper.id, "title": paper.title},
        "sections": [
            {
                "id": section.id,
                "type": section.section_type,
                "title": section.section_title,
                "content": section.content,
                "page_start": section.page_start,
                "page_end": section.page_end,
                "order_index": section.order_index,
            }
            for section in sections
        ],
        "chunks": [chunk._asdict() for chunk in chunks],
        "evidence": [
            {
                "chunk_id": evidence.chunk_id,
                "type": evidence.evidence_type,
                "source": evidence.evidence_source,
                "text": evidence.evidence_text,
                "score": evidence.score,
                "extra": evidence.extra,
            }
            for evidence in sorted(
                evidence_rows,
                key=lambda row: (
                    row.evidence_type,
                    row.chunk_id or "",
                    row.evidence_text,
                    row.id,
                ),
            )
        ],
    }
    encoded = json.dumps(
        source_snapshot, sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return hashlib.sha256(encoded).hexdigest()[:24]


def _classification_inputs(paper: Paper) -> dict:
    classification = paper.classification
    graph_signals = classification.graph_signals or {} if classification else {}
    matched_topics = classification.matched_topics or [] if classification else []
    return {
        "author_score": classification.author_score if classification else 0.0,
        "institution_score": (
            classification.institution_score if classification else 0.0
        ),
        "topic_score": classification.topic_score if classification else 0.0,
        "network_score": classification.network_score if classification else 0.0,
        "citation_score": classification.citation_score if classification else 0.0,
        "has_second_degree": bool(graph_signals.get("second_degree_paths")),
        "cites_ac_core": bool(graph_signals.get("citation_signals")),
        "has_core_topic_match": any(
            isinstance(topic, dict)
            and topic.get("is_core")
            and float(topic.get("score") or 0) > 0
            for topic in matched_topics
        ),
    }


def build_attribution_evidence_tree(
    session: Session, paper_id: str
) -> AttributionEvidenceTreeOut:
    """Build a deterministic, read-only AET without changing classifier state."""
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise ValueError(f"Paper {paper_id} not found")

    sections = list(
        session.execute(
            select(PaperSection)
            .where(PaperSection.paper_id == paper_id)
            .order_by(PaperSection.order_index, PaperSection.id)
        ).scalars()
    )
    chunks = [
        _ChunkRef(*row)
        for row in session.execute(
            select(PaperChunk.id, PaperChunk.section_id, PaperChunk.section_type)
            .where(PaperChunk.paper_id == paper_id)
            .order_by(PaperChunk.char_start, PaperChunk.id)
        )
    ]
    evidence_rows = list(
        session.execute(
            select(PaperEvidence)
            .where(PaperEvidence.paper_id == paper_id)
            .order_by(PaperEvidence.id)
        ).scalars()
    )

    structural_generation_id = _tree_generation_id(
        paper, sections, chunks, evidence_rows
    )
    scoring = score_attribution_evidence(
        evidence_rows=evidence_rows,
        has_funding_evidence=any(
            row.evidence_type == "funding_acknowledgement" and row.score > 0
            for row in evidence_rows
        )
        or bool(paper.ac_acknowledged)
        or has_ac_funding_in_text(paper.funding_text, paper.ac_programs),
        **_classification_inputs(paper),
    )
    tree_generation_id = hashlib.sha256(
        f"{structural_generation_id}:{scoring.generation_id}".encode()
    ).hexdigest()[:24]
    root_id = f"aet:{tree_generation_id}:root"
    page_start, page_end = _page_bounds(sections)
    nodes = [
        AttributionTreeNodeOut(
            node_id=root_id,
            node_type="root",
            path=["Paper"],
            title=paper.title,
            summary=paper.title,
            page_start=page_start,
            page_end=page_end,
        )
    ]
    chunks_by_id = {chunk.id: chunk for chunk in chunks}
    chunks_by_section: dict[str, list[_ChunkRef]] = {}
    for chunk in chunks:
        if chunk.section_id:
            chunks_by_section.setdefault(chunk.section_id, []).append(chunk)

    node_by_section: dict[str, AttributionTreeNodeOut] = {}
    for section in sections:
        title = _section_title(section)
        node = AttributionTreeNodeOut(
            node_id=f"aet:{tree_generation_id}:section:{section.id}",
            parent_node_id=root_id,
            node_type="section",
            path=["Paper", title],
            section_type=section.section_type,
            title=title,
            summary=_extractive_summary(section.content),
            page_start=section.page_start,
            page_end=section.page_end,
            source_section_id=section.id,
            source_chunk_ids=[
                chunk.id for chunk in chunks_by_section.get(section.id, [])
            ],
        )
        nodes.append(node)
        node_by_section[section.id] = node

    virtual_nodes: dict[str, AttributionTreeNodeOut] = {}

    def source_node(source: str, chunk_id: str | None) -> AttributionTreeNodeOut:
        chunk = chunks_by_id.get(chunk_id or "")
        if chunk and chunk.section_id in node_by_section:
            return node_by_section[chunk.section_id]

        section_type = chunk.section_type if chunk else source
        node = virtual_nodes.get(section_type)
        if node is None:
            title = _display_name(section_type, "Unlocated Evidence")
            node = AttributionTreeNodeOut(
                node_id=f"aet:{tree_generation_id}:source:{section_type}",
                parent_node_id=root_id,
                node_type="source",
                path=["Paper", title],
                section_type=section_type,
                title=title,
            )
            virtual_nodes[section_type] = node
            nodes.append(node)
        if chunk_id and chunk_id not in node.source_chunk_ids:
            node.source_chunk_ids.append(chunk_id)
        return node

    evidence_by_id = {row.id: row for row in evidence_rows}
    paths: list[AttributionEvidencePathOut] = []
    for normalized in scoring.paths:
        evidence = evidence_by_id.get(normalized.source_evidence_id or "")
        source = evidence.evidence_source if evidence else "classifier_signals"
        chunk_id = evidence.chunk_id if evidence else None
        node = source_node(source, chunk_id)
        paths.append(
            AttributionEvidencePathOut(
                generation_id=normalized.generation_id,
                path_id=normalized.path_id,
                rank=1,
                node_id=node.node_id,
                path=list(normalized.path),
                evidence_type=normalized.evidence_type,
                polarity=normalized.polarity,
                centrality=normalized.centrality,
                quote=normalized.quote or normalized.evidence_type,
                page_start=node.page_start,
                page_end=node.page_end,
                source_chunk_ids=list(normalized.source_chunk_ids),
                raw_score=normalized.raw_score,
                weight=normalized.weight,
                confidence=normalized.confidence,
                detector_type=normalized.detector_type,
                metadata_status=normalized.metadata_status,
            )
        )

    paths.sort(
        key=lambda path: (
            -abs(path.weight),
            _CENTRALITY_RANK[path.centrality],
            path.evidence_type,
            path.path_id,
        )
    )
    for rank, path in enumerate(paths, start=1):
        path.rank = rank

    evidence_review_reasons: list[str] = []
    if not paths:
        evidence_review_reasons.append("AET_NO_EVIDENCE")
    elif scoring.conflicting:
        evidence_review_reasons.append("AET_CONFLICTING_EVIDENCE")

    return AttributionEvidenceTreeOut(
        paper_id=paper_id,
        tree_version=TREE_VERSION,
        generation_mode="derived_ephemeral",
        generation_id=tree_generation_id,
        metadata_contract_version=ATTRIBUTION_EVIDENCE_METADATA_VERSION,
        nodes=nodes,
        evidence_paths=paths,
        evidence_review_recommended=bool(evidence_review_reasons),
        evidence_review_reasons=evidence_review_reasons,
    )
