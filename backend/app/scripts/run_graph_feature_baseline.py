"""Evaluate leakage-safe structural graph features against human gold labels.

Usage:
    python -m app.scripts.run_graph_feature_baseline --json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import REPO_ROOT, settings
from app.services.eval_service import load_gold_labels
from app.services.graph_feature_baseline import (
    evaluate_graph_feature_baseline,
    load_graph_ml_dataset,
)

DEFAULT_GRAPH_DIR = REPO_ROOT / "outputs" / "graph_ml"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph-dir", type=Path, default=DEFAULT_GRAPH_DIR)
    parser.add_argument("--labels", type=Path, default=settings.eval_labels_csv)
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    parser.add_argument("--out", type=Path, default=None, help="Write JSON report")
    args = parser.parse_args()

    try:
        dataset = load_graph_ml_dataset(args.graph_dir)
        gold = load_gold_labels(args.labels)
        report = evaluate_graph_feature_baseline(dataset, gold)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Graph feature baseline cannot run: {exc}") from exc

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    baseline = report["baseline"]
    print(
        "Graph feature baseline: "
        f"n={report['n_evaluated']} "
        f"accuracy={baseline['accuracy']:.3f} "
        f"macro_f1={baseline['macro_f1']:.3f}"
    )
    current = report["current_classifier"]
    if current is None:
        print("Current classifier comparison: unavailable (no overlapping labels)")
    else:
        print(
            "Current classifier: "
            f"n={current['n_evaluated']} "
            f"accuracy={current['accuracy']:.3f} "
            f"macro_f1={current['macro_f1']:.3f}"
        )
        print(f"Macro-F1 delta vs current: {report['macro_f1_delta_vs_current']:+.3f}")


if __name__ == "__main__":
    main()
