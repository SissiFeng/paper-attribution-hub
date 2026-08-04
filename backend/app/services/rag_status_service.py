"""RAG status per paper — chunk/embedding/evidence counts."""
from __future__ import annotations
from collections import defaultdict
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Paper, PaperChunk, PaperEvidence
from app.schemas import RagStatusOut

ATTRIBUTION_EVIDENCE_TYPES = {"funding_acknowledgement","sdl_methodology","figure_caption_sdl"}

def rag_status_by_paper(session: Session, paper_ids: list[str]) -> dict[str, RagStatusOut]:
    if not paper_ids:
        return {}
    chunk_rows = session.execute(
        select(PaperChunk.paper_id, PaperChunk.embedding).where(PaperChunk.paper_id.in_(paper_ids))
    ).all()
    chunk_count: dict[str, int] = defaultdict(int)
    embedded_count: dict[str, int] = defaultdict(int)
    for pid, emb in chunk_rows:
        chunk_count[pid] += 1
        if emb:
            embedded_count[pid] += 1
    ev_rows = session.execute(
        select(PaperEvidence.paper_id, PaperEvidence.evidence_type).where(PaperEvidence.paper_id.in_(paper_ids))
    ).all()
    ev_count: dict[str, int] = defaultdict(int)
    attr_ev_count: dict[str, int] = defaultdict(int)
    for pid, ev_type in ev_rows:
        ev_count[pid] += 1
        if ev_type in ATTRIBUTION_EVIDENCE_TYPES:
            attr_ev_count[pid] += 1
    ft_map = dict(session.execute(
        select(Paper.id, Paper.full_text_available).where(Paper.id.in_(paper_ids))
    ).all())
    result: dict[str, RagStatusOut] = {}
    for pid in paper_ids:
        ft = bool(ft_map.get(pid, False))
        cc, ec, evc, aec = chunk_count[pid], embedded_count[pid], ev_count[pid], attr_ev_count[pid]
        if not ft:
            s, ready, action, hint = "missing_fulltext", False, "upload_or_fetch_fulltext", "Upload or fetch the PDF to enable full-text evidence."
        elif cc == 0:
            s, ready, action, hint = "not_chunked", False, "run_chunker", "POST /admin/seed-chunks to create abstract chunks."
        elif ec == 0:
            s, ready, action, hint = "not_embedded", False, "build_embeddings", "POST /admin/seed-chunks --force to rebuild embeddings."
        else:
            s, ready, action, hint = "ready", True, None, None
        result[pid] = RagStatusOut(status=s, ready=ready, full_text_available=ft,
            chunk_count=cc, embedded_chunk_count=ec, evidence_count=evc,
            attribution_evidence_count=aec, needs_action=action, action_hint=hint)
    return result
