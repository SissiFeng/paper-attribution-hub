from __future__ import annotations

import re
import shutil
import tempfile
from typing import Any, Literal
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Paper, PaperChunk
from app.schemas import ChunkOut, PropositionHit, RagFeedbackIn, RagFeedbackOut, RetrieveRequest
from app.services.embedding_service import get_embedder
from app.services.fulltext_service import build_chunk_embeddings, ingest_fulltext_file
from app.services.grounded_answer_service import (
    contextualized_retrieval_query,
    generate_grounded_answer,
)
from app.services.pdf_parser import SUPPORTED_FULLTEXT_SUFFIXES
from app.services.relevance_classifier import classify_all
from app.services.reranker import get_reranker
from app.services.rag_evaluator import record_feedback
from app.services.retrieval_service import HybridIndex, search_propositions
from app.services.filter_spec import PaperFilter
from app.services.nl_to_sql_service import (
    NlSqlUnsupportedError,
    plan_nl_sql,
    run_nl_sql,
)
from app.services.modular_rag_service import ModularRagRequest, run_modular_rag

router = APIRouter(tags=["fulltext"])


class ConversationTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("conversation content must not be blank")
        return normalized


class AnswerRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    search_query: str | None = Field(default=None, min_length=1, max_length=2000)
    top_k: int = Field(default=8, ge=1, le=20)
    alpha: float = Field(default=0.5, ge=0.0, le=1.0)
    year_from: int | None = None
    year_to: int | None = None
    paper_ids: list[str] | None = None
    mode: Literal["iterative", "recursive", "adaptive"] = "adaptive"
    agentic_search: bool = True
    conversation: list[ConversationTurn] = Field(default_factory=list, max_length=12)
    page_context: str | None = Field(default=None, max_length=1000)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query must not be blank")
        return normalized


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
    agentic_links: list[dict[str, Any]] = Field(default_factory=list)


class NlSqlOut(BaseModel):
    intent: str
    planner: str
    sql: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    rows: list[dict[str, Any]]
    summary: str
    audit: dict[str, Any] = Field(default_factory=dict)


class SqlChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    filters: PaperFilter = Field(default_factory=PaperFilter)
    paper_ids: list[str] | None = Field(default=None, max_length=100)
    conversation: list[ConversationTurn] = Field(default_factory=list, max_length=12)
    page_context: str | None = Field(default=None, max_length=1000)

    @field_validator("query")
    @classmethod
    def normalize_sql_chat_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query must not be blank")
        return normalized

    @field_validator("paper_ids")
    @classmethod
    def validate_paper_ids(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        normalized = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if any(len(value) > 200 for value in normalized):
            raise ValueError("paper IDs must be at most 200 characters")
        return normalized


class SqlChatOut(BaseModel):
    answer: str
    model: Literal["deterministic-text-to-sql"]
    intent: str
    planner: str
    resolved_query: str
    sql: str
    parameters: dict[str, Any]
    rows: list[dict[str, Any]]
    audit: dict[str, Any]
    conversation_turns_used: int = 0
    page_context: str | None = None


class AnswerOut(BaseModel):
    answer: str
    sources: list[SourceOut]
    model: str
    chunks_retrieved: int
    proposition_hints: list[PropositionHit] = Field(default_factory=list)
    sql_hints: list[NlSqlOut] = Field(default_factory=list)
    query_type: str = "fact"
    evidence_score: float = 0.0
    source_precision: float = 0.0
    missing_evidence: list[str] = Field(default_factory=list)
    should_retry: bool = False
    execution_mode: str = "adaptive"
    module_trace: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_quality: dict[str, Any] = Field(default_factory=dict)
    answer_grounding: dict[str, Any] = Field(default_factory=dict)
    human_feedback: dict[str, Any] = Field(default_factory=dict)
    module_metrics: dict[str, Any] = Field(default_factory=dict)
    retrieval_query: str
    conversation_turns_used: int = 0
    page_context: str | None = None


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
    if suffix not in SUPPORTED_FULLTEXT_SUFFIXES:
        accepted = " / ".join(sorted(SUPPORTED_FULLTEXT_SUFFIXES))
        raise HTTPException(status_code=415, detail=f"Only {accepted} accepted")

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


@router.get("/retrieval/nl-sql", response_model=NlSqlOut)
def nl_sql_search(
    q: str = Query(min_length=1, max_length=2000),
    session: Session = Depends(get_session),
) -> NlSqlOut:
    """Run deterministic schema-constrained text-to-SQL."""
    try:
        result = run_nl_sql(session, q)
    except NlSqlUnsupportedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return NlSqlOut(
        intent=result.plan.intent,
        planner=result.plan.source,
        sql=result.sql,
        parameters=result.parameters,
        rows=result.rows,
        summary=result.summary,
        audit=result.audit,
    )


def _resolve_sql_chat_query(
    query: str,
    conversation: list[ConversationTurn],
) -> tuple[str, int]:
    try:
        plan_nl_sql(query)
        return query, 0
    except NlSqlUnsupportedError as original_error:
        for turn in reversed(conversation):
            if turn.role != "user":
                continue
            candidate = f"{turn.content.rstrip()} Follow-up: {query}"
            try:
                plan_nl_sql(candidate)
                return candidate, 1
            except NlSqlUnsupportedError:
                continue
        raise original_error


@router.post("/retrieve/sql-chat", response_model=SqlChatOut)
def retrieve_sql_chat(
    payload: SqlChatRequest,
    session: Session = Depends(get_session),
) -> SqlChatOut:
    """Answer only through deterministic, parameter-bound, read-only SQL."""
    try:
        resolved_query, context_turns_used = _resolve_sql_chat_query(
            payload.query,
            payload.conversation,
        )
        result = run_nl_sql(
            session,
            resolved_query,
            base_filter=payload.filters,
            paper_ids=payload.paper_ids,
        )
    except NlSqlUnsupportedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SqlChatOut(
        answer=result.summary,
        model="deterministic-text-to-sql",
        intent=result.plan.intent,
        planner=result.plan.source,
        resolved_query=resolved_query,
        sql=result.sql,
        parameters=result.parameters,
        rows=result.rows,
        audit=result.audit,
        conversation_turns_used=context_turns_used,
        page_context=payload.page_context,
    )


def _conversation_context(turns: list[ConversationTurn]) -> str:
    """Bounded dialogue context for follow-ups without server-side chat state."""
    from app.services.grounded_answer_service import conversation_context

    return conversation_context(turns)


def _contextualized_retrieval_query(
    query: str,
    turns: list[ConversationTurn],
) -> str:
    return contextualized_retrieval_query(query, turns)


def _llm_answer(
    query: str,
    context_blocks: str,
    *,
    conversation: list[ConversationTurn] | None = None,
    page_context: str | None = None,
) -> tuple[str | None, str]:
    """Generate a grounded answer via Kimi or Claude.  Returns (answer, model_name)."""
    return generate_grounded_answer(
        query,
        context_blocks,
        conversation=conversation or [],
        page_context=page_context,
    )


@router.post("/retrieve/answer", response_model=AnswerOut)
def retrieve_answer(
    payload: AnswerRequest,
    session: Session = Depends(get_session),
) -> AnswerOut:
    """Modular RAG endpoint with controlled agentic search.

    Supports Kimi (PAS_KIMI_API_KEY) and Claude (PAS_ANTHROPIC_API_KEY).
    Set PAS_LLM_PROVIDER=kimi|anthropic|auto (default: auto).

    OOM fix: limits chunk loading to MAX_CHUNKS most-recently-embedded chunks
    to bound the memory used by the TF-IDF fit.
    """
    MAX_CHUNKS = 2000  # bounds index memory; covers ~1000 papers × 2 chunks

    retrieval_query = payload.search_query or _contextualized_retrieval_query(
        payload.query, payload.conversation
    )
    chunk_count = session.scalar(select(func.count()).select_from(PaperChunk))
    if not chunk_count:
        return AnswerOut(
            answer="知识库还没有索引任何论文片段。请先触发 POST /admin/seed-chunks。",
            sources=[],
            model="none",
            chunks_retrieved=0,
            sql_hints=[],
            query_type="fact",
            missing_evidence=["No paper chunks are indexed yet."],
            should_retry=False,
            execution_mode=payload.mode,
            module_trace=[{"module": "search", "skipped": "no_chunks"}],
            retrieval_query=retrieval_query,
            conversation_turns_used=len(payload.conversation),
            page_context=payload.page_context,
        )

    result = run_modular_rag(
        session,
        ModularRagRequest(
            query=retrieval_query,
            top_k=payload.top_k,
            alpha=payload.alpha,
            year_from=payload.year_from,
            year_to=payload.year_to,
            paper_ids=payload.paper_ids,
            mode=payload.mode,
            max_chunks=MAX_CHUNKS,
            agentic_search=payload.agentic_search,
        ),
        answer_fn=lambda _query, context: _llm_answer(
            payload.query,
            context,
            conversation=payload.conversation,
            page_context=payload.page_context,
        ),
    )

    sources = [SourceOut(**src) for src in result.sources]
    prop_hints = [PropositionHit(**h.__dict__) for h in result.proposition_hints]
    sql_hints = [
        NlSqlOut(
            intent=hint.plan.intent,
            planner=hint.plan.source,
            sql=hint.sql,
            parameters=hint.parameters,
            rows=hint.rows,
            summary=hint.summary,
            audit=hint.audit,
        )
        for hint in result.sql_hints
    ]
    assessment = result.assessment

    return AnswerOut(
        answer=result.answer,
        sources=sources,
        model=result.model,
        chunks_retrieved=result.chunks_retrieved,
        proposition_hints=prop_hints,
        sql_hints=sql_hints,
        query_type=assessment.query_type if assessment else "fact",
        evidence_score=assessment.evidence_score if assessment else 0.0,
        source_precision=assessment.source_precision if assessment else 0.0,
        missing_evidence=assessment.missing_evidence if assessment else [],
        should_retry=assessment.should_retry if assessment else False,
        execution_mode=result.mode,
        module_trace=result.module_trace,
        retrieval_quality=assessment.retrieval_quality if assessment else {},
        answer_grounding=assessment.answer_grounding if assessment else {},
        human_feedback=assessment.human_feedback if assessment else {},
        module_metrics=assessment.module_metrics if assessment else {},
        retrieval_query=retrieval_query,
        conversation_turns_used=len(payload.conversation),
        page_context=payload.page_context,
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
