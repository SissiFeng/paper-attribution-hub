"""Extract typed entities (method/material/instrument/software) for papers.

Usage:
    python -m app.scripts.run_entity_extraction [--paper-ids P001 P002] [--json]

Flags:
    --paper-ids  Only process these paper ids (default: all papers).
    --limit      Process at most N papers (ordered by paper id).
    --offset     Skip the first N papers (ordered by paper id).
    --json       Print the summary as JSON instead of text.
"""
from __future__ import annotations

import argparse
import json
import sys

from app.db import SessionLocal, init_database
from app.services.entity_extractor import run_entity_extraction


def main() -> int:
    parser = argparse.ArgumentParser(description="Run typed entity extraction.")
    parser.add_argument(
        "--paper-ids", nargs="*", default=None, help="Only process these paper ids."
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Process at most N papers."
    )
    parser.add_argument(
        "--offset", type=int, default=None, help="Skip the first N papers."
    )
    parser.add_argument("--json", action="store_true", help="Print summary as JSON.")
    args = parser.parse_args()

    init_database()
    with SessionLocal() as session:
        summary = run_entity_extraction(
            session, paper_ids=args.paper_ids, limit=args.limit, offset=args.offset
        )
        session.commit()

    if args.json:
        print(json.dumps(summary))
    else:
        print(
            f"Extracted {summary['entities']} entities from "
            f"{summary['papers_processed']} papers."
        )
        for entity_type, count in sorted(summary["by_type"].items()):
            print(f"  {entity_type}: {count}")
    if args.paper_ids and summary["papers_processed"] == 0:
        print("No matching papers found.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
