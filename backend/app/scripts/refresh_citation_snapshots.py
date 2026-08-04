"""Refresh time-stamped OpenAlex citation counts.

Usage:
    python -m app.scripts.refresh_citation_snapshots [--limit N] [--json]
"""

from __future__ import annotations

import argparse
import json

from app.db import SessionLocal, init_database
from app.services.citation_snapshot_service import (
    refresh_openalex_citation_snapshots,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    init_database()
    with SessionLocal() as session:
        result = refresh_openalex_citation_snapshots(
            session,
            limit=args.limit,
        )
    print(json.dumps(result) if args.json else result)


if __name__ == "__main__":
    main()
