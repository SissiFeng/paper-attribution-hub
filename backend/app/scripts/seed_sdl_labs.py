"""Seed the SDL lab registry from data/sdl_labs.yaml and map papers to labs.

Usage:
    python -m app.scripts.seed_sdl_labs [--json]

Flags:
    --json  Print the summary as JSON instead of text.
"""
from __future__ import annotations

import argparse
import json
import sys

from app.db import SessionLocal, init_database
from app.services.lab_service import load_labs_from_yaml, map_papers_to_labs


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed SDL labs and map papers.")
    parser.add_argument("--json", action="store_true", help="Print summary as JSON.")
    args = parser.parse_args()

    init_database()
    with SessionLocal() as session:
        lab_summary = load_labs_from_yaml(session)
        map_summary = map_papers_to_labs(session)
        session.commit()

    summary = {"labs": lab_summary, "mapping": map_summary}
    if args.json:
        print(json.dumps(summary))
    else:
        print(
            f"Labs: {lab_summary['created']} created, "
            f"{lab_summary['updated']} updated."
        )
        print(
            f"Mapping: {map_summary['links_created']} new links "
            f"({map_summary['papers_linked']} papers) across "
            f"{map_summary['labs']} labs."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
