"""Attach full-text content to an existing Paper and (re)build chunks + evidence.

Pipeline:
  1. parse_any(path) → list[ParsedSection]
  2. wipe old PaperSection / PaperChunk / PaperEvidence rows for the paper
  3. write fresh PaperSection rows
  4. chunk_sections() → PaperChunk rows (no embeddings yet)
  5. persist_evidence() → PaperEvidence + aggregate score
  6. mark Paper.full_text_available = True, store pdf_path
  7. caller is responsible for `build_chunk_embeddings(session)` afterwards
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AcCorePaper,
    Paper,
    PaperChunk,
    PaperEvidence,
    PaperReference,
    PaperSection,
)
from app.services.chunking_service import (
    chunk_sections,
    contextual_prefix,
    with_parent_context,
)
from app.services.evidence_extractor import persist_evidence
from app.services.normalization_service import normalize_doi
from app.services.pdf_parser import (
    ParsedDocument,
    ParsedReferenceRecord,
    ParsedSection,
    SUPPORTED_FULLTEXT_SUFFIXES,
    parse_any,
)
from app.services.reference_parser import extract_references_from_sections


@dataclass
class FulltextIngestResult:
    paper_id: str
    sections: int
    chunks: int
    evidence_records: int
    fulltext_score: float
    references: int = 0
    references_resolved_corpus: int = 0
    references_resolved_ac_core: int = 0
    backend: str = "txt"


def _wipe_fulltext(session: Session, paper_id: str) -> None:
    for ev in (
        session.execute(
            select(PaperEvidence).where(PaperEvidence.paper_id == paper_id)
        )
        .scalars()
        .all()
    ):
        session.delete(ev)
    for ch in (
        session.execute(
            select(PaperChunk).where(PaperChunk.paper_id == paper_id)
        )
        .scalars()
        .all()
    ):
        session.delete(ch)
    for sec in (
        session.execute(
            select(PaperSection).where(PaperSection.paper_id == paper_id)
        )
        .scalars()
        .all()
    ):
        session.delete(sec)
    for ref in (
        session.execute(
            select(PaperReference).where(PaperReference.citing_paper_id == paper_id)
        )
        .scalars()
        .all()
    ):
        session.delete(ref)
    session.flush()


def _persist_sections(
    session: Session, paper_id: str, sections: list[ParsedSection]
) -> list[PaperSection]:
    rows: list[PaperSection] = []
    for idx, sec in enumerate(sections):
        row = PaperSection(
            id=f"sec_{uuid.uuid4().hex[:12]}",
            paper_id=paper_id,
            section_type=sec.section_type,
            section_title=sec.title,
            content=sec.text,
            page_start=sec.page_start,
            page_end=sec.page_end,
            order_index=idx,
        )
        session.add(row)
        rows.append(row)
    session.flush()
    return rows


def _persist_chunks(
    session: Session,
    paper: Paper,
    sections: list[PaperSection],
    parsed: list[ParsedSection],
) -> int:
    """Section-aware chunking → PaperChunk rows. Embeddings filled in later."""
    chunks = chunk_sections(parsed)
    # Map (section_type, order) → section row id.
    type_to_section: dict[str, PaperSection] = {}
    for sec_row, sec_parsed in zip(sections, parsed):
        type_to_section.setdefault(sec_parsed.section_type, sec_row)

    from app.config import settings

    for chunk in chunks:
        section_row = type_to_section.get(chunk.section_type)
        prefix = contextual_prefix(
            title=paper.title,
            year=paper.year,
            section_type=chunk.section_type,
            section_title=chunk.section_title,
        )
        indexed_text = (
            with_parent_context(chunk.text, prefix, chunk.parent_text)
            if settings.contextual_chunking
            else chunk.text
        )
        session.add(
            PaperChunk(
                id=f"chk_{uuid.uuid4().hex[:12]}",
                paper_id=paper.id,
                section_id=section_row.id if section_row else None,
                section_type=chunk.section_type,
                chunk_text=chunk.text,
                indexed_text=indexed_text,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                token_count=chunk.token_count,
                chunk_metadata={
                    "section_title": chunk.section_title,
                    "year": paper.year,
                    "doi": paper.doi,
                    "venue": paper.venue,
                    "contextual_prefix": prefix,
                    "chunk_kind": "child",
                    "parent_id": chunk.parent_id,
                    "parent_text": chunk.parent_text,
                    "parent_char_start": chunk.parent_char_start,
                    "parent_char_end": chunk.parent_char_end,
                    "parent_token_count": chunk.parent_token_count,
                    "split_strategy": chunk.split_strategy,
                },
            )
        )
    session.flush()
    return len(chunks)


def _persist_references(
    session: Session,
    paper_id: str,
    parsed_sections: list[ParsedSection],
    structured_refs: list[ParsedReferenceRecord] | None = None,
) -> tuple[int, int, int]:
    """Use GROBID-provided structured references when available; otherwise
    fall back to the regex parser on the References section text."""
    if structured_refs:
        # Convert ParsedReferenceRecord into the shape the rest of the function expects.
        from app.services.reference_parser import ParsedReference

        refs = [
            ParsedReference(
                raw_text=r.raw_text,
                doi=r.doi,
                title=r.title,
                year=r.year,
                authors=list(r.authors),
            )
            for r in structured_refs
        ]
    else:
        refs = extract_references_from_sections(parsed_sections)
    if not refs:
        return 0, 0, 0

    # Resolve cited DOIs against (a) our corpus and (b) AC core seeds.
    corpus_doi_to_id: dict[str, str] = {}
    for pid, doi in session.execute(select(Paper.id, Paper.doi)).all():
        if doi:
            corpus_doi_to_id[normalize_doi(doi) or ""] = pid
    ac_core_doi_to_id: dict[str, str] = {}
    for core_id, doi in session.execute(select(AcCorePaper.id, AcCorePaper.doi)).all():
        if doi:
            ac_core_doi_to_id[normalize_doi(doi) or ""] = core_id

    corpus_hits = 0
    ac_hits = 0
    for order, ref in enumerate(refs):
        cited_paper_id = corpus_doi_to_id.get(ref.doi or "")
        cited_ac_core_id = ac_core_doi_to_id.get(ref.doi or "")
        if cited_paper_id and cited_paper_id != paper_id:
            corpus_hits += 1
        if cited_ac_core_id:
            ac_hits += 1
        session.add(
            PaperReference(
                id=f"ref_{uuid.uuid4().hex[:12]}",
                citing_paper_id=paper_id,
                cited_paper_id=cited_paper_id if cited_paper_id != paper_id else None,
                cited_ac_core_id=cited_ac_core_id,
                cited_doi=ref.doi,
                cited_title=ref.title,
                cited_authors=ref.authors or None,
                cited_year=ref.year,
                raw_text=ref.raw_text,
                order_index=order,
            )
        )
    session.flush()
    return len(refs), corpus_hits, ac_hits


def ingest_fulltext_file(
    session: Session,
    paper_id: str,
    path: Path,
    *,
    prefer_grobid: bool | None = None,
) -> FulltextIngestResult:
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise ValueError(f"Paper {paper_id} not found")

    doc = parse_any(path, prefer_grobid=prefer_grobid)
    if not doc.sections:
        raise ValueError(f"No sections parsed from {path}")

    _wipe_fulltext(session, paper_id)
    section_rows = _persist_sections(session, paper_id, doc.sections)
    chunk_count = _persist_chunks(session, paper, section_rows, doc.sections)
    ref_total, ref_corpus_hits, ref_ac_hits = _persist_references(
        session,
        paper_id,
        doc.sections,
        structured_refs=doc.references or None,
    )

    paper.full_text_available = True
    paper.pdf_path = str(path)
    session.flush()

    evidence_count, score = persist_evidence(session, paper_id)
    session.commit()

    return FulltextIngestResult(
        paper_id=paper_id,
        sections=len(section_rows),
        chunks=chunk_count,
        evidence_records=evidence_count,
        fulltext_score=score,
        references=ref_total,
        references_resolved_corpus=ref_corpus_hits,
        references_resolved_ac_core=ref_ac_hits,
        backend=doc.source,
    )


def ingest_fulltext_directory(
    session: Session,
    directory: Path,
    *,
    prefer_grobid: bool | None = None,
) -> list[FulltextIngestResult]:
    """Auto-match files in `directory` to papers by filename stem == paper_id."""
    results: list[FulltextIngestResult] = []
    for path in sorted(Path(directory).glob("*")):
        if path.is_dir():
            continue
        if path.suffix.lower() not in SUPPORTED_FULLTEXT_SUFFIXES:
            continue
        paper_id = path.stem
        if session.get(Paper, paper_id) is None:
            continue
        results.append(
            ingest_fulltext_file(session, paper_id, path, prefer_grobid=prefer_grobid)
        )
    return results


def build_chunk_embeddings(session: Session) -> int:
    """Re-fit the embedder on the current chunk corpus and store per-chunk vectors.

    Uses the contextually-prefixed `indexed_text` when available so retrieval
    benefits from the v0.4 contextual chunking (parse.md §3).
    """
    from app.services.embedding_service import get_embedder

    chunks = list(session.execute(select(PaperChunk)).scalars())
    if not chunks:
        return 0
    embedder = get_embedder()
    corpus = [c.indexed_text or c.chunk_text for c in chunks]
    embedder.fit(corpus)
    matrix = embedder.encode(corpus)
    for chunk, vec in zip(chunks, matrix):
        chunk.embedding = vec.tolist()
        chunk.embedding_backend = embedder.backend
    session.commit()
    return len(chunks)
