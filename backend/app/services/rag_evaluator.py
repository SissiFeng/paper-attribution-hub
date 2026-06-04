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

    def to_dict(self) -> dict:
        return {
            "query_type": self.query_type,
            "evidence_score": self.evidence_score,
            "source_precision": self.source_precision,
            "missing_evidence": self.missing_evidence,
            "should_retry": self.should_retry,
        }


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
    for src in sources:
        score = float(getattr(src, "score", 0.0) or 0.0)
        bm25 = float(getattr(src, "bm25_score", 0.0) or 0.0)
        cosine = float(getattr(src, "cosine_score", 0.0) or 0.0)
        if score > 0 or bm25 > 0 or cosine > 0:
            precision_hits += 1
        if getattr(src, "graph_context", None):
            graph_hits += 1

    source_precision = round(precision_hits / source_count, 3) if source_count else 0.0
    coverage = min(source_count / 5.0, 1.0)
    proposition_bonus = 0.15 if prop_count else 0.0
    graph_bonus = min(graph_hits * 0.05, 0.15)
    evidence_score = round(min(1.0, 0.65 * coverage + 0.2 * source_precision + proposition_bonus + graph_bonus), 3)

    should_retry = evidence_score < 0.55 or bool(missing)
    return RagAssessment(
        query_type=query_type,
        evidence_score=evidence_score,
        source_precision=source_precision,
        missing_evidence=missing,
        should_retry=should_retry,
    )


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
