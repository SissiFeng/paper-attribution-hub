"""Compare classifier output against the gold-standard eval set.

Usage:
    python -m app.scripts.run_eval [--labels data/eval_labels.csv]
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
    args = parser.parse_args()

    init_database()
    with SessionLocal() as session:
        report = run_evaluation(session, args.labels, k=args.k)
    print_report(report)


if __name__ == "__main__":
    main()
