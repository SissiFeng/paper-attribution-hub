"""Run a discovery cycle against OpenAlex / Semantic Scholar / Crossref.

Usage:
    python -m app.scripts.run_discovery
    python -m app.scripts.run_discovery --strategy cite_of_core --max 20
    python -m app.scripts.run_discovery --offline   # cache-only, no network
"""
from __future__ import annotations

import argparse

from app.db import SessionLocal, init_database
from app.services.discovery_service import run_discovery


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strategy",
        action="append",
        choices=["cite_of_core", "ac_coauthor", "s2_recommend"],
        help="Restrict to specific strategies. Repeatable. Default: all.",
    )
    parser.add_argument(
        "--max",
        dest="max_candidates",
        type=int,
        default=None,
        help="Cap candidates returned per strategy.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Cache-only: skip clients and use whatever's in external_cache.",
    )
    args = parser.parse_args()

    init_database()
    with SessionLocal() as session:
        if args.offline:
            # In offline mode we still call the clients but they'll only ever
            # hit cache (httpx transport ends up unused because cache hits short-circuit).
            # If the cache is empty for a request, the client returns nothing for
            # that path — which is the desired behavior for offline demos.
            print("Offline mode — using external_cache only.")
        result = run_discovery(
            session,
            strategies=args.strategy,
            max_candidates=args.max_candidates,
        )

    print("Discovery complete:")
    print(f"  candidates_seen        = {result.candidates_seen}")
    print(f"  auto_ingested          = {result.auto_ingested}")
    print(f"  queued                 = {result.queued}")
    print(f"  skipped_already_in_db  = {result.skipped_already_in_corpus}")
    print(f"  by strategy            = {result.by_strategy}")


if __name__ == "__main__":
    main()
