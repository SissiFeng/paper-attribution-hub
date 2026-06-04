from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Paper, PaperChunk
from app.schemas import ChunkOut, PropositionHit, RagFeedbackIn, RagFeedbackOut, RetrieveRequest
from app.services.embedding_service import get_embedder
from app.services.fulltext_service import build_chunk_embeddings, ingest_fulltext_file
from app.services.relevance_classifier import classify_all
from app.services.reranker import get_reranker
from app.services.rag_evaluator import evaluate_retrieval, record_feedback
from app.services.retrieval_service import HybridIndex, is_structured_query, search_propositions

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
    graph_score: float = 0.0
    graph_context: str | None = None   # Point 3: structured network paths


class AnswerOut(BaseModel):
    answer: str
    sources: list[SourceOut]
    model: str
    chunks_retrieved: int
    proposition_hints: list[PropositionHit] = []  # Point 2: structured hits
    query_type: str = "fact"
    evidence_score: float = 0.0
    source_precision: float = 0.0
    missing_evidence: list[str] = []
    should_retry: bool = False


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
            graph_score=r.graph_score,
        )
        for r in retrieved
    ]


# Point 2: Proposition-first endpoint
@router.get("/retrieval/propositions", response_model=list[PropositionHit])
def proposition_search(
    q: str,
    top_k: int = 10,
    predicate: list[str] | None = None,
    session: Session = Depends(get_session),
) -> list[PropositionHit]:
    """Search structured propositions (method/funding/mechanism claims).

    More precise than chunk search for queries like:
      'which papers use Bayesian optimization?'
      'papers funded by NSERC'
    """
    hits = search_propositions(session, q, top_k=top_k, predicates=predicate)
    return [PropositionHit(**h.__dict__) for h in hits]


def _llm_answer(query: str, context_blocks: str) -> tuple[str, str]:
    """Generate a grounded answer via Kimi or Claude.  Returns (answer, model_name)."""
    from app.config import settings

    system_prompt = (
        "You are a research assistant specialised in self-driving laboratories, "
        "laboratory automation, and materials-acceleration platforms. "
        "Answer strictly from the provided passages, citing them as [N]. "
        "If the passages are insufficient, state that explicitly."
    )
    user_prompt = (
        f"Question: {query}\n\n"
        f"Retrieved passages:\n{context_blocks}\n\n"
        "Provide a comprehensive, citation-grounded answer."
    )

    # Determine which LLM to call
    provider = settings.llm_provider
    if provider == "auto":
        provider = "kimi" if settings.kimi_api_key else ("anthropic" if settings.anthropic_api_key else "none")

    if provider == "kimi" and settings.kimi_api_key:
        try:
            import openai
            client = openai.OpenAI(
                api_key=settings.kimi_api_key,
                base_url=settings.kimi_base_url,
            )
            resp = client.chat.completions.create(
                model=settings.kimi_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                max_tokens=1024,
                temperature=0.3,
            )
            return resp.choices[0].message.content, f"kimi/{settings.kimi_model}"
        except Exception as exc:
            return f"Kimi answer generation failed: {exc}", "error"

    if provider == "anthropic" and settings.anthropic_api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return resp.content[0].text, "claude-sonnet-4-6"
        except Exception as exc:
            return f"Anthropic answer generation failed: {exc}", "error"

    # No LLM configured — return passages only
    return None, "retrieval-only"


@router.post("/retrieve/answer", response_model=AnswerOut)
def retrieve_answer(
    payload: AnswerRequest,
    session: Session = Depends(get_session),
) -> AnswerOut:
    """Advanced RAG endpoint: hybrid retrieval → LLM answer generation.

    Supports Kimi (PAS_KIMI_API_KEY) and Claude (PAS_ANTHROPIC_API_KEY).
    Set PAS_LLM_PROVIDER=kimi|anthropic|auto (default: auto).

    OOM fix: limits chunk loading to MAX_CHUNKS most-recently-embedded chunks
    so the TF-IDF fit stays within Render's 512 MB limit.
    """
    MAX_CHUNKS = 2000  # safe for Render 512 MB; covers ~1000 papers × 2 chunks

    # Check if any chunks exist at all
    chunk_count = session.scalar(select(func.count()).select_from(PaperChunk))
    if not chunk_count:
        return AnswerOut(
            answer="知识库还没有索引任何论文片段。请先触发 POST /admin/seed-chunks。",
            sources=[],
            model="none",
            chunks_retrieved=0,
            query_type="fact",
            missing_evidence=["No paper chunks are indexed yet."],
            should_retry=False,
        )

    embedder = get_embedder()
    # load_graph_scores=False skips loading all PaperClassification rows (saves ~100 MB)
    index = HybridIndex.from_session(session, embedder,
                                      max_chunks=MAX_CHUNKS,
                                      load_graph_scores=False)
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

    # Point 3: load graph context (second-degree paths + AC citations) for top papers.
    from app.models import PaperClassification
    unique_paper_ids = list({r.paper_id for r in reranked})
    graph_ctx: dict[str, str] = {}
    for cls_row in session.execute(
        select(PaperClassification).where(PaperClassification.paper_id.in_(unique_paper_ids))
    ).scalars():
        gs = cls_row.graph_signals or {}
        lines: list[str] = []
        for path in (gs.get("second_degree_paths") or [])[:2]:
            lines.append(
                f"network: {path.get('via_author_name','')} → {path.get('ac_author_name','')}"
                f" ({len(path.get('shared_papers', []))} shared papers)"
            )
        for sig in (gs.get("citation_signals") or [])[:2]:
            title = (sig.get("cited_ac_core_title") or "")[:60]
            lines.append(f"cites AC core: {title}")
        if lines:
            graph_ctx[cls_row.paper_id] = " | ".join(lines)

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
            graph_score=r.graph_score,
            graph_context=graph_ctx.get(r.paper_id),
        )
        for r in reranked
    ]

    # Point 2: append proposition hints for structured queries.
    prop_hints: list[PropositionHit] = []
    if is_structured_query(payload.query):
        raw_hits = search_propositions(session, payload.query, top_k=5)
        prop_hints = [PropositionHit(**h.__dict__) for h in raw_hits]

    assessment = evaluate_retrieval(
        payload.query,
        sources,
        proposition_hints=prop_hints,
    )

    # Build context and generate answer
    context_blocks = "\n\n".join(
        f"[{i+1}] (paper={s.paper_id}, section={s.section_type}"
        + (f", graph: {s.graph_context}" if s.graph_context else "")
        + f")\n{s.text}"
        for i, s in enumerate(sources)
    )

    answer, model_used = _llm_answer(payload.query, context_blocks)

    if answer is None:
        # No LLM configured — show passages with hint
        from app.config import settings
        answer = (
            "**Retrieved passages** (set PAS_KIMI_API_KEY or PAS_ANTHROPIC_API_KEY in "
            "Render environment to enable LLM answer generation):\n\n"
            + "\n\n".join(f"**[{i+1}]** {s.text[:500]}" for i, s in enumerate(sources))
        )
        model_used = "retrieval-only"

    return AnswerOut(
        answer=answer,
        sources=sources,
        model=model_used,
        chunks_retrieved=len(candidates),
        proposition_hints=prop_hints,
        query_type=assessment.query_type,
        evidence_score=assessment.evidence_score,
        source_precision=assessment.source_precision,
        missing_evidence=assessment.missing_evidence,
        should_retry=assessment.should_retry,
    )


@router.post("/retrieve/feedback", response_model=RagFeedbackOut)
def submit_rag_feedback(
    payload: RagFeedbackIn,
    session: Session = Depends(get_session),
) -> RagFeedbackOut:
    row = record_feedback(
        session,
        query=payload.query,
        rating=payload.rating,
        failure_type=payload.failure_type,
        note=payload.note,
        answer_model=payload.answer_model,
        source_chunk_ids=payload.source_chunk_ids,
        source_paper_ids=payload.source_paper_ids,
    )
    return RagFeedbackOut(
        id=row.id,
        query=row.query,
        rating=row.rating,
        failure_type=row.failure_type,
        note=row.note,
        answer_model=row.answer_model,
        source_chunk_ids=row.source_chunk_ids or [],
        source_paper_ids=row.source_paper_ids or [],
        created_at=row.created_at,
    )
