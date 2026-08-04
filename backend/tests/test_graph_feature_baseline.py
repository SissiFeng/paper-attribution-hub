"""Leakage-safe graph-feature baseline for paper classification."""

from __future__ import annotations

from copy import deepcopy
import json
import sys

import pytest

from app.graph_ml_contract import GRAPH_ML_FORMAT
from app.services.graph_feature_baseline import (
    GRAPH_FEATURE_NAMES,
    build_graph_features,
    evaluate_graph_feature_baseline,
    load_graph_ml_dataset,
)
from app.scripts.run_graph_feature_baseline import main


def _structural_dataset() -> dict:
    return {
        "nodes": [
            {
                "id": "paper:p1",
                "type": "paper",
                "attrs": {
                    "paper_id": "P1",
                    "year": 2024,
                    "full_text_available": True,
                    "ac_known_publication": True,
                    "provenance": "ac_gold",
                },
            },
            {
                "id": "paper:p2",
                "type": "paper",
                "attrs": {"paper_id": "P2", "year": 2022},
            },
            {
                "id": "author:a1",
                "type": "author",
                "attrs": {"is_ac_member": True},
            },
            {
                "id": "author:a2",
                "type": "author",
                "attrs": {"is_ac_member": False},
            },
            {
                "id": "institution:i1",
                "type": "institution",
                "attrs": {"is_partner": True},
            },
            {"id": "lab:l1", "type": "lab", "attrs": {}},
            {"id": "entity:e1", "type": "entity", "attrs": {}},
            {"id": "topic:t1", "type": "topic", "attrs": {}},
            {"id": "ac_core:c1", "type": "ac_core_paper", "attrs": {}},
        ],
        "edges": [
            {
                "src": "paper:p1",
                "dst": "author:a1",
                "type": "paper_authored_by",
                "attrs": {},
            },
            {
                "src": "paper:p1",
                "dst": "author:a2",
                "type": "paper_authored_by",
                "attrs": {},
            },
            {
                "src": "author:a1",
                "dst": "institution:i1",
                "type": "author_affiliated_with",
                "attrs": {},
            },
            {
                "src": "paper:p1",
                "dst": "lab:l1",
                "type": "paper_linked_to_lab",
                "attrs": {},
            },
            {
                "src": "paper:p1",
                "dst": "entity:e1",
                "type": "paper_mentions_entity",
                "attrs": {"confidence": 0.99},
            },
            {
                "src": "paper:p1",
                "dst": "topic:t1",
                "type": "paper_has_topic",
                "attrs": {"score": 0.95},
            },
            {
                "src": "paper:p1",
                "dst": "paper:p2",
                "type": "paper_cites_paper",
                "attrs": {},
            },
            {
                "src": "paper:p1",
                "dst": "ac_core:c1",
                "type": "paper_cites_ac_core",
                "attrs": {},
            },
        ],
        "labels": [
            {
                "node_id": "paper:p1",
                "paper_id": "P1",
                "label": "CORE_RELEVANT",
                "confidence": 0.99,
                "scores": {"author_score": 1.0, "topic_score": 0.95},
            }
        ],
        "manifest": {},
    }


def _evaluation_dataset() -> tuple[dict, dict[str, str]]:
    nodes: list[dict] = []
    edges: list[dict] = []
    labels: list[dict] = []
    gold: dict[str, str] = {}
    label_order = [
        "CORE_RELEVANT",
        "RELATED_RELEVANT",
        "ADJACENT",
        "EXCLUDE",
    ]

    for index in range(8):
        paper_id = f"P{index + 1}"
        paper_node = f"paper:{paper_id.lower()}"
        label = label_order[index // 2]
        gold[paper_id] = label
        nodes.append(
            {
                "id": paper_node,
                "type": "paper",
                "attrs": {
                    "paper_id": paper_id,
                    "year": 2017 + index,
                    "full_text_available": index % 2 == 0,
                },
            }
        )
        labels.append({"node_id": paper_node, "paper_id": paper_id, "label": label})

        if label in {"CORE_RELEVANT", "RELATED_RELEVANT"}:
            author_node = f"author:a{index}"
            nodes.append(
                {
                    "id": author_node,
                    "type": "author",
                    "attrs": {"is_ac_member": label == "CORE_RELEVANT"},
                }
            )
            edges.append(
                {
                    "src": paper_node,
                    "dst": author_node,
                    "type": "paper_authored_by",
                    "attrs": {},
                }
            )
        if label != "EXCLUDE":
            topic_node = f"topic:t{index}"
            nodes.append({"id": topic_node, "type": "topic", "attrs": {}})
            edges.append(
                {
                    "src": paper_node,
                    "dst": topic_node,
                    "type": "paper_has_topic",
                    "attrs": {"score": 0.5 + index / 20},
                }
            )
        if label == "CORE_RELEVANT":
            core_node = f"ac_core:c{index}"
            nodes.append({"id": core_node, "type": "ac_core_paper", "attrs": {}})
            edges.append(
                {
                    "src": paper_node,
                    "dst": core_node,
                    "type": "paper_cites_ac_core",
                    "attrs": {},
                }
            )

    return {"nodes": nodes, "edges": edges, "labels": labels, "manifest": {}}, gold


def test_build_graph_features_uses_structure_without_classifier_leakage():
    dataset = _structural_dataset()

    features = build_graph_features(dataset)

    assert tuple(features["P1"]) == GRAPH_FEATURE_NAMES
    assert features["P1"] == {
        "year": 2024.0,
        "full_text_available": 1.0,
        "author_count": 2.0,
        "ac_author_count": 1.0,
        "partner_institution_count": 1.0,
        "lab_count": 1.0,
        "entity_count": 1.0,
        "paper_citation_count": 1.0,
        "ac_core_citation_count": 1.0,
        "cited_by_count": 0.0,
    }
    assert features["P2"]["cited_by_count"] == 1.0

    changed_scores = deepcopy(dataset)
    changed_scores["labels"][0]["label"] = "EXCLUDE"
    changed_scores["labels"][0]["confidence"] = 0.01
    changed_scores["labels"][0]["scores"] = {"author_score": 0.0, "topic_score": 0.0}
    changed_scores["edges"][4]["attrs"]["confidence"] = 0.01
    changed_scores["edges"] = [
        edge for edge in changed_scores["edges"] if edge["type"] != "paper_has_topic"
    ]

    assert build_graph_features(changed_scores) == features


def test_evaluate_graph_feature_baseline_is_deterministic_and_compares_current():
    dataset, gold = _evaluation_dataset()

    first = evaluate_graph_feature_baseline(dataset, gold)
    second = evaluate_graph_feature_baseline(dataset, gold)

    assert first == second
    assert first["validation"] == {
        "strategy": "leave_one_out",
        "model": "standard_scaler_logistic_regression",
    }
    assert first["feature_names"] == list(GRAPH_FEATURE_NAMES)
    assert first["n_graph_papers"] == 8
    assert first["n_gold_labels"] == 8
    assert first["n_evaluated"] == 8
    assert len(first["predictions"]) == 8
    assert 0.0 <= first["baseline"]["macro_f1"] <= 1.0
    assert first["current_classifier"]["accuracy"] == 1.0
    assert first["current_classifier"]["macro_f1"] == 1.0
    assert first["macro_f1_delta_vs_current"] <= 0.0


def test_graph_baseline_normalizes_review_alias_and_accepts_sdl_field_label():
    dataset, gold = _evaluation_dataset()
    gold["P3"] = gold["P4"] = "INCLUDE"
    gold["P5"] = gold["P6"] = "SDL_FIELD_RELEVANT"

    report = evaluate_graph_feature_baseline(dataset, gold)

    assert report["label_counts"]["RELATED_RELEVANT"] == 2
    assert report["label_counts"]["SDL_FIELD_RELEVANT"] == 2


def test_evaluate_graph_feature_baseline_rejects_empty_graph():
    with pytest.raises(ValueError, match="no paper nodes"):
        evaluate_graph_feature_baseline(
            {"nodes": [], "edges": [], "labels": [], "manifest": {}},
            {"P1": "CORE_RELEVANT"},
        )


def test_evaluate_graph_feature_baseline_rejects_no_gold_overlap():
    with pytest.raises(ValueError, match="No gold labels overlap"):
        evaluate_graph_feature_baseline(_structural_dataset(), {"OTHER": "EXCLUDE"})


def test_evaluate_graph_feature_baseline_rejects_single_class():
    with pytest.raises(ValueError, match="at least two label classes"):
        evaluate_graph_feature_baseline(
            _structural_dataset(),
            {"P1": "CORE_RELEVANT", "P2": "CORE_RELEVANT"},
        )


def test_evaluate_graph_feature_baseline_rejects_untrainable_loo_fold():
    with pytest.raises(ValueError, match="leave-one-out training fold"):
        evaluate_graph_feature_baseline(
            _structural_dataset(),
            {"P1": "CORE_RELEVANT", "P2": "EXCLUDE"},
        )


def test_current_comparison_uses_same_graph_gold_overlap():
    dataset, gold = _evaluation_dataset()
    gold["OUTSIDE"] = "EXCLUDE"
    dataset["labels"][0]["human_confirmed"] = True
    dataset["labels"].append(
        {"node_id": "paper:outside", "paper_id": "OUTSIDE", "label": "EXCLUDE"}
    )

    report = evaluate_graph_feature_baseline(dataset, gold)

    assert report["n_evaluated"] == 8
    assert report["current_classifier"]["n_evaluated"] == 7
    assert report["predictions"][0]["current_label"] is None


def test_load_graph_ml_dataset_rejects_unknown_manifest_version(tmp_path):
    for name in ("nodes", "edges", "labels"):
        (tmp_path / f"{name}.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"format": "paper-graph-ml-v999"}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unsupported graph dataset format"):
        load_graph_ml_dataset(tmp_path)


def test_graph_feature_baseline_cli_writes_json_report(tmp_path, monkeypatch, capsys):
    dataset, gold = _evaluation_dataset()
    for name in ("nodes", "edges", "labels"):
        (tmp_path / f"{name}.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in dataset[name]),
            encoding="utf-8",
        )
    (tmp_path / "manifest.json").write_text(
        json.dumps({"format": GRAPH_ML_FORMAT}) + "\n",
        encoding="utf-8",
    )
    labels_path = tmp_path / "gold.csv"
    labels_path.write_text(
        "paper_id,gold_label,gold_topics,notes\n"
        + "".join(f"{paper_id},{label},,test\n" for paper_id, label in gold.items()),
        encoding="utf-8",
    )
    report_path = tmp_path / "reports" / "baseline.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_graph_feature_baseline",
            "--graph-dir",
            str(tmp_path),
            "--labels",
            str(labels_path),
            "--out",
            str(report_path),
            "--json",
        ],
    )

    main()

    stdout_report = json.loads(capsys.readouterr().out)
    written_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert stdout_report == written_report
    assert written_report["n_evaluated"] == 8
