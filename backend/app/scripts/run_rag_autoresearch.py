"""Run attribution RAG autoresearch gates.

Usage:
    python -m app.scripts.run_rag_autoresearch --json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.db import SessionLocal, init_database
from app.services.autoresearch_service import (
    run_rag_autoresearch,
    write_autoresearch_report,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--alpha", type=float, default=0.5)
    parser.add_argument(
        "--section-type",
        action="append",
        dest="section_types",
        help="Restrict retrieval to a section type. Repeat for multiple values.",
    )
    parser.add_argument("--min-recall", type=float, default=1.0)
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
        report = run_rag_autoresearch(
            session,
            top_k=args.k,
            alpha=args.alpha,
            section_types=args.section_types,
            min_recall_at_k=args.min_recall,
        )

    if args.out:
        write_autoresearch_report(report, args.out)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        status = "ACCEPTED" if report["accepted"] else "REJECTED"
        metrics = report["metrics"]
        coverage = report["coverage"]
        print(f"RAG autoresearch: {status}")
        print(
            f"Tasks={metrics['tasks']} hits={metrics['hits']} "
            f"recall@{args.k}={metrics['recall_at_k']} mrr={metrics['mrr']}"
        )
        print(
            f"Fulltext papers={coverage['fulltext_papers']}/{coverage['papers']} "
            f"chunks={coverage['chunks']} non_abstract={coverage['non_abstract_chunks']}"
        )
        for gate in report["gates"]:
            print(
                f"- {gate['status'].upper()} {gate['name']}: "
                f"{gate['observed']} / {gate['threshold']}"
            )


if __name__ == "__main__":
    main()
