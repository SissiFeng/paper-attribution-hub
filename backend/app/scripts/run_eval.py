"""Compare classifier output against the gold-standard eval set.

Usage:
    python -m app.scripts.run_eval [--labels data/eval_labels.csv] [--include-silver]

--include-silver additionally loads data/eval_labels_silver.csv (built by
app.scripts.build_silver_eval_labels); hand labels win on conflicts.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from app.config import settings
from app.db import SessionLocal, init_database
from app.services.eval_service import print_report, run_evaluation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path, default=settings.eval_labels_csv)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument(
        "--include-silver",
        action="store_true",
        help="Also load the silver eval labels (hand labels win on conflicts).",
    )
    parser.add_argument(
        "--silver-labels", type=Path, default=settings.eval_labels_silver_csv
    )
    args = parser.parse_args()

    init_database()
    with SessionLocal() as session:
        report = run_evaluation(
            session,
            args.labels,
            k=args.k,
            silver_labels_path=args.silver_labels if args.include_silver else None,
        )
    print_report(report)


if __name__ == "__main__":
    main()
