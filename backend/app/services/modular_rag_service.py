"""Modular RAG graph for answer generation.

The current API still returns the same answer shape, but execution is split
into explicit modules:

- Routing: classify intent and choose iterative / recursive / adaptive mode.
- Memory: load recent feedback signals for retry hints.
- Search: run hybrid retrieval over one or more queries.
- Agentic Search: explore propositions, citations, and graph links from
  initial candidates, then retrieve with generated follow-up queries.
- Fusion: deduplicate, rerank, and attach graph/proposition/SQL context.
- Predict: score evidence quality and decide whether another pass is needed.
- Demonstrate: build grounded context and call the answer generator.

LangGraph can run the same node shape when installed; the local runner keeps
tests and deployments working without forcing that dependency at import time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable, Literal, TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PaperChunk
from app.services.embedding_service import get_embedder
from app.services.rag_evaluator import (
    RagAssessment,
    build_feedback_report,
    classify_query,
    evaluate_module_metrics,
    evaluate_retrieval,
)
from app.services.reranker import get_reranker
from app.services.retrieval_service import (
    HybridIndex,
    RetrievedChunk,
    is_structured_query,
    search_propositions,
)
from app.services.nl_to_sql_service import NlSqlUnsupportedError, run_nl_sql

RagMode = Literal["iterative", "recursive", "adaptive"]
AnswerFn = Callable[[str, str], tuple[str | None, str]]


@dataclass
class ModularRagRequest:
    query: str
    top_k: int = 8
    alpha: float = 0.5
    year_from: int | None = None
    year_to: int | None = None
    paper_ids: list[str] | None = None
    mode: RagMode = "adaptive"
    max_chunks: int = 2000
    max_iterations: int = 2
    agentic_search: bool = True


@dataclass
class ModularRagResult:
    answer: str
    model: str
    sources: list[dict[str, Any]]
    proposition_hints: list[Any] = field(default_factory=list)
    sql_hints: list[Any] = field(default_factory=list)
    assessment: RagAssessment | None = None
    chunks_retrieved: int = 0
    mode: RagMode = "adaptive"
    module_trace: list[dict[str, Any]] = field(default_factory=list)


class RagGraphState(TypedDict, total=False):
    request: ModularRagRequest
    mode: RagMode
    query_type: str
    generated_queries: list[str]
    memory: dict[str, Any]
    candidates: list[RetrievedChunk]
    agentic_queries: list[str]
    agentic_links: list[dict[str, Any]]
    reranked: list[RetrievedChunk]
    sources: list[dict[str, Any]]
    proposition_hints: list[Any]
    sql_hints: list[Any]
    assessment: RagAssessment
    context_blocks: str
    answer: str
    model: str
    attempts: int
    should_continue: bool
    trace: list[dict[str, Any]]


def _trace(state: RagGraphState, module: str, **details: Any) -> None:
    state.setdefault("trace", []).append({"module": module, **details})


def _dedupe_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    seen: set[str] = set()
    out: list[RetrievedChunk] = []
    for chunk in chunks:
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        out.append(chunk)
    return out


def _graph_context(session: Session, chunks: list[RetrievedChunk]) -> dict[str, str]:
    from app.models import PaperClassification

    paper_ids = list({r.paper_id for r in chunks})
    if not paper_ids:
        return {}
    out: dict[str, str] = {}
    for cls_row in session.execute(
        select(PaperClassification).where(PaperClassification.paper_id.in_(paper_ids))
    ).scalars():
        gs = cls_row.graph_signals or {}
        lines: list[str] = []
        for path in (gs.get("second_degree_paths") or [])[:2]:
            lines.append(
                f"network: {path.get('via_author_name','')} -> {path.get('ac_author_name','')}"
                f" ({len(path.get('shared_papers', []))} shared papers)"
            )
        for sig in (gs.get("citation_signals") or [])[:2]:
            title = (sig.get("cited_ac_core_title") or "")[:60]
            lines.append(f"cites AC core: {title}")
        if lines:
            out[cls_row.paper_id] = " | ".join(lines)
    return out


def routing_module(state: RagGraphState) -> RagGraphState:
    req = state["request"]
    query_type = classify_query(req.query)
    mode: RagMode = req.mode
    if req.mode == "adaptive":
        if query_type in {"comparison", "gap"}:
            mode = "recursive"
        elif query_type in {"structured", "citation"}:
            mode = "adaptive"
        else:
            mode = "iterative"
    state["query_type"] = query_type
    state["mode"] = mode
    state["generated_queries"] = [req.query]
    state["attempts"] = 0
    _trace(state, "routing", query_type=query_type, mode=mode)
    return state


def memory_module(session: Session, state: RagGraphState) -> RagGraphState:
    try:
        report = build_feedback_report(session, limit=5)
    except Exception:
        report = {"total_feedback": 0, "low_rating_count": 0, "by_failure_type": {}}
    state["memory"] = {
        "low_rating_count": report.get("low_rating_count", 0),
        "failure_types": report.get("by_failure_type", {}),
    }
    _trace(state, "memory", low_rating_count=state["memory"]["low_rating_count"])
    return state


def _recursive_queries(query: str, query_type: str) -> list[str]:
    if query_type == "comparison":
        return [
            query,
            f"methods and platform evidence for {query}",
            f"funding attribution and institutional evidence for {query}",
        ]
    if query_type == "gap":
        return [
            query,
            f"limitations missing evidence future work {query}",
            f"methods results evidence {query}",
        ]
    return [query]


def _adaptive_retry_queries(query: str, state: RagGraphState) -> list[str]:
    failure_types = state.get("memory", {}).get("failure_types", {})
    suffix = " self-driving laboratory Acceleration Consortium funding methods citations"
    if failure_types:
        suffix += " missing evidence"
    return [query, f"{query}{suffix}"]


def _agentic_search_enabled(query_type: str, mode: str, request: ModularRagRequest) -> bool:
    if not request.agentic_search:
        return False
    return mode in {"recursive", "adaptive"} or query_type in {
        "comparison",
        "citation",
        "gap",
        "structured",
    }


def search_module(session: Session, state: RagGraphState) -> RagGraphState:
    req = state["request"]
    chunk_count = session.scalar(select(PaperChunk.id).limit(1))
    if not chunk_count:
        state["candidates"] = []
        _trace(state, "search", skipped="no_chunks")
        return state

    queries = state.get("generated_queries") or [req.query]
    if state["mode"] == "recursive":
        queries = _recursive_queries(req.query, state.get("query_type", "fact"))
        state["generated_queries"] = queries

    embedder = get_embedder()
    index = HybridIndex.from_session(
        session,
        embedder,
        max_chunks=req.max_chunks,
        load_graph_scores=False,
    )
    year_range = None
    if req.year_from is not None or req.year_to is not None:
        year_range = (req.year_from, req.year_to)

    candidates: list[RetrievedChunk] = []
    for q in queries:
        candidates.extend(
            index.search(
                q,
                paper_ids=req.paper_ids,
                year_range=year_range,
                top_k=max(req.top_k * 4, 20),
                alpha=req.alpha,
            )
        )
    state["candidates"] = _dedupe_chunks(candidates)
    state["attempts"] = state.get("attempts", 0) + 1
    _trace(
        state,
        "search",
        queries=len(queries),
        candidates=len(state["candidates"]),
        attempt=state["attempts"],
    )
    return state


def agentic_search_module(session: Session, state: RagGraphState) -> RagGraphState:
    """Controlled multi-hop exploration over corpus relationships.

    This is intentionally not a free-form agent. It explores only known local
    structures: propositions, paper references, and stored graph signals.
    """
    req = state["request"]
    if not _agentic_search_enabled(
        state.get("query_type", "fact"),
        state.get("mode", req.mode),
        req,
    ):
        state["agentic_queries"] = []
        state["agentic_links"] = []
        _trace(state, "agentic_search", skipped="not_needed")
        return state

    seed_paper_ids = list({chunk.paper_id for chunk in state.get("candidates", [])[:8]})
    if not seed_paper_ids:
        state["agentic_queries"] = []
        state["agentic_links"] = []
        _trace(state, "agentic_search", skipped="no_seed_papers")
        return state

    from app.models import PaperClassification, PaperProposition, PaperReference

    generated: list[str] = []
    links: list[dict[str, Any]] = []

    propositions = list(
        session.execute(
            select(PaperProposition).where(PaperProposition.paper_id.in_(seed_paper_ids))
        ).scalars()
    )
    for prop in propositions[:20]:
        generated.append(f"{prop.predicate} {prop.object_value} {prop.claim_text}")
        links.append(
            {
                "type": "proposition",
                "paper_id": prop.paper_id,
                "predicate": prop.predicate,
                "object_value": prop.object_value,
                "source_chunk_id": prop.source_chunk_id,
            }
        )

    refs = list(
        session.execute(
            select(PaperReference).where(
                PaperReference.citing_paper_id.in_(seed_paper_ids)
            )
        ).scalars()
    )
    for ref in refs[:20]:
        if ref.cited_title:
            generated.append(f"cites related work {ref.cited_title}")
        links.append(
            {
                "type": "citation",
                "paper_id": ref.citing_paper_id,
                "cited_paper_id": ref.cited_paper_id,
                "cited_ac_core_id": ref.cited_ac_core_id,
                "cited_title": ref.cited_title,
            }
        )

    classifications = list(
        session.execute(
            select(PaperClassification).where(
                PaperClassification.paper_id.in_(seed_paper_ids)
            )
        ).scalars()
    )
    for cls in classifications:
        signals = cls.graph_signals or {}
        for path in (signals.get("second_degree_paths") or [])[:3]:
            via = path.get("via_author_name")
            ac = path.get("ac_author_name")
            if via or ac:
                generated.append(f"network relation {via or ''} {ac or ''}")
            links.append(
                {
                    "type": "network",
                    "paper_id": cls.paper_id,
                    "via_author_name": via,
                    "ac_author_name": ac,
                }
            )
        for sig in (signals.get("citation_signals") or [])[:3]:
            title = sig.get("cited_ac_core_title")
            if title:
                generated.append(f"cites AC core paper {title}")
            links.append(
                {
                    "type": "graph_citation",
                    "paper_id": cls.paper_id,
                    "cited_ac_core_title": title,
                }
            )

    generated = list(dict.fromkeys(q.strip() for q in generated if q.strip()))[:6]
    if not generated:
        state["agentic_queries"] = []
        state["agentic_links"] = links
        _trace(state, "agentic_search", generated_queries=0, links=len(links))
        return state

    embedder = get_embedder()
    index = HybridIndex.from_session(
        session,
        embedder,
        max_chunks=req.max_chunks,
        load_graph_scores=False,
    )
    year_range = None
    if req.year_from is not None or req.year_to is not None:
        year_range = (req.year_from, req.year_to)

    expanded: list[RetrievedChunk] = []
    for q in generated:
        expanded.extend(
            index.search(
                q,
                paper_ids=req.paper_ids,
                year_range=year_range,
                top_k=max(req.top_k * 2, 10),
                alpha=req.alpha,
            )
        )
    state["candidates"] = _dedupe_chunks(state.get("candidates", []) + expanded)
    state["agentic_queries"] = generated
    state["agentic_links"] = links
    _trace(
        state,
        "agentic_search",
        generated_queries=len(generated),
        links=len(links),
        expanded_candidates=len(expanded),
        candidates=len(state["candidates"]),
    )
    return state


def fusion_module(session: Session, state: RagGraphState) -> RagGraphState:
    req = state["request"]
    candidates = state.get("candidates", [])
    reranked = get_reranker().rerank(req.query, candidates)[: req.top_k]
    graph_ctx = _graph_context(session, reranked)
    sources = [
        {
            "chunk_id": r.chunk_id,
            "paper_id": r.paper_id,
            "section_type": r.section_type,
            "section_title": r.section_title,
            "text": r.text,
            "score": r.score,
            "bm25_score": r.bm25_score,
            "cosine_score": r.cosine_score,
            "graph_score": r.graph_score,
            "graph_context": graph_ctx.get(r.paper_id),
            "agentic_links": [
                link for link in state.get("agentic_links", [])
                if link.get("paper_id") == r.paper_id
            ][:5],
        }
        for r in reranked
    ]
    prop_hints = []
    if is_structured_query(req.query):
        prop_hints = search_propositions(session, req.query, top_k=5)

    sql_hints = []
    try:
        nl_sql_result = run_nl_sql(session, req.query)
    except NlSqlUnsupportedError:
        nl_sql_result = None
    if nl_sql_result is not None and nl_sql_result.rows:
        sql_hints.append(nl_sql_result)

    state["reranked"] = reranked
    state["sources"] = sources
    state["proposition_hints"] = prop_hints
    state["sql_hints"] = sql_hints
    _trace(
        state,
        "fusion",
        sources=len(sources),
        propositions=len(prop_hints),
        sql_hints=len(sql_hints),
        agentic_links=sum(len(src.get("agentic_links", [])) for src in sources),
    )
    return state


def predict_module(state: RagGraphState) -> RagGraphState:
    req = state["request"]
    assessment = evaluate_retrieval(
        req.query,
        [SimpleNamespace(**src) for src in state.get("sources", [])],
        proposition_hints=state.get("proposition_hints", []),
    )
    state["assessment"] = assessment
    should_continue = (
        state["mode"] == "adaptive"
        and assessment.should_retry
        and state.get("attempts", 0) < req.max_iterations
    )
    state["should_continue"] = should_continue
    if should_continue:
        state["generated_queries"] = _adaptive_retry_queries(req.query, state)
    _trace(
        state,
        "predict",
        evidence_score=assessment.evidence_score,
        should_retry=assessment.should_retry,
        continue_graph=should_continue,
    )
    return state


def demonstrate_module(state: RagGraphState, answer_fn: AnswerFn) -> RagGraphState:
    sources = state.get("sources", [])
    sql_hints = state.get("sql_hints", [])
    context_blocks = "\n\n".join(
        f"[{i+1}] (paper={s['paper_id']}, section={s['section_type']}"
        + (f", graph: {s['graph_context']}" if s.get("graph_context") else "")
        + f")\n{s['text']}"
        for i, s in enumerate(sources)
    )
    if sql_hints:
        sql_context = "\n\n".join(
            f"[SQL-{i+1}] intent={hint.plan.intent}, planner={hint.plan.source}\n"
            f"{hint.summary}\nSQL:\n{hint.sql}\nRows:\n{hint.rows[:8]}"
            for i, hint in enumerate(sql_hints)
        )
        context_blocks = f"{sql_context}\n\n{context_blocks}" if context_blocks else sql_context
    answer, model = answer_fn(state["request"].query, context_blocks)
    if answer is None:
        answer = (
            "**Retrieved passages** (set PAS_KIMI_API_KEY or PAS_ANTHROPIC_API_KEY in "
            "Render environment to enable LLM answer generation):\n\n"
            + "\n\n".join(f"**[{i+1}]** {s['text'][:500]}" for i, s in enumerate(sources))
        )
        model = "retrieval-only"
    state["context_blocks"] = context_blocks
    state["answer"] = answer
    state["model"] = model
    _trace(state, "demonstrate", model=model, context_chars=len(context_blocks))
    state["assessment"] = evaluate_retrieval(
        state["request"].query,
        [SimpleNamespace(**src) for src in sources],
        proposition_hints=state.get("proposition_hints", []),
        answer=answer,
        module_trace=state.get("trace", []),
    )
    return state


def run_modular_rag(
    session: Session,
    request: ModularRagRequest,
    *,
    answer_fn: AnswerFn,
) -> ModularRagResult:
    state: RagGraphState = {"request": request, "trace": []}
    routing_module(state)
    memory_module(session, state)
    while True:
        search_module(session, state)
        agentic_search_module(session, state)
        fusion_module(session, state)
        predict_module(state)
        if not state.get("should_continue"):
            break
    demonstrate_module(state, answer_fn)
    if state.get("assessment"):
        state["assessment"].module_metrics = evaluate_module_metrics(
            state.get("trace", []),
            query_type=state["assessment"].query_type,
        )
    return ModularRagResult(
        answer=state["answer"],
        model=state["model"],
        sources=state.get("sources", []),
        proposition_hints=state.get("proposition_hints", []),
        sql_hints=state.get("sql_hints", []),
        assessment=state.get("assessment"),
        chunks_retrieved=len(state.get("candidates", [])),
        mode=state.get("mode", request.mode),
        module_trace=state.get("trace", []),
    )


def build_langgraph_app(
    *,
    routing=routing_module,
    memory=None,
    search=None,
    agentic_search=None,
    fusion=None,
    predict=predict_module,
    demonstrate=None,
):
    """Build a LangGraph skeleton for the same module DAG when installed.

    The production endpoint uses `run_modular_rag` so tests do not need
    LangGraph. This adapter documents the graph shape and gives us a direct
    migration path to LangGraph runtime/checkpointing.
    """
    if not all([memory, search, agentic_search, fusion, demonstrate]):
        raise ValueError(
            "memory, search, agentic_search, fusion, and demonstrate nodes "
            "must be provided with their Session / answer_fn dependencies bound."
        )

    try:
        from langgraph.graph import END, START, StateGraph  # type: ignore
    except ImportError as e:
        raise RuntimeError("Install langgraph to build the modular RAG graph.") from e

    graph = StateGraph(RagGraphState)
    graph.add_node("routing", routing)
    graph.add_node("memory", memory)
    graph.add_node("search", search)
    graph.add_node("agentic_search", agentic_search)
    graph.add_node("fusion", fusion)
    graph.add_node("predict", predict)
    graph.add_node("demonstrate", demonstrate)
    graph.add_edge(START, "routing")
    graph.add_edge("routing", "memory")
    graph.add_edge("memory", "search")
    graph.add_edge("search", "agentic_search")
    graph.add_edge("agentic_search", "fusion")
    graph.add_edge("fusion", "predict")
    graph.add_conditional_edges(
        "predict",
        lambda state: "search" if state.get("should_continue") else END,
        {"search": "search", END: "demonstrate"},
    )
    graph.add_edge("demonstrate", END)
    return graph
