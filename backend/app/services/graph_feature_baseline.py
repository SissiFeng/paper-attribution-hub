"""Leakage-safe structural baseline for the graph ML paper dataset.

The baseline deliberately ignores classifier labels, confidences, score fields,
and edge weights. It measures whether graph structure alone adds useful signal
before the project takes on a GNN runtime dependency.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np

from app.classification_labels import normalize_classification_label
from app.graph_ml_contract import GRAPH_ML_FORMAT
from app.services.eval_service import EvalReport, compute_metrics

GRAPH_FEATURE_NAMES = (
    "year",
    "full_text_available",
    "author_count",
    "ac_author_count",
    "partner_institution_count",
    "lab_count",
    "entity_count",
    "paper_citation_count",
    "ac_core_citation_count",
    "cited_by_count",
)


def _number(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def build_graph_features(dataset: dict) -> dict[str, dict[str, float]]:
    """Return one fixed-order structural feature row per paper.

    Only node identity, safe paper metadata, neighbor attributes, and edge
    presence are used. ``dataset["labels"]`` and every edge ``attrs`` mapping
    are intentionally ignored.
    """
    nodes = dataset.get("nodes") or []
    edges = dataset.get("edges") or []
    node_by_id = {row["id"]: row for row in nodes}
    paper_id_by_node = {
        row["id"]: str(row.get("attrs", {}).get("paper_id") or "").strip()
        for row in nodes
        if row.get("type") == "paper"
    }
    paper_id_by_node = {
        node_id: paper_id for node_id, paper_id in paper_id_by_node.items() if paper_id
    }

    neighbors = {
        paper_id: {
            "authors": set(),
            "labs": set(),
            "entities": set(),
            "paper_citations": set(),
            "ac_core_citations": set(),
            "cited_by": set(),
        }
        for paper_id in paper_id_by_node.values()
    }
    author_institutions: dict[str, set[str]] = {}

    for edge in edges:
        src = edge.get("src")
        dst = edge.get("dst")
        edge_type = edge.get("type")
        if edge_type == "author_affiliated_with" and src and dst:
            author_institutions.setdefault(src, set()).add(dst)
            continue

        paper_id = paper_id_by_node.get(src)
        if paper_id:
            key_by_edge = {
                "paper_authored_by": "authors",
                "paper_linked_to_lab": "labs",
                "paper_mentions_entity": "entities",
                "paper_cites_paper": "paper_citations",
                "paper_cites_ac_core": "ac_core_citations",
            }
            key = key_by_edge.get(edge_type)
            if key and dst:
                neighbors[paper_id][key].add(dst)

        cited_paper_id = paper_id_by_node.get(dst)
        if cited_paper_id and edge_type == "paper_cites_paper" and src:
            neighbors[cited_paper_id]["cited_by"].add(src)

    features: dict[str, dict[str, float]] = {}
    for paper_node, paper_id in paper_id_by_node.items():
        paper_attrs = node_by_id[paper_node].get("attrs", {})
        paper_neighbors = neighbors[paper_id]
        authors = paper_neighbors["authors"]
        ac_authors = {
            author_id
            for author_id in authors
            if bool(node_by_id.get(author_id, {}).get("attrs", {}).get("is_ac_member"))
        }
        partner_institutions = {
            institution_id
            for author_id in authors
            for institution_id in author_institutions.get(author_id, set())
            if bool(
                node_by_id.get(institution_id, {}).get("attrs", {}).get("is_partner")
            )
        }
        values = {
            "year": _number(paper_attrs.get("year")),
            "full_text_available": float(bool(paper_attrs.get("full_text_available"))),
            "author_count": float(len(authors)),
            "ac_author_count": float(len(ac_authors)),
            "partner_institution_count": float(len(partner_institutions)),
            "lab_count": float(len(paper_neighbors["labs"])),
            "entity_count": float(len(paper_neighbors["entities"])),
            "paper_citation_count": float(len(paper_neighbors["paper_citations"])),
            "ac_core_citation_count": float(len(paper_neighbors["ac_core_citations"])),
            "cited_by_count": float(len(paper_neighbors["cited_by"])),
        }
        features[paper_id] = {name: values[name] for name in GRAPH_FEATURE_NAMES}
    return features


def _metrics_dict(report: EvalReport) -> dict:
    return {
        "n_evaluated": report.n_evaluated,
        "accuracy": report.accuracy,
        "macro_precision": report.macro_precision,
        "macro_recall": report.macro_recall,
        "macro_f1": report.macro_f1,
        "per_label": [
            {
                "label": metric.label,
                "precision": metric.precision,
                "recall": metric.recall,
                "f1": metric.f1,
                "support": metric.support,
            }
            for metric in report.per_label
        ],
        "confusion": report.confusion,
    }


def evaluate_graph_feature_baseline(
    dataset: dict,
    gold_by_paper: dict[str, str],
) -> dict:
    """Evaluate structural features with deterministic leave-one-out CV."""
    features_by_paper = build_graph_features(dataset)
    if not features_by_paper:
        raise ValueError("Graph dataset contains no paper nodes.")

    normalized_gold: dict[str, str] = {}
    unsupported: set[str] = set()
    for paper_id, label in gold_by_paper.items():
        normalized = normalize_classification_label(label)
        if normalized is None:
            unsupported.add(str(label))
        else:
            normalized_gold[paper_id] = normalized
    if unsupported:
        raise ValueError(f"Unsupported gold labels: {', '.join(sorted(unsupported))}")

    paper_ids = sorted(set(features_by_paper) & set(normalized_gold))
    if not paper_ids:
        raise ValueError("No gold labels overlap graph paper nodes.")
    gold_labels = [normalized_gold[paper_id] for paper_id in paper_ids]
    if len(set(gold_labels)) < 2:
        raise ValueError("Graph baseline needs at least two label classes.")
    if any(
        len(set(gold_labels[:index] + gold_labels[index + 1 :])) < 2
        for index in range(len(gold_labels))
    ):
        raise ValueError(
            "Every leave-one-out training fold needs at least two label classes."
        )

    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import LeaveOneOut
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    x = np.asarray(
        [
            [features_by_paper[paper_id][name] for name in GRAPH_FEATURE_NAMES]
            for paper_id in paper_ids
        ],
        dtype=np.float32,
    )
    y = np.asarray(gold_labels)
    predicted: dict[str, str] = {}
    for train_index, test_index in LeaveOneOut().split(x):
        train_labels = y[train_index]
        model = Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                (
                    "classifier",
                    LogisticRegression(
                        class_weight="balanced",
                        max_iter=500,
                        random_state=0,
                    ),
                ),
            ]
        )
        model.fit(x[train_index], train_labels)
        prediction = str(model.predict(x[test_index])[0])
        predicted[paper_ids[int(test_index[0])]] = prediction

    baseline_metrics = compute_metrics(predicted, normalized_gold)
    current_by_paper: dict[str, str] = {}
    for row in dataset.get("labels") or []:
        if bool(row.get("human_confirmed")):
            continue
        paper_id = str(row.get("paper_id") or "").strip()
        label = normalize_classification_label(row.get("label"))
        if paper_id and label:
            current_by_paper[paper_id] = label
    current_for_eval = {
        paper_id: current_by_paper[paper_id]
        for paper_id in paper_ids
        if paper_id in current_by_paper
    }
    current_metrics = (
        compute_metrics(current_for_eval, normalized_gold) if current_for_eval else None
    )
    current_dict = _metrics_dict(current_metrics) if current_metrics else None
    baseline_comparison_metrics = (
        compute_metrics(
            {paper_id: predicted[paper_id] for paper_id in current_for_eval},
            normalized_gold,
        )
        if current_for_eval
        else None
    )
    macro_f1_delta = (
        round(baseline_comparison_metrics.macro_f1 - current_metrics.macro_f1, 3)
        if baseline_comparison_metrics and current_metrics
        else None
    )

    return {
        "target": "graph_feature_baseline",
        "validation": {
            "strategy": "leave_one_out",
            "model": "standard_scaler_logistic_regression",
        },
        "feature_names": list(GRAPH_FEATURE_NAMES),
        "n_graph_papers": len(features_by_paper),
        "n_gold_labels": len(normalized_gold),
        "n_evaluated": len(paper_ids),
        "label_counts": dict(sorted(Counter(gold_labels).items())),
        "baseline": _metrics_dict(baseline_metrics),
        "current_classifier": current_dict,
        "macro_f1_delta_vs_current": macro_f1_delta,
        "predictions": [
            {
                "paper_id": paper_id,
                "gold_label": normalized_gold[paper_id],
                "baseline_label": predicted[paper_id],
                "current_label": current_by_paper.get(paper_id),
            }
            for paper_id in paper_ids
        ],
    }


def load_graph_ml_dataset(graph_dir: Path) -> dict:
    """Load the four files written by ``export_graph_ml_dataset``."""
    graph_dir = Path(graph_dir)

    def read_jsonl(name: str) -> list[dict]:
        path = graph_dir / f"{name}.jsonl"
        if not path.is_file():
            raise ValueError(f"Missing graph dataset file: {path}")
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    manifest_path = graph_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"Missing graph dataset file: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format") != GRAPH_ML_FORMAT:
        raise ValueError(
            "Unsupported graph dataset format: "
            f"{manifest.get('format')!r}; expected {GRAPH_ML_FORMAT!r}."
        )
    return {
        "nodes": read_jsonl("nodes"),
        "edges": read_jsonl("edges"),
        "labels": read_jsonl("labels"),
        "manifest": manifest,
    }
