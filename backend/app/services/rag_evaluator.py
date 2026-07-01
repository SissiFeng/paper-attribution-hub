"""Evidence control for PAS RAG responses."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models import RagFeedback


@dataclass
class RagAssessment:
    query_type: str
    evidence_score: float
    source_precision: float
    missing_evidence: list[str] = field(default_factory=list)
    should_retry: bool = False
    retrieval_quality: dict = field(default_factory=dict)
    answer_grounding: dict = field(default_factory=dict)
    human_feedback: dict = field(default_factory=dict)
    module_metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "query_type": self.query_type,
            "evidence_score": self.evidence_score,
            "source_precision": self.source_precision,
            "missing_evidence": self.missing_evidence,
            "should_retry": self.should_retry,
            "retrieval_quality": self.retrieval_quality,
            "answer_grounding": self.answer_grounding,
            "human_feedback": self.human_feedback,
            "module_metrics": self.module_metrics,
        }


def _source_value(src, field: str, default=None):
    if isinstance(src, dict):
        return src.get(field, default)
    return getattr(src, field, default)


def classify_query(query: str) -> str:
    q = query.lower()
    if any(t in q for t in ("compare", "versus", " vs ", "difference", "对比", "比较")):
        return "comparison"
    if any(t in q for t in ("citation", "cite", "reference", "引用")):
        return "citation"
    if any(t in q for t in ("gap", "missing", "frontier", "future", "空白", "前沿")):
        return "gap"
    if any(t in q for t in ("use", "uses", "method", "platform", "funded", "bayesian", "哪些论文")):
        return "structured"
    return "fact"


def evaluate_retrieval(
    query: str,
    sources: list,
    *,
    proposition_hints: list | None = None,
    answer: str | None = None,
    module_trace: list[dict] | None = None,
    human_feedback: dict | None = None,
) -> RagAssessment:
    query_type = classify_query(query)
    prop_count = len(proposition_hints or [])
    source_count = len(sources)
    missing: list[str] = []

    if source_count == 0:
        missing.append("No source passages were retrieved.")
    if query_type in {"structured", "citation"} and prop_count == 0:
        missing.append("No structured proposition evidence matched the query.")
    if query_type in {"comparison", "gap"} and source_count < 3:
        missing.append("Cross-paper synthesis needs at least three supporting passages.")

    precision_hits = 0
    graph_hits = 0
    paper_ids: set[str] = set()
    section_types: set[str] = set()
    for src in sources:
        score = float(_source_value(src, "score", 0.0) or 0.0)
        bm25 = float(_source_value(src, "bm25_score", 0.0) or 0.0)
        cosine = float(_source_value(src, "cosine_score", 0.0) or 0.0)
        if score > 0 or bm25 > 0 or cosine > 0:
            precision_hits += 1
        if _source_value(src, "graph_context"):
            graph_hits += 1
        paper_id = _source_value(src, "paper_id")
        section_type = _source_value(src, "section_type")
        if paper_id:
            paper_ids.add(paper_id)
        if section_type:
            section_types.add(section_type)

    source_precision = round(precision_hits / source_count, 3) if source_count else 0.0
    coverage = min(source_count / 5.0, 1.0)
    proposition_bonus = 0.15 if prop_count else 0.0
    graph_bonus = min(graph_hits * 0.05, 0.15)
    evidence_score = round(min(1.0, 0.65 * coverage + 0.2 * source_precision + proposition_bonus + graph_bonus), 3)

    retrieval_quality = {
        "layer": "retrieval_quality",
        "recall_proxy": round(coverage, 3),
        "source_precision_proxy": source_precision,
        "source_count": source_count,
        "unique_papers": len(paper_ids),
        "section_diversity": len(section_types),
        "proposition_coverage": prop_count,
        "graph_context_count": graph_hits,
        "score": evidence_score,
        "requires_gold_evidence": "recall@k and nDCG need labeled evidence chunks.",
    }

    answer_grounding = evaluate_answer_grounding(
        answer=answer,
        sources=sources,
        retrieval_quality=retrieval_quality,
    )
    feedback = evaluate_human_feedback(human_feedback)
    module_metrics = evaluate_module_metrics(module_trace or [], query_type=query_type)

    should_retry = evidence_score < 0.55 or bool(missing)
    return RagAssessment(
        query_type=query_type,
        evidence_score=evidence_score,
        source_precision=source_precision,
        missing_evidence=missing,
        should_retry=should_retry,
        retrieval_quality=retrieval_quality,
        answer_grounding=answer_grounding,
        human_feedback=feedback,
        module_metrics=module_metrics,
    )


def evaluate_answer_grounding(
    *,
    answer: str | None,
    sources: list,
    retrieval_quality: dict,
) -> dict:
    """Layer 2: answer grounding.

    This intentionally avoids pretending we can fully grade answer correctness
    without a judge or human label. The automatic part measures citation/source
    support and records what still needs LLM/human assessment.
    """
    if not answer:
        return {
            "layer": "answer_grounding",
            "score": None,
            "citation_coverage": 0.0,
            "supported_by_sources": False,
            "requires_judge": True,
            "notes": ["No generated answer supplied for grounding evaluation."],
        }
    source_count = len(sources)
    citation_hits = sum(1 for idx in range(1, source_count + 1) if f"[{idx}]" in answer)
    citation_coverage = round(citation_hits / source_count, 3) if source_count else 0.0
    supported = bool(source_count) and (
        citation_coverage > 0 or answer.startswith("**Retrieved passages**")
    )
    base = 0.5 * retrieval_quality.get("score", 0.0) + 0.5 * citation_coverage
    return {
        "layer": "answer_grounding",
        "score": round(base, 3),
        "citation_coverage": citation_coverage,
        "supported_by_sources": supported,
        "requires_judge": True,
        "judge_dimensions": [
            "faithfulness_to_sources",
            "answer_completeness",
            "unsupported_claims",
            "contradiction_handling",
        ],
    }


def evaluate_human_feedback(feedback: dict | None = None) -> dict:
    """Layer 3: human feedback. Empty until users or annotators rate answers."""
    if not feedback:
        return {
            "layer": "human_feedback",
            "score": None,
            "rating": None,
            "failure_type": None,
            "requires_human": True,
        }
    rating = feedback.get("rating")
    score = round(float(rating) / 5.0, 3) if rating is not None else None
    return {
        "layer": "human_feedback",
        "score": score,
        "rating": rating,
        "failure_type": feedback.get("failure_type"),
        "note_present": bool(feedback.get("note")),
        "requires_human": False,
    }


def evaluate_module_metrics(
    module_trace: list[dict],
    *,
    query_type: str,
) -> dict:
    """Per-module metrics for Modular RAG.

    These are intentionally operational and cheap: they grade whether each
    module produced the expected state, not whether the final answer is true.
    """
    by_module = {step.get("module"): step for step in module_trace}
    search = by_module.get("search", {})
    fusion = by_module.get("fusion", {})
    predict = by_module.get("predict", {})
    routing = by_module.get("routing", {})
    demonstrate = by_module.get("demonstrate", {})
    agentic = by_module.get("agentic_search", {})

    search_candidates = int(search.get("candidates", 0) or 0)
    fused_sources = int(fusion.get("sources", 0) or 0)
    metrics = {
        "routing": {
            "selected_mode": routing.get("mode"),
            "query_type": routing.get("query_type", query_type),
            "score": 1.0 if routing.get("query_type") == query_type else 0.0,
        },
        "memory": {
            "feedback_loaded": "memory" in by_module,
            "low_rating_count": by_module.get("memory", {}).get("low_rating_count", 0),
        },
        "search": {
            "queries": int(search.get("queries", 0) or 0),
            "candidates": search_candidates,
            "score": min(search_candidates / 20.0, 1.0),
        },
        "agentic_search": {
            "enabled": "agentic_search" in by_module and not agentic.get("skipped"),
            "generated_queries": int(agentic.get("generated_queries", 0) or 0),
            "links": int(agentic.get("links", 0) or 0),
            "expanded_candidates": int(agentic.get("expanded_candidates", 0) or 0),
            "score": min(
                (
                    int(agentic.get("generated_queries", 0) or 0)
                    + int(agentic.get("links", 0) or 0)
                )
                / 10.0,
                1.0,
            ),
        },
        "fusion": {
            "sources": fused_sources,
            "propositions": int(fusion.get("propositions", 0) or 0),
            "sql_hints": int(fusion.get("sql_hints", 0) or 0),
            "agentic_links": int(fusion.get("agentic_links", 0) or 0),
            "dedupe_ratio": round(fused_sources / search_candidates, 3)
            if search_candidates
            else 0.0,
            "score": min(fused_sources / 5.0, 1.0),
        },
        "predict": {
            "evidence_score": predict.get("evidence_score"),
            "should_retry": bool(predict.get("should_retry", False)),
            "continue_graph": bool(predict.get("continue_graph", False)),
        },
        "demonstrate": {
            "model": demonstrate.get("model"),
            "context_chars": int(demonstrate.get("context_chars", 0) or 0),
            "score": 1.0 if int(demonstrate.get("context_chars", 0) or 0) > 0 else 0.0,
        },
    }
    numeric_scores = [
        m["score"] for m in metrics.values() if isinstance(m, dict) and "score" in m
    ]
    return {
        "layer": "module_metrics",
        "score": round(sum(numeric_scores) / len(numeric_scores), 3)
        if numeric_scores
        else 0.0,
        "modules": metrics,
    }


def record_feedback(
    session: Session,
    *,
    query: str,
    rating: int,
    failure_type: str | None = None,
    note: str | None = None,
    answer_model: str | None = None,
    source_chunk_ids: list[str] | None = None,
    source_paper_ids: list[str] | None = None,
) -> RagFeedback:
    row = RagFeedback(
        id=f"rfb_{uuid.uuid4().hex[:12]}",
        query=query,
        rating=rating,
        failure_type=failure_type,
        note=note,
        answer_model=answer_model,
        source_chunk_ids=source_chunk_ids or [],
        source_paper_ids=source_paper_ids or [],
        created_at=datetime.now(UTC),
    )
    session.add(row)
    session.commit()
    return row


def build_feedback_report(session: Session, *, limit: int = 20) -> dict:
    total = session.scalar(select(func.count(RagFeedback.id))) or 0
    avg = session.scalar(select(func.avg(RagFeedback.rating)))
    low = session.scalar(select(func.count(RagFeedback.id)).where(RagFeedback.rating <= 2)) or 0
    by_failure = {
        key or "none": count
        for key, count in session.execute(
            select(RagFeedback.failure_type, func.count())
            .group_by(RagFeedback.failure_type)
        ).all()
    }
    recent = list(
        session.execute(
            select(RagFeedback).order_by(desc(RagFeedback.created_at)).limit(limit)
        ).scalars()
    )
    return {
        "total_feedback": total,
        "average_rating": round(float(avg), 3) if avg is not None else None,
        "low_rating_count": low,
        "by_failure_type": by_failure,
        "recent": recent,
    }
