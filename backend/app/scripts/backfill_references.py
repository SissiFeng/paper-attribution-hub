"""Backfill paper_references from OpenAlex for lab-linked papers.

The Scopus batch CSV carries only Reference_Count, so the citation graph is
empty for that corpus and the lab-to-lab citation-flow matrix has nothing to
count. This script fills the gap: for every paper linked to an SDL lab (via
paper_lab_links) that has a DOI, it fetches the OpenAlex work record, reads
`referenced_works`, and writes a PaperReference row for each reference that
resolves to another paper in our corpus.

Resolution is done within the fetched set: pass 1 fetches every target
paper's work record and builds {openalex_id -> paper_id}; pass 2 inserts
edges whose cited OpenAlex id appears in that map. References that point
outside the corpus are not stored (they carry no signal for lab-to-lab flow
and would add ~40 rows of noise per paper).

Rows created here use raw_text = "openalex:<work_id>" so re-runs can replace
them idempotently without touching references parsed from PDF full text.

Usage:
    python -m app.scripts.backfill_references [--limit N] [--all-papers] [--json]

Requires network access to api.openalex.org (responses are cached in
external_cache, so interrupted runs resume cheaply).
"""
from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal, init_database
from app.models import Paper, PaperReference
from app.models.sdl import PaperLabLink
from app.services.external.openalex_client import OpenAlexClient

RAW_TEXT_PREFIX = "openalex:"


def _target_papers(session: Session, all_papers: bool, limit: int | None) -> list[Paper]:
    stmt = select(Paper).where(Paper.doi.is_not(None))
    if not all_papers:
        stmt = stmt.where(Paper.id.in_(select(PaperLabLink.paper_id)))
    stmt = stmt.order_by(Paper.id)
    if limit:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt))


def backfill_references(
    session: Session,
    client: OpenAlexClient | None = None,
    *,
    all_papers: bool = False,
    limit: int | None = None,
) -> dict:
    """Fetch referenced_works for target papers and store corpus-internal edges."""
    owns_client = client is None
    client = client or OpenAlexClient()
    papers = _target_papers(session, all_papers, limit)

    works: dict[str, dict] = {}  # paper_id -> work payload
    openalex_to_paper: dict[str, str] = {}
    fetched = 0
    misses = 0
    try:
        for paper in papers:
            work = client.work_by_doi(session, paper.doi)
            if not work or not work.get("id"):
                misses += 1
                continue
            fetched += 1
            works[paper.id] = work
            openalex_to_paper[work["id"]] = paper.id
    finally:
        if owns_client:
            client.close()

    edges_created = 0
    edges_replaced = 0
    for paper_id, work in works.items():
        refs = work.get("referenced_works") or []
        resolved = [
            (ref_id, openalex_to_paper[ref_id])
            for ref_id in refs
            if ref_id in openalex_to_paper and openalex_to_paper[ref_id] != paper_id
        ]
        # Idempotent replace of previously backfilled rows for this paper.
        existing = session.scalars(
            select(PaperReference).where(
                PaperReference.citing_paper_id == paper_id,
                PaperReference.raw_text.like(f"{RAW_TEXT_PREFIX}%"),
            )
        ).all()
        for row in existing:
            session.delete(row)
        edges_replaced += len(existing)
        for order_index, (ref_id, cited_paper_id) in enumerate(resolved):
            session.add(
                PaperReference(
                    id=f"ref-oa-{paper_id}-{ref_id.rsplit('/', 1)[-1]}",
                    citing_paper_id=paper_id,
                    cited_paper_id=cited_paper_id,
                    cited_doi=session.get(Paper, cited_paper_id).doi,
                    raw_text=f"{RAW_TEXT_PREFIX}{ref_id}",
                    order_index=order_index,
                )
            )
            edges_created += 1
    session.commit()

    return {
        "papers_targeted": len(papers),
        "works_fetched": fetched,
        "doi_misses": misses,
        "edges_created": edges_created,
        "edges_replaced": edges_replaced,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Max papers to process")
    parser.add_argument(
        "--all-papers",
        action="store_true",
        help="Process every paper with a DOI, not just lab-linked ones",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable summary")
    args = parser.parse_args()

    init_database()
    session = SessionLocal()
    try:
        summary = backfill_references(
            session, all_papers=args.all_papers, limit=args.limit
        )
    finally:
        session.close()

    if args.json:
        print(json.dumps(summary))
    else:
        print(
            f"Targeted {summary['papers_targeted']} papers, fetched "
            f"{summary['works_fetched']} works ({summary['doi_misses']} DOI misses); "
            f"created {summary['edges_created']} corpus-internal reference edges "
            f"(replaced {summary['edges_replaced']})."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
