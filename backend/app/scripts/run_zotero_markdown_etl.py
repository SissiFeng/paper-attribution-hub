"""Run one S3-triggered Zotero Markdown ETL batch."""
from __future__ import annotations

import argparse
import json
import sys

from app.db import SessionLocal, init_database
from app.logging_utils import configure_logging
from app.services.markdown_etl_service import process_zotero_markdown_batch


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Process one Zotero Markdown batch manifest from S3."
    )
    parser.add_argument("--manifest-key", required=True)
    parser.add_argument(
        "--postprocess",
        action="store_true",
        help=(
            "Explicitly run embeddings, classification, and review-queue "
            "updates after full-text import. Disabled by default."
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    configure_logging()
    init_database()
    with SessionLocal() as session:
        stats = process_zotero_markdown_batch(
            session,
            args.manifest_key,
            run_postprocessing=args.postprocess,
        )

    payload = stats.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            "Zotero Markdown ETL complete:",
            f"processed={stats.processed}",
            f"skipped={stats.skipped_idempotent}",
            f"failed={stats.failed}",
            f"entities={stats.entities}",
            f"postprocessing={stats.postprocessing_run}",
            f"classified={stats.classified_new + stats.reclassified_stale}",
        )
    return 1 if stats.failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(
            f"Zotero Markdown ETL failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
