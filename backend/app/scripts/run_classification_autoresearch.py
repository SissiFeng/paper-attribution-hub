"""Run classification autoresearch gates.

Usage:
    python -m app.scripts.run_classification_autoresearch --json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import settings
from app.db import SessionLocal, init_database
from app.services.autoresearch_service import (
    run_classification_autoresearch,
    write_autoresearch_report,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path, default=settings.eval_labels_csv)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--reclassify", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional path to write the JSON report.",
    )
    args = parser.parse_args()

    init_database()
    with SessionLocal() as session:
        report = run_classification_autoresearch(
            session,
            eval_labels_path=args.labels,
            k=args.k,
            reclassify=args.reclassify,
        )

    if args.out:
        write_autoresearch_report(report, args.out)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        status = "ACCEPTED" if report["accepted"] else "REJECTED"
        human = report["human_eval"]
        ac = report["ac_publications_eval"]
        print(f"Classification autoresearch: {status}")
        print(
            f"Human gold: n={human['n_evaluated']} "
            f"accuracy={human['accuracy']:.3f} macro_f1={human['macro_f1']:.3f}"
        )
        print(
            f"AC Publications: n={ac['gold_set_size']} "
            f"precision={ac['precision']} recall={ac['recall']} "
            f"false_positives={ac['false_positives']}"
        )
        for gate in report["gates"]:
            print(
                f"- {gate['status'].upper()} {gate['name']}: "
                f"{gate['observed']} / {gate['threshold']}"
            )


if __name__ == "__main__":
    main()
