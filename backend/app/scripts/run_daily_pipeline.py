"""CLI: run the daily scheduled pipeline once.

Usage:

    # Plain pass over already-ingested papers — safe for offline cron.
    python -m app.scripts.run_daily_pipeline

    # Also fetch new papers from external sources (OpenAlex / S2 / Crossref).
    PAS_PIPELINE_DISCOVERY=1 python -m app.scripts.run_daily_pipeline

    # Full upgrade — discovery + full-text + learned classifier + LLM judge.
    PAS_PIPELINE_DISCOVERY=1 PAS_PIPELINE_FULLTEXT=1 \
        PAS_LEARNED_CLASSIFIER=1 PAS_LLM_JUDGE=1 \
        python -m app.scripts.run_daily_pipeline

Exit code:
    0 on success
    1 on failure (so cron will email you)
"""
from __future__ import annotations

import argparse
import json
import sys

from app.db import SessionLocal, init_database
from app.logging_utils import configure_logging
from app.services.scheduled_pipeline import run_daily_pipeline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-zotero-sync",
        action="store_true",
        help=(
            "Keep the persisted corpus locked and skip the configured Zotero "
            "sync for this run."
        ),
    )
    parser.add_argument(
        "--discovery",
        action="store_true",
        help="Also run the discovery step. Defaults to PAS_PIPELINE_DISCOVERY.",
    )
    parser.add_argument(
        "--fulltext",
        action="store_true",
        help="Refresh full-text evidence. Defaults to PAS_PIPELINE_FULLTEXT.",
    )
    parser.add_argument(
        "--force-reclassify",
        action="store_true",
        help="Re-run classification for every non-human-confirmed paper.",
    )
    parser.add_argument(
        "--learned",
        action="store_true",
        help="Apply the learned-classifier override.",
    )
    parser.add_argument(
        "--judge",
        action="store_true",
        help="Run the LLM judge on the UNCERTAIN bucket.",
    )
    parser.add_argument(
        "--triggered-by",
        default="cron",
        help="Free-form label that goes into the audit log.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of a human summary.",
    )
    args = parser.parse_args()

    configure_logging()
    init_database()
    with SessionLocal() as session:
        result = run_daily_pipeline(
            session,
            do_zotero_sync=not args.skip_zotero_sync,
            do_discovery=True if args.discovery else None,
            do_fulltext=True if args.fulltext else None,
            force_reclassify=args.force_reclassify,
            use_learned=True if args.learned else None,
            use_judge=True if args.judge else None,
            triggered_by=args.triggered_by,
        )

    if args.json:
        print(
            json.dumps(
                {
                    "run_id": result.run_id,
                    "status": result.status,
                    "duration_seconds": result.duration_seconds,
                    "discovered_candidates": result.discovered_candidates,
                    "auto_ingested": result.auto_ingested,
                    "queued_for_review": result.queued_for_review,
                    "classified_new": result.classified_new,
                    "reclassified_stale": result.reclassified_stale,
                    "enqueued_for_review": result.enqueued_for_review,
                    "error_message": result.error_message,
                    "steps": result.steps,
                },
                indent=2,
                default=str,
            )
        )
    else:
        print(
            f"[{result.run_id}] {result.status} in "
            f"{result.duration_seconds:.2f}s"
        )
        print(f"  discovery   : seen={result.discovered_candidates} "
              f"auto={result.auto_ingested} queued={result.queued_for_review}")
        print(f"  classify    : new={result.classified_new} "
              f"refreshed={result.reclassified_stale}")
        print(f"  staged review: queued={result.enqueued_for_review}")
        if result.error_message:
            print(f"  error: {result.error_message}", file=sys.stderr)

    return 0 if result.status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
