"""End-to-end pipeline: ingest → classify → print summary.

Usage:
    python -m app.scripts.run_classification [--reset] [--verbose]
"""
from __future__ import annotations

import argparse
from collections import Counter

from app.adapters import CsvPaperSource
from app.config import settings
from app.db import SessionLocal, init_database, reset_database
from app.services.fulltext_service import build_chunk_embeddings, ingest_fulltext_directory
from app.services.ingestion_service import ingest_all
from app.services.relevance_classifier import classify_all


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full attribution pipeline.")
    parser.add_argument("--reset", action="store_true", help="Drop tables first.")
    parser.add_argument("--verbose", action="store_true", help="Print per-paper detail.")
    parser.add_argument(
        "--with-fulltext",
        action="store_true",
        help=f"Also ingest full-texts from {settings.fulltexts_dir} (v0.2).",
    )
    parser.add_argument(
        "--grobid",
        dest="prefer_grobid",
        action="store_true",
        default=None,
        help="Force GROBID for PDF parsing.",
    )
    parser.add_argument(
        "--no-grobid",
        dest="prefer_grobid",
        action="store_false",
        help="Force PyMuPDF, even if GROBID is configured.",
    )
    args = parser.parse_args()

    if args.reset:
        reset_database()
    else:
        init_database()

    source = CsvPaperSource(
        papers_csv=settings.papers_csv,
        people_csv=settings.people_csv,
        institutions_csv=settings.institutions_csv,
        topics_yaml=settings.topics_yaml,
    )

    with SessionLocal() as session:
        stats = ingest_all(session, source)
        fulltext_count = 0
        if args.with_fulltext and settings.fulltexts_dir.exists():
            results = ingest_fulltext_directory(
                session, settings.fulltexts_dir, prefer_grobid=args.prefer_grobid
            )
            fulltext_count = len(results)
            build_chunk_embeddings(session)
        papers = classify_all(session)

    print("=" * 72)
    print(f"Ingestion: {stats.papers} new papers, "
          f"{stats.people} people, {stats.institutions} institutions, "
          f"{stats.topics} topics. Skipped {stats.skipped_duplicates} duplicate DOIs.")
    if args.with_fulltext:
        print(f"Full-text: {fulltext_count} files ingested.")

    counts = Counter(p.classification.label for p in papers if p.classification)
    print("Classification labels:", dict(counts))
    print("=" * 72)

    if args.verbose:
        for p in papers:
            c = p.classification
            if c is None:
                continue
            print(f"\n[{c.label}] ({c.confidence:.2f})  {p.id}: {p.title[:80]}")
            print(
                f"  scores  author={c.author_score:.2f} "
                f"inst={c.institution_score:.2f} "
                f"topic={c.topic_score:.2f} "
                f"fulltext={c.fulltext_evidence_score:.2f}"
            )
            for r in c.reasons or []:
                print(f"  - {r}")


if __name__ == "__main__":
    main()
