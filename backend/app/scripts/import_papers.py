"""Idempotently load CSV/YAML sources into the database.

Usage:
    python -m app.scripts.import_papers [--reset]
"""
from __future__ import annotations

import argparse

from app.adapters import CsvPaperSource
from app.config import settings
from app.db import SessionLocal, init_database, reset_database
from app.services.ingestion_service import ingest_all


def main() -> None:
    parser = argparse.ArgumentParser(description="Import papers + metadata into the DB.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop and recreate tables before importing.",
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

    print(
        "Ingestion complete:",
        f"papers={stats.papers}",
        f"people={stats.people}",
        f"institutions={stats.institutions}",
        f"topics={stats.topics}",
        f"skipped_duplicates={stats.skipped_duplicates}",
    )


if __name__ == "__main__":
    main()
