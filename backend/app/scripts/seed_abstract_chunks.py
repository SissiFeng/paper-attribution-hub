"""Seed the RAG corpus from paper abstracts + metadata fields.

Since we don't have PDF full-texts in production, this script creates
PaperChunk rows from each paper's abstract, title, and keyword fields.
After seeding, it rebuilds all embeddings so /retrieve works immediately.

Usage:
    python -m app.scripts.seed_abstract_chunks [--force] [--limit N]

Flags:
    --force   Re-seed papers that already have chunks (wipe + rebuild).
    --limit N Process at most N papers (useful for testing).
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Paper, PaperChunk
from app.services.chunking_service import contextual_prefix, with_context
from app.services.fulltext_service import build_chunk_embeddings


def _chunk_id(paper_id: str, section_type: str, index: int) -> str:
    key = f"{paper_id}:{section_type}:{index}"
    return "abs_" + hashlib.sha1(key.encode()).hexdigest()[:16]


def _make_chunks(paper: Paper) -> list[dict]:
    """Return raw chunk dicts for a paper using abstract + keyword fields."""
    chunks = []

    # --- Abstract chunk ---
    abstract = (paper.abstract or "").strip()
    if abstract:
        prefix = contextual_prefix(
            title=paper.title or "",
            year=paper.year,
            section_type="abstract",
            section_title="Abstract",
        )
        indexed = with_context(abstract, prefix)
        tokens = len(abstract.split())
        chunks.append({
            "id": _chunk_id(paper.id, "abstract", 0),
            "paper_id": paper.id,
            "section_type": "abstract",
            "chunk_text": abstract,
            "indexed_text": indexed,
            "char_start": 0,
            "char_end": len(abstract),
            "token_count": tokens,
            "chunk_metadata": {
                "section_title": "Abstract",
                "year": paper.year,
                "doi": paper.doi,
                "venue": paper.venue,
                "contextual_prefix": prefix,
            },
        })

    # --- Keywords / tags chunk ---
    kw_parts: list[str] = []
    for field in (paper.keywords, paper.indexed_keywords, paper.sdl_tags, paper.research_tags):
        if field:
            kw_parts.extend(str(k).strip() for k in field if str(k).strip())

    if kw_parts:
        kw_text = "; ".join(dict.fromkeys(kw_parts))  # deduplicate, preserve order
        prefix = contextual_prefix(
            title=paper.title or "",
            year=paper.year,
            section_type="keywords",
            section_title="Keywords and Tags",
        )
        indexed = with_context(kw_text, prefix)
        chunks.append({
            "id": _chunk_id(paper.id, "keywords", 0),
            "paper_id": paper.id,
            "section_type": "keywords",
            "chunk_text": kw_text,
            "indexed_text": indexed,
            "char_start": 0,
            "char_end": len(kw_text),
            "token_count": len(kw_text.split()),
            "chunk_metadata": {
                "section_title": "Keywords and Tags",
                "year": paper.year,
                "doi": paper.doi,
                "venue": paper.venue,
                "contextual_prefix": prefix,
            },
        })

    return chunks


def seed_paper(session: Session, paper: Paper, force: bool = False) -> int:
    """Create chunks for a single paper. Returns number of chunks created."""
    existing = session.execute(
        select(PaperChunk.id).where(PaperChunk.paper_id == paper.id).limit(1)
    ).first()
    if existing and not force:
        return 0
    if existing and force:
        session.execute(
            PaperChunk.__table__.delete().where(PaperChunk.paper_id == paper.id)
        )

    raw = _make_chunks(paper)
    if not raw:
        return 0

    now = datetime.now(timezone.utc)
    for c in raw:
        session.add(PaperChunk(
            id=c["id"],
            paper_id=c["paper_id"],
            section_type=c["section_type"],
            chunk_text=c["chunk_text"],
            indexed_text=c["indexed_text"],
            char_start=c["char_start"],
            char_end=c["char_end"],
            token_count=c["token_count"],
            chunk_metadata=c["chunk_metadata"],
            created_at=now,
        ))
    return len(raw)


def run(force: bool = False, limit: int | None = None) -> None:
    with SessionLocal() as session:
        stmt = select(Paper).order_by(Paper.year.desc())
        if limit:
            stmt = stmt.limit(limit)
        papers = list(session.execute(stmt).scalars())

        total_created = 0
        for i, paper in enumerate(papers, 1):
            n = seed_paper(session, paper, force=force)
            total_created += n
            if i % 500 == 0:
                session.flush()
                print(f"  [{i}/{len(papers)}] {total_created} chunks so far…", flush=True)

        session.commit()
        print(f"Seeded {total_created} chunks from {len(papers)} papers.")

        if total_created > 0:
            print("Building embeddings…", flush=True)
            built = build_chunk_embeddings(session)
            session.commit()
            print(f"Embedded {built} chunks.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Wipe and re-seed existing chunks")
    parser.add_argument("--limit", type=int, default=None, help="Max papers to process")
    args = parser.parse_args()
    run(force=args.force, limit=args.limit)
    sys.exit(0)
