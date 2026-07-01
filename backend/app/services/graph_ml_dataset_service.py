"""Export a GNN-ready heterogeneous graph dataset from the paper KB.

This is deliberately a data-contract layer, not a model-training layer. It
preserves the existing rule classifier and writes graph artifacts that can feed
GraphSAGE/GAT/hetero-GNN experiments later.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AcCorePaper,
    Author,
    Institution,
    Paper,
    PaperAuthor,
    PaperClassification,
    PaperEntity,
    PaperLabLink,
    PaperReference,
    SdlLab,
)


def _safe_key(value: str) -> str:
    key = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return re.sub(r"-{2,}", "-", key)[:120] or "unknown"


def _node_id(kind: str, key: str) -> str:
    return f"{kind}:{_safe_key(key)}"


def _entity_node_id(entity_type: str, name: str) -> str:
    return _node_id("entity", f"{entity_type}:{name}")


def _topic_from_match(match: dict[str, Any]) -> tuple[str, str]:
    topic_id = str(match.get("topic_id") or match.get("id") or match.get("name") or "")
    name = str(match.get("name") or topic_id)
    return topic_id or name, name


def collect_graph_ml_dataset(session: Session) -> dict[str, list[dict] | dict]:
    """Return deterministic nodes, edges, labels, and manifest for graph ML."""
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    labels: list[dict] = []

    def add_node(node_id: str, node_type: str, **attrs: Any) -> None:
        if node_id in nodes:
            nodes[node_id]["attrs"].update({k: v for k, v in attrs.items() if v is not None})
            return
        nodes[node_id] = {
            "id": node_id,
            "type": node_type,
            "attrs": {k: v for k, v in attrs.items() if v is not None},
        }

    def add_edge(src: str, dst: str, edge_type: str, **attrs: Any) -> None:
        edges.append(
            {
                "src": src,
                "dst": dst,
                "type": edge_type,
                "attrs": {k: v for k, v in attrs.items() if v is not None},
            }
        )

    for paper in session.execute(select(Paper).order_by(Paper.id)).scalars():
        add_node(
            _node_id("paper", paper.id),
            "paper",
            paper_id=paper.id,
            title=paper.title,
            year=paper.year,
            venue=paper.venue,
            provenance=paper.provenance,
            ac_known_publication=bool(paper.ac_known_publication),
            full_text_available=bool(paper.full_text_available),
        )

    for author in session.execute(select(Author).order_by(Author.id)).scalars():
        add_node(
            _node_id("author", author.id),
            "author",
            author_id=author.id,
            name=author.canonical_name,
            normalized_name=author.normalized_name,
            institution_id=author.institution_id,
            is_ac_member=bool(author.is_ac_member),
        )

    for institution in session.execute(select(Institution).order_by(Institution.id)).scalars():
        add_node(
            _node_id("institution", institution.id),
            "institution",
            institution_id=institution.id,
            name=institution.canonical_name,
            country=institution.country,
            city=institution.city,
            is_partner=bool(institution.is_partner),
        )

    for lab in session.execute(select(SdlLab).order_by(SdlLab.id)).scalars():
        add_node(
            _node_id("lab", lab.id),
            "lab",
            lab_id=lab.id,
            name=lab.name,
            institution=lab.institution,
            domain_focus=lab.domain_focus,
            automation_level=lab.automation_level,
        )

    for core in session.execute(select(AcCorePaper).order_by(AcCorePaper.id)).scalars():
        add_node(
            _node_id("ac_core", core.id),
            "ac_core_paper",
            ac_core_id=core.id,
            title=core.title,
            doi=core.doi,
            year=core.year,
            venue=core.venue,
        )

    for link in session.execute(select(PaperAuthor).order_by(PaperAuthor.paper_id, PaperAuthor.author_order)).scalars():
        add_edge(
            _node_id("paper", link.paper_id),
            _node_id("author", link.author_id),
            "paper_authored_by",
            author_order=link.author_order,
            match_confidence=link.match_confidence,
        )

    for author_id, institution_id in session.execute(
        select(Author.id, Author.institution_id)
        .where(Author.institution_id.is_not(None))
        .order_by(Author.id)
    ):
        add_edge(
            _node_id("author", author_id),
            _node_id("institution", institution_id),
            "author_affiliated_with",
        )

    for link in session.execute(
        select(PaperLabLink).order_by(PaperLabLink.paper_id, PaperLabLink.lab_id)
    ).scalars():
        add_edge(
            _node_id("paper", link.paper_id),
            _node_id("lab", link.lab_id),
            "paper_linked_to_lab",
            source=link.source,
            confidence=link.confidence,
        )

    for entity in session.execute(
        select(PaperEntity).order_by(
            PaperEntity.paper_id, PaperEntity.entity_type, PaperEntity.normalized_name
        )
    ).scalars():
        entity_id = _entity_node_id(entity.entity_type, entity.normalized_name)
        add_node(
            entity_id,
            "entity",
            entity_type=entity.entity_type,
            name=entity.normalized_name,
        )
        add_edge(
            _node_id("paper", entity.paper_id),
            entity_id,
            "paper_mentions_entity",
            confidence=entity.confidence,
            stage=entity.stage,
            evidence_chunk_id=entity.evidence_chunk_id,
        )

    for ref in session.execute(
        select(PaperReference).order_by(PaperReference.citing_paper_id, PaperReference.id)
    ).scalars():
        if ref.cited_paper_id:
            add_edge(
                _node_id("paper", ref.citing_paper_id),
                _node_id("paper", ref.cited_paper_id),
                "paper_cites_paper",
                reference_id=ref.id,
                cited_doi=ref.cited_doi,
            )
        if ref.cited_ac_core_id:
            add_edge(
                _node_id("paper", ref.citing_paper_id),
                _node_id("ac_core", ref.cited_ac_core_id),
                "paper_cites_ac_core",
                reference_id=ref.id,
                cited_doi=ref.cited_doi,
            )

    for cls in session.execute(
        select(PaperClassification).order_by(PaperClassification.paper_id)
    ).scalars():
        paper_node = _node_id("paper", cls.paper_id)
        labels.append(
            {
                "node_id": paper_node,
                "paper_id": cls.paper_id,
                "label": cls.label,
                "confidence": cls.confidence,
                "source": "paper_classification",
                "human_confirmed": bool(cls.human_confirmed),
                "model_version": cls.model_version,
                "scores": {
                    "author_score": cls.author_score,
                    "institution_score": cls.institution_score,
                    "topic_score": cls.topic_score,
                    "network_score": cls.network_score,
                    "citation_score": cls.citation_score,
                    "fulltext_evidence_score": cls.fulltext_evidence_score,
                },
            }
        )
        for match in cls.matched_topics or []:
            topic_id, topic_name = _topic_from_match(match)
            if not topic_id:
                continue
            topic_node = _node_id("topic", topic_id)
            add_node(topic_node, "topic", topic_id=topic_id, name=topic_name)
            add_edge(
                paper_node,
                topic_node,
                "paper_has_topic",
                score=match.get("score"),
                is_core=match.get("is_core"),
            )

    sorted_nodes = sorted(nodes.values(), key=lambda row: row["id"])
    sorted_edges = sorted(
        edges, key=lambda row: (row["src"], row["type"], row["dst"], json.dumps(row["attrs"], sort_keys=True))
    )
    sorted_labels = sorted(labels, key=lambda row: row["node_id"])
    manifest = {
        "format": "paper-graph-ml-v0.1",
        "node_count": len(sorted_nodes),
        "edge_count": len(sorted_edges),
        "label_count": len(sorted_labels),
        "node_types": dict(sorted(Counter(row["type"] for row in sorted_nodes).items())),
        "edge_types": dict(sorted(Counter(row["type"] for row in sorted_edges).items())),
        "label_values": dict(sorted(Counter(row["label"] for row in sorted_labels).items())),
    }
    return {
        "nodes": sorted_nodes,
        "edges": sorted_edges,
        "labels": sorted_labels,
        "manifest": manifest,
    }


def write_graph_ml_dataset(session: Session, output_dir: Path) -> dict:
    """Write graph ML JSONL artifacts and return the manifest."""
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset = collect_graph_ml_dataset(session)
    for name in ("nodes", "edges", "labels"):
        rows = dataset[name]
        assert isinstance(rows, list)
        (output_dir / f"{name}.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
    manifest = dataset["manifest"]
    assert isinstance(manifest, dict)
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest
