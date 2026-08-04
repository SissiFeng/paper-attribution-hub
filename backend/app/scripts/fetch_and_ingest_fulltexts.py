"""Download open-access PDFs and run them through the full-text pipeline.

Priority ordering (highest first)
-----------------------------------
1. CORE_RELEVANT + RELATED_RELEVANT — smallest set, highest attribution value
2. provenance=ac_gold               — AC papers not found by Scopus retrieval
3. UNCERTAIN with review_priority ≥ 0.6
4. SDL_FIELD_RELEVANT + full SDL architecture (all 3 components)
5. SDL_FIELD_RELEVANT               — broad SDL field coverage

Within each tier, papers without a DOI are skipped.
Papers that already have full_text_available=True are skipped unless --force.

Usage
-----
    python -m app.scripts.fetch_and_ingest_fulltexts [OPTIONS]

Options
-------
--limit N         Stop after N successful downloads (default: 500)
--tier {1,2,3,4,5,all}
                  Only process the given priority tier (default: all)
--force           Re-download even if full_text_available=True
--rate-limit S    Seconds between HTTP requests (default: 1.0)
--dry-run         Print which papers would be fetched, don't download
--grobid          Use GROBID parser instead of PyMuPDF
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal, init_database

FULLTEXTS_DIR = settings.fulltexts_dir


def _priority_queries(session: Session, force: bool) -> list[tuple[int, list]]:
    """Return list of (priority_tier, paper_rows) in priority order."""
    from app.models import Paper, PaperClassification
    from app.services.relevance_classifier import (
        LABEL_CORE,
        LABEL_RELATED,
        LABEL_SDL_FIELD,
        LABEL_UNCERTAIN,
    )

    base = select(Paper, PaperClassification).join(
        PaperClassification, PaperClassification.paper_id == Paper.id, isouter=True
    ).where(Paper.doi.isnot(None))

    if not force:
        base = base.where(Paper.full_text_available == False)  # noqa: E712

    tiers = []

    # Tier 1: CORE + RELATED
    q1 = base.where(
        PaperClassification.label.in_([LABEL_CORE, LABEL_RELATED])
    )
    tiers.append((1, session.execute(q1).all()))

    # Tier 2: AC gold papers not from Scopus retrieval
    q2 = base.where(Paper.provenance == "ac_gold")
    tiers.append((2, session.execute(q2).all()))

    # Tier 3: UNCERTAIN with high priority
    q3 = base.where(
        and_(
            PaperClassification.label == LABEL_UNCERTAIN,
            PaperClassification.review_priority >= 0.6,
        )
    )
    tiers.append((3, session.execute(q3).all()))

    # Tier 4: SDL_FIELD_RELEVANT + full architecture
    q4 = base.where(
        and_(
            PaperClassification.label == LABEL_SDL_FIELD,
            Paper.ai_decision_score == 1.0,
            Paper.automation_score == 1.0,
            Paper.closed_loop_score == 1.0,
        )
    )
    tiers.append((4, session.execute(q4).all()))

    # Tier 5: Remaining SDL_FIELD_RELEVANT
    q5 = base.where(PaperClassification.label == LABEL_SDL_FIELD)
    tiers.append((5, session.execute(q5).all()))

    return tiers


def run(
    limit: int = 500,
    tier_filter: str = "all",
    force: bool = False,
    rate_limit: float = 1.0,
    dry_run: bool = False,
    use_grobid: bool = False,
) -> None:
    init_database()
    FULLTEXTS_DIR.mkdir(parents=True, exist_ok=True)

    from app.services.fulltext_fetcher import fetch_and_ingest
    from app.services.scopus_classifier import run_scopus_classification

    stats = {
        "attempted": 0,
        "succeeded": 0,
        "failed_no_url": 0,
        "failed_download": 0,
        "failed_parse": 0,
        "skipped_existing": 0,
    }

    with SessionLocal() as session:
        tiers = _priority_queries(session, force)

        for tier_num, rows in tiers:
            if tier_filter != "all" and str(tier_num) != tier_filter:
                continue

            tier_count = len(rows)
            print(
                f"\n[tier {tier_num}] {tier_count} papers",
                file=sys.stderr,
            )

            for paper, cls in rows:
                if stats["succeeded"] >= limit:
                    break

                doi = paper.doi
                if not doi:
                    continue

                stats["attempted"] += 1

                if dry_run:
                    label = cls.label if cls else "unclassified"
                    print(f"  [dry-run] {doi}  label={label}  id={paper.id}")
                    continue

                ok, reason = fetch_and_ingest(
                    session,
                    paper.id,
                    doi,
                    FULLTEXTS_DIR,
                    prefer_grobid=True if use_grobid else None,
                    rate_limit_s=rate_limit,
                )

                if ok:
                    stats["succeeded"] += 1
                    print(
                        f"  ✓ [{stats['succeeded']:>4}/{limit}] {doi[:60]}  ({reason})",
                        file=sys.stderr,
                    )
                else:
                    if "no OA URL" in reason:
                        stats["failed_no_url"] += 1
                    elif "download failed" in reason:
                        stats["failed_download"] += 1
                    else:
                        stats["failed_parse"] += 1
                    print(
                        f"  ✗ {doi[:60]}  {reason}",
                        file=sys.stderr,
                    )

                # Flush every 50 successes
                if stats["succeeded"] % 50 == 0 and stats["succeeded"] > 0:
                    session.commit()

            if stats["succeeded"] >= limit:
                break

        if not dry_run and stats["succeeded"] > 0:
            session.commit()

            # Re-classify papers that now have full text
            print(
                f"\nRe-classifying {stats['succeeded']} papers with new full text...",
                file=sys.stderr,
            )
            reclassify_stats = run_scopus_classification(session)
            print(f"  Re-classified: {reclassify_stats}", file=sys.stderr)

    print("\n── Fetch summary ──────────────────────────", file=sys.stderr)
    for k, v in stats.items():
        print(f"  {k:<22} {v}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch OA full texts and run through fulltext pipeline."
    )
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--tier", default="all", choices=["1", "2", "3", "4", "5", "all"])
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--rate-limit", type=float, default=1.0, dest="rate_limit")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--grobid", action="store_true")
    args = parser.parse_args()

    run(
        limit=args.limit,
        tier_filter=args.tier,
        force=args.force,
        rate_limit=args.rate_limit,
        dry_run=args.dry_run,
        use_grobid=args.grobid,
    )


if __name__ == "__main__":
    main()
