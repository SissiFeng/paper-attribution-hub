"""Ingest full-text files from a directory.

Usage:
    python -m app.scripts.ingest_fulltexts [--dir data/fulltexts] [--paper P001]
"""
from __future__ import annotations

import argparse
from pathlib import Path

from app.config import settings
from app.db import SessionLocal, init_database
from app.services.fulltext_service import (
    build_chunk_embeddings,
    ingest_fulltext_directory,
    ingest_fulltext_file,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, default=settings.fulltexts_dir)
    parser.add_argument(
        "--paper",
        action="append",
        default=[],
        help="Ingest a specific paper id (matching filename stem). Repeatable.",
    )
    parser.add_argument(
        "--skip-embed",
        action="store_true",
        help="Skip the embedding step (useful for fast tests).",
    )
    parser.add_argument(
        "--grobid",
        dest="prefer_grobid",
        action="store_true",
        default=None,
        help="Force GROBID for PDF parsing (PAS_GROBID_URL must be reachable).",
    )
    parser.add_argument(
        "--no-grobid",
        dest="prefer_grobid",
        action="store_false",
        help="Force PyMuPDF, even if GROBID is configured.",
    )
    args = parser.parse_args()

    init_database()
    with SessionLocal() as session:
        if args.paper:
            results = []
            for pid in args.paper:
                candidates = [args.dir / f"{pid}.txt", args.dir / f"{pid}.pdf"]
                path = next((c for c in candidates if c.exists()), None)
                if path is None:
                    print(f"  ! no file for {pid}")
                    continue
                results.append(
                    ingest_fulltext_file(
                        session, pid, path, prefer_grobid=args.prefer_grobid
                    )
                )
        else:
            results = ingest_fulltext_directory(
                session, args.dir, prefer_grobid=args.prefer_grobid
            )

        print(f"Ingested {len(results)} full-text files")
        backend_counts: dict[str, int] = {}
        for r in results:
            backend_counts[r.backend] = backend_counts.get(r.backend, 0) + 1
            print(
                f"  {r.paper_id} [{r.backend}]: {r.sections} sections, "
                f"{r.chunks} chunks, {r.evidence_records} evidence rows, "
                f"{r.references} refs ({r.references_resolved_ac_core} → AC core), "
                f"score={r.fulltext_score:.2f}"
            )
        if backend_counts:
            print(
                "Parse backends: "
                + ", ".join(f"{k}={v}" for k, v in backend_counts.items())
            )

        if not args.skip_embed:
            n = build_chunk_embeddings(session)
            print(f"Built embeddings for {n} chunks")


if __name__ == "__main__":
    main()
