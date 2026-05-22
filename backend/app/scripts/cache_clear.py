"""Clear the external_cache table.

Usage:
    python -m app.scripts.cache_clear              # everything
    python -m app.scripts.cache_clear --source openalex
"""
from __future__ import annotations

import argparse

from app.db import SessionLocal, init_database
from app.services.external import invalidate_cache


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        choices=["openalex", "semantic_scholar", "crossref"],
        default=None,
        help="Restrict to one source. Default: clear everything.",
    )
    args = parser.parse_args()

    init_database()
    with SessionLocal() as session:
        n = invalidate_cache(session, source=args.source)
    print(f"Removed {n} cache rows.")


if __name__ == "__main__":
    main()
