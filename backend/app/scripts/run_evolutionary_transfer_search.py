"""Run evolutionary cross-SDL transfer autosearch.

Usage:
    python -m app.scripts.run_evolutionary_transfer_search --target sdl4
    python -m app.scripts.run_evolutionary_transfer_search --target sdl4 --json
"""
from __future__ import annotations

import argparse
import json

from app.db import SessionLocal, init_database
from app.services.evolutionary_transfer_service import (
    EvolutionConfig,
    export_autosearch_run,
    run_evolutionary_transfer_search,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="target SDL id, e.g. sdl4")
    parser.add_argument("--source-domain", default=None)
    parser.add_argument("--source-pool", type=int, default=24)
    parser.add_argument("--population-size", type=int, default=12)
    parser.add_argument("--generations", type=int, default=6)
    parser.add_argument("--genome-size", type=int, default=3)
    parser.add_argument("--mutation-rate", type=float, default=0.35)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--json", action="store_true", help="print JSON report")
    parser.add_argument(
        "--db-only",
        action="store_true",
        help="use only database TKUs, ignoring outputs/ac_focus_knowledge_md/knowledge_json",
    )
    parser.add_argument(
        "--no-export",
        action="store_true",
        help="run search without writing llm-wiki/autosearch output",
    )
    args = parser.parse_args()

    init_database()
    config = EvolutionConfig(
        target_id=args.target,
        source_domain=args.source_domain,
        source_pool=args.source_pool,
        population_size=args.population_size,
        generations=args.generations,
        genome_size=args.genome_size,
        mutation_rate=args.mutation_rate,
        seed=args.seed,
        include_knowledge_json=not args.db_only,
    )
    with SessionLocal() as session:
        report = run_evolutionary_transfer_search(session, config)
        path = None if args.no_export else export_autosearch_run(report)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    status = "ACCEPTED" if report["accepted"] else "NEEDS_REVIEW"
    best = report.get("best") or {}
    print(f"Evolutionary transfer autosearch: {status}")
    print(f"Target: {report['target']['name']}")
    print(f"Source TKUs: {report['source_count']}")
    print(f"Best score: {best.get('score')}")
    print(f"Hypothesis: {best.get('hypothesis')}")
    if path:
        print(f"Wrote autosearch run to {path}")


if __name__ == "__main__":
    main()
