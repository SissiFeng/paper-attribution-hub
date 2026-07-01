"""Extract Transferable Knowledge Units (TKUs) for papers.

Usage:
    python -m app.scripts.run_tku_extraction [--provenance ac_gold] [--limit N]
        [--paper-ids P001 P002] [--force] [--json]
    python -m app.scripts.run_tku_extraction --load-examples

Flags:
    --provenance     Only process papers with this provenance (default: ac_gold).
    --limit          Process at most N papers (ordered by paper id).
    --paper-ids      Only process these paper ids.
    --force          Re-extract even if a TKU already exists.
    --load-examples  Load the hand-written example TKUs (no API key needed) and exit.
    --json           Print the summary as JSON instead of text.

LLM extraction needs PAS_KIMI_API_KEY (Kimi/MoonShot) or PAS_ANTHROPIC_API_KEY
in backend/.env. Run cost-conscious: it prints how many papers it will call for.
"""
from __future__ import annotations

import argparse
import json
import sys

from app.db import SessionLocal, init_database


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TKU extraction.")
    parser.add_argument("--provenance", default="ac_gold", help="Provenance filter.")
    parser.add_argument("--limit", type=int, default=None, help="Process at most N.")
    parser.add_argument(
        "--paper-ids", nargs="*", default=None, help="Only process these paper ids."
    )
    parser.add_argument(
        "--force", action="store_true", help="Re-extract even if a TKU exists."
    )
    parser.add_argument(
        "--load-examples",
        action="store_true",
        help="Load hand-written example TKUs and exit.",
    )
    parser.add_argument("--json", action="store_true", help="Print summary as JSON.")
    args = parser.parse_args()

    init_database()

    if args.load_examples:
        from app.services.tku_extractor import load_example_tkus

        with SessionLocal() as session:
            summary = load_example_tkus(session)
        if args.json:
            print(json.dumps(summary))
        else:
            print(
                f"Loaded {summary['loaded']} example TKUs "
                f"({summary['skipped_missing']} skipped: paper not in DB)."
            )
        return 0

    from app.services.tku_extractor import _resolve_client, run_tku_extraction

    with SessionLocal() as session:
        # Preflight: resolve provider and count targets so we don't surprise
        # the user with API spend.
        from sqlalchemy import select

        from app.models import Paper, TransferKnowledgeUnit

        try:
            _call, _provider, model = _resolve_client()
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        stmt = select(Paper).where(Paper.abstract.isnot(None), Paper.abstract != "")
        if args.provenance:
            stmt = stmt.where(Paper.provenance == args.provenance)
        if args.paper_ids:
            stmt = stmt.where(Paper.id.in_(args.paper_ids))
        target_ids = [p.id for p in session.execute(stmt.order_by(Paper.id)).scalars()]
        if args.limit is not None:
            target_ids = target_ids[: args.limit]
        if not args.force:
            existing = set(
                session.execute(select(TransferKnowledgeUnit.paper_id)).scalars()
            )
            to_call = [pid for pid in target_ids if pid not in existing]
        else:
            to_call = target_ids
        print(f"About to call {model} for {len(to_call)} papers")

        summary = run_tku_extraction(
            session,
            paper_ids=args.paper_ids,
            provenance=args.provenance,
            limit=args.limit,
            force=args.force,
        )

    if args.json:
        print(json.dumps(summary))
    else:
        print(
            f"Targeted {summary['targeted']}, extracted {summary['extracted']}, "
            f"skipped {summary['skipped_existing']}, failures {summary['failures']}."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
