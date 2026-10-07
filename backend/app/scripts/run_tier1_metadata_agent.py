"""Run the auditable Tier 1 metadata enrichment agent."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.db import SessionLocal, init_database
from app.services.tier1_metadata_agent import run_tier1_metadata_agent


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "DOI-deduplicate a Zotero CSV, enrich paper-specific authorships "
            "with OpenAlex/Crossref/ROR, and persist auditable metadata."
        )
    )
    parser.add_argument("--csv", type=Path, required=True, help="Zotero CSV path.")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="OpenAlex DOI batch size (1-100).",
    )
    parser.add_argument(
        "--max-papers",
        type=int,
        default=None,
        help="Optional smoke-test limit after DOI deduplication.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args()

    init_database()
    with SessionLocal() as session:
        summary = run_tier1_metadata_agent(
            session,
            args.csv,
            batch_size=args.batch_size,
            max_papers=args.max_papers,
        )

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    else:
        print(
            f"Metadata run {summary['run_id']} {summary['status']}: "
            f"{summary['papers_persisted']}/{summary['selected_papers']} papers, "
            f"{summary['authorship_rows']} authorships."
        )
        print(
            f"Resolved affiliation assertions: "
            f"{summary['resolved_affiliation_assertions']}; unresolved: "
            f"{summary['unresolved_affiliation_assertions']}."
        )
    return 0 if summary["status"] == "succeeded" else 1


if __name__ == "__main__":
    sys.exit(main())
