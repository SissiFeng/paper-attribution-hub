from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Paper, PaperChunk
from app.schemas import ChunkOut, RetrieveRequest
from app.services.embedding_service import get_embedder
from app.services.fulltext_service import build_chunk_embeddings, ingest_fulltext_file
from app.services.relevance_classifier import classify_all
from app.services.reranker import get_reranker
from app.services.retrieval_service import HybridIndex

router = APIRouter(tags=["fulltext"])


class AnswerRequest(BaseModel):
    query: str
    top_k: int = 8
    alpha: float = 0.5
    year_from: int | None = None
    year_to: int | None = None
    paper_ids: list[str] | None = None


class SourceOut(BaseModel):
    chunk_id: str
    paper_id: str
    section_type: str
    section_title: str | None = None
    text: str
    score: float
    bm25_score: float
    cosine_score: float


class AnswerOut(BaseModel):
    answer: str
    sources: list[SourceOut]
    model: str
    chunks_retrieved: int


@router.post("/papers/{paper_id}/fulltext", response_model=dict)
async def upload_fulltext(
    paper_id: str,
    file: UploadFile,
    session: Session = Depends(get_session),
) -> dict:
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail=f"Paper {paper_id} not found")

    suffix = Path(file.filename or "").suffix.lower() or ".txt"
    if suffix not in {".pdf", ".txt", ".md"}:
        raise HTTPException(status_code=415, detail="Only .pdf / .txt / .md accepted")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        result = ingest_fulltext_file(session, paper_id, tmp_path)
        build_chunk_embeddings(session)
        classify_all(session)
    finally:
        tmp_path.unlink(missing_ok=True)

    return {
        "paper_id": result.paper_id,
        "sections": result.sections,
        "chunks": result.chunks,
        "evidence_records": result.evidence_records,
        "fulltext_score": result.fulltext_score,
    }


@router.get("/papers/{paper_id}/chunks", response_model=list[ChunkOut])
def list_chunks(paper_id: str, session: Session = Depends(get_session)) -> list[ChunkOut]:
    rows = (
        session.execute(
            select(PaperChunk).where(PaperChunk.paper_id == paper_id)
        )
        .scalars()
        .all()
    )
    return [
        ChunkOut(
            chunk_id=c.id,
            paper_id=c.paper_id,
            section_type=c.section_type,
            section_title=(c.chunk_metadata or {}).get("section_title"),
            text=c.chunk_text,
            token_count=c.token_count,
        )
        for c in rows
    ]


@router.post("/retrieve", response_model=list[ChunkOut])
def retrieve(payload: RetrieveRequest, session: Session = Depends(get_session)) -> list[ChunkOut]:
    chunks = list(session.execute(select(PaperChunk)).scalars())
    if not chunks:
        return []

    # Rebuild embedder + index on demand. For a corpus of thousands this is
    # cheap (TF-IDF over a few hundred chunks runs in <50ms).
    embedder = get_embedder()
    embedder.fit([c.chunk_text for c in chunks])

    index = HybridIndex.from_session(session, embedder)
    year_range: tuple[int | None, int | None] | None = None
    if payload.year_from is not None or payload.year_to is not None:
        year_range = (payload.year_from, payload.year_to)

    retrieved = index.search(
        payload.query,
        paper_ids=payload.paper_ids,
        section_types=payload.section_types,
        year_range=year_range,
        # Pull a wider net for the reranker; trim back to top_k after rerank.
        top_k=max(payload.top_k * 3, payload.top_k),
        alpha=payload.alpha,
    )
    retrieved = get_reranker().rerank(payload.query, retrieved)[: payload.top_k]
    return [
        ChunkOut(
            chunk_id=r.chunk_id,
            paper_id=r.paper_id,
            section_type=r.section_type,
            section_title=r.section_title,
            text=r.text,
            token_count=len(r.text.split()),
            score=r.score,
            bm25_score=r.bm25_score,
            cosine_score=r.cosine_score,
        )
        for r in retrieved
    ]


@router.post("/retrieve/answer", response_model=AnswerOut)
def retrieve_answer(
    payload: AnswerRequest,
    session: Session = Depends(get_session),
) -> AnswerOut:
    """Advanced RAG endpoint: hybrid retrieval → LLM re-ranking → grounded answer.

    Pipeline:
    1. Hybrid BM25 + cosine search with Reciprocal Rank Fusion
    2. Retrieve 3× top_k candidates for the reranker to work on
    3. Re-rank via ClaudeReranker (if PAS_RERANKER=claude) or NullReranker
    4. Trim to top_k and generate a citation-grounded answer with Claude
    """
    chunks = list(session.execute(select(PaperChunk)).scalars())
    if not chunks:
        return AnswerOut(
            answer="The knowledge base is empty — no paper chunks have been indexed yet. "
                   "Run `python -m app.scripts.seed_abstract_chunks` to seed the corpus.",
            sources=[],
            model="none",
            chunks_retrieved=0,
        )

    embedder = get_embedder()
    index = HybridIndex.from_session(session, embedder)
    year_range: tuple[int | None, int | None] | None = None
    if payload.year_from is not None or payload.year_to is not None:
        year_range = (payload.year_from, payload.year_to)

    # Fetch wider net for re-ranking
    candidates = index.search(
        payload.query,
        paper_ids=payload.paper_ids,
        year_range=year_range,
        top_k=max(payload.top_k * 4, 20),
        alpha=payload.alpha,
    )
    # Re-rank (Claude or null)
    reranked = get_reranker().rerank(payload.query, candidates)[: payload.top_k]

    sources = [
        SourceOut(
            chunk_id=r.chunk_id,
            paper_id=r.paper_id,
            section_type=r.section_type,
            section_title=r.section_title,
            text=r.text,
            score=r.score,
            bm25_score=r.bm25_score,
            cosine_score=r.cosine_score,
        )
        for r in reranked
    ]

    # Generate grounded answer with Claude
    api_key = os.environ.get("PAS_ANTHROPIC_API_KEY", "")
    if not api_key:
        answer = (
            "Retrieved the following passages. "
            "Set PAS_ANTHROPIC_API_KEY to enable answer generation.\n\n"
            + "\n\n".join(f"[{i+1}] {s.text[:400]}" for i, s in enumerate(sources))
        )
        model_used = "retrieval-only"
    else:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)

            context_blocks = "\n\n".join(
                f"[{i+1}] (paper={s.paper_id}, section={s.section_type})\n{s.text}"
                for i, s in enumerate(sources)
            )
            system_prompt = (
                "You are a research assistant with deep expertise in self-driving labs, "
                "laboratory automation, and materials acceleration platforms. "
                "Answer questions based strictly on the provided passages. "
                "Cite passages using [N] notation inline. "
                "If the passages are insufficient, say so explicitly rather than speculating."
            )
            user_prompt = (
                f"Question: {payload.query}\n\n"
                f"Retrieved passages:\n{context_blocks}\n\n"
                f"Provide a comprehensive, citation-grounded answer."
            )

            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            answer = response.content[0].text
            model_used = "claude-sonnet-4-6"
        except Exception as exc:
            answer = f"Answer generation failed: {exc}\n\nTop passages:\n" + "\n\n".join(
                f"[{i+1}] {s.text[:400]}" for i, s in enumerate(sources)
            )
            model_used = "error"

    return AnswerOut(
        answer=answer,
        sources=sources,
        model=model_used,
        chunks_retrieved=len(candidates),
    )
