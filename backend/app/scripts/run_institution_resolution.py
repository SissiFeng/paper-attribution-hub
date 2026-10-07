"""Resolve current PDF-derived institution candidates with official ROR."""
from __future__ import annotations

import argparse
import json
import sys

from app.db import SessionLocal, init_database
from app.services.institution_resolution_service import (
    resolve_institution_entities_with_ror,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve PDF-derived affiliation candidates with ROR."
    )
    parser.add_argument(
        "--paper-ids",
        nargs="*",
        default=None,
        help="Only process these paper ids.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    init_database()
    with SessionLocal() as session:
        summary = resolve_institution_entities_with_ror(
            session,
            paper_ids=args.paper_ids,
        )
        session.commit()

    if args.json:
        print(json.dumps(summary))
    else:
        print(
            f"Resolved {summary['matched']} institution rows from "
            f"{summary['candidates']} candidates."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
