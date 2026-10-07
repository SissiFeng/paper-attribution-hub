"""Build classification-neutral scientific knowledge for full-text papers."""

from __future__ import annotations

import argparse
import json
import sys

from app.db import SessionLocal, init_database
from app.services.scientific_knowledge_service import (
    compile_scientific_knowledge_batch,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--paper-id",
        action="append",
        dest="paper_ids",
        help="Compile only this paper ID. Repeat to select multiple papers.",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")

    init_database()
    with SessionLocal() as session:
        result = compile_scientific_knowledge_batch(
            session,
            paper_ids=args.paper_ids,
            limit=args.limit,
        )
        session.commit()

    payload = result.as_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            "Scientific knowledge build complete:",
            f"selected={result.selected}",
            f"changed={result.changed}",
            f"unchanged={result.unchanged}",
            f"failed={result.failed}",
        )
    return 1 if result.failed else 0


if __name__ == "__main__":
    sys.exit(main())
