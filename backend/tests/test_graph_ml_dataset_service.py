"""GNN-ready graph ML dataset export."""
from __future__ import annotations

import json
from pathlib import Path

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
from app.services.graph_ml_dataset_service import (
    collect_graph_ml_dataset,
    write_graph_ml_dataset,
)


def _seed(session) -> None:
    session.add(
        Institution(
            id="inst-uot",
            canonical_name="University of Toronto",
            is_partner=True,
        )
    )
    session.add(
        Author(
            id="auth-ac",
            canonical_name="Ada Chemist",
            normalized_name="ada chemist",
            institution_id="inst-uot",
            is_ac_member=True,
        )
    )
    session.add(
        SdlLab(
            id="lab-a",
            name="Lab A",
            institution="University of Toronto",
            domain_focus="materials",
        )
    )
    session.add_all(
        [
            Paper(
                id="P1",
                title="Closed-loop materials optimization",
                year=2024,
                venue="Test Journal",
                provenance="csv",
                ac_known_publication=True,
            ),
            Paper(id="P2", title="Cited paper", year=2023, provenance="csv"),
        ]
    )
    session.add(PaperAuthor(paper_id="P1", author_id="auth-ac", author_order=0))
    session.add(PaperLabLink(paper_id="P1", lab_id="lab-a", source="manual"))
    session.add(
        PaperEntity(
            id="ent-1",
            paper_id="P1",
            entity_type="method",
            name="bayesian optimization",
            normalized_name="bayesian optimization",
            confidence=0.9,
            stage="optimization",
            evidence_chunk_id="CH1",
        )
    )
    session.add(
        AcCorePaper(
            id="core-1",
            title="Self-driving lab landmark",
            doi="10.test/core",
            year=2020,
        )
    )
    session.add_all(
        [
            PaperReference(
                id="R1",
                citing_paper_id="P1",
                cited_paper_id="P2",
                cited_doi="10.test/p2",
                raw_text="P2 reference",
            ),
            PaperReference(
                id="R2",
                citing_paper_id="P1",
                cited_ac_core_id="core-1",
                cited_doi="10.test/core",
                raw_text="core reference",
            ),
        ]
    )
    session.add(
        PaperClassification(
            id="C1",
            paper_id="P1",
            label="CORE_RELEVANT",
            confidence=0.91,
            author_score=1.0,
            institution_score=1.0,
            topic_score=0.8,
            network_score=1.0,
            citation_score=0.5,
            fulltext_evidence_score=0.4,
            matched_topics=[
                {
                    "topic_id": "self-driving-lab",
                    "name": "Self-driving lab",
                    "score": 0.8,
                    "is_core": True,
                }
            ],
            model_version="rules-test",
        )
    )
    session.flush()


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_collect_graph_ml_dataset(session):
    _seed(session)

    dataset = collect_graph_ml_dataset(session)

    node_ids = {row["id"] for row in dataset["nodes"]}
    assert {
        "paper:p1",
        "paper:p2",
        "author:auth-ac",
        "institution:inst-uot",
        "lab:lab-a",
        "entity:method-bayesian-optimization",
        "ac_core:core-1",
        "topic:self-driving-lab",
    }.issubset(node_ids)

    edge_keys = {(row["src"], row["type"], row["dst"]) for row in dataset["edges"]}
    assert ("paper:p1", "paper_authored_by", "author:auth-ac") in edge_keys
    assert ("author:auth-ac", "author_affiliated_with", "institution:inst-uot") in edge_keys
    assert ("paper:p1", "paper_linked_to_lab", "lab:lab-a") in edge_keys
    assert (
        "paper:p1",
        "paper_mentions_entity",
        "entity:method-bayesian-optimization",
    ) in edge_keys
    assert ("paper:p1", "paper_cites_paper", "paper:p2") in edge_keys
    assert ("paper:p1", "paper_cites_ac_core", "ac_core:core-1") in edge_keys
    assert ("paper:p1", "paper_has_topic", "topic:self-driving-lab") in edge_keys

    assert dataset["labels"] == [
        {
            "node_id": "paper:p1",
            "paper_id": "P1",
            "label": "CORE_RELEVANT",
            "confidence": 0.91,
            "source": "paper_classification",
            "human_confirmed": False,
            "model_version": "rules-test",
            "scores": {
                "author_score": 1.0,
                "institution_score": 1.0,
                "topic_score": 0.8,
                "network_score": 1.0,
                "citation_score": 0.5,
                "fulltext_evidence_score": 0.4,
            },
        }
    ]
    manifest = dataset["manifest"]
    assert manifest["node_types"]["paper"] == 2
    assert manifest["edge_types"]["paper_has_topic"] == 1
    assert manifest["label_values"] == {"CORE_RELEVANT": 1}


def test_write_graph_ml_dataset(session, tmp_path):
    _seed(session)

    manifest = write_graph_ml_dataset(session, tmp_path)

    assert manifest["format"] == "paper-graph-ml-v0.1"
    assert (tmp_path / "nodes.jsonl").is_file()
    assert (tmp_path / "edges.jsonl").is_file()
    assert (tmp_path / "labels.jsonl").is_file()
    assert (tmp_path / "manifest.json").is_file()
    assert json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8")) == manifest
    assert any(row["id"] == "paper:p1" for row in _read_jsonl(tmp_path / "nodes.jsonl"))
    assert any(
        row["type"] == "paper_mentions_entity"
        for row in _read_jsonl(tmp_path / "edges.jsonl")
    )
    assert _read_jsonl(tmp_path / "labels.jsonl")[0]["label"] == "CORE_RELEVANT"
