"""Autoresearch-style evaluation loops for classification and RAG.

These functions do not mutate classifier rules or retrieval code. They define
fixed tasks, fixed metrics, and accept/reject gates so every human-reviewed
gold-set update can be evaluated the same way before a change is trusted.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import HumanReview, Paper, PaperChunk, PaperClassification, PaperEvidence
from app.services.eval_service import EvalReport, run_evaluation

AC_RELEVANT = {"CORE_RELEVANT", "RELATED_RELEVANT"}
RAG_EVIDENCE_TYPES = {
    "funding_acknowledgement",
    "sdl_methodology",
    "figure_caption_sdl",
}
RAG_QUERY_BY_EVIDENCE_TYPE = {
    "funding_acknowledgement": (
        "Acceleration Consortium funding acknowledgement grant support CFREF"
    ),
    "sdl_methodology": (
        "self-driving laboratory closed-loop autonomous experimentation "
        "Bayesian optimization methods"
    ),
    "figure_caption_sdl": "self-driving lab autonomous platform figure caption",
}


@dataclass
class Gate:
    name: str
    status: str
    observed: float | int | str | None
    threshold: float | int | str | None
    details: str


@dataclass
class RagTask:
    paper_id: str
    query: str
    evidence_types: list[str]
    expected_chunk_ids: list[str]


def _gate(
    name: str,
    passed: bool,
    observed: float | int | str | None,
    threshold: float | int | str | None,
    details: str,
) -> Gate:
    return Gate(
        name=name,
        status="pass" if passed else "fail",
        observed=observed,
        threshold=threshold,
        details=details,
    )


def _skip_gate(name: str, details: str) -> Gate:
    return Gate(name=name, status="skip", observed=None, threshold=None, details=details)


def _accepted(gates: list[Gate]) -> bool:
    return all(g.status != "fail" for g in gates)


def _eval_summary(report: EvalReport) -> dict:
    return {
        "dataset_role": report.dataset_role,
        "dataset_id": report.dataset_id,
        "dataset_hash": report.dataset_hash,
        "includes_silver": report.includes_silver,
        "n_evaluated": report.n_evaluated,
        "accuracy": report.accuracy,
        "macro_precision": report.macro_precision,
        "macro_recall": report.macro_recall,
        "macro_f1": report.macro_f1,
        "evidence_recall_at_k": report.evidence_recall_at_k,
        "k": report.k,
        "per_label": [asdict(m) for m in report.per_label],
        "confusion": report.confusion,
    }


def _measure_ac_gold(session: Session) -> dict:
    rows = session.execute(
        select(
            Paper.id,
            Paper.title,
            Paper.ac_members_matched,
            PaperClassification.label,
            PaperClassification.confidence,
            PaperClassification.author_score,
            PaperClassification.topic_score,
        )
        .join(PaperClassification, PaperClassification.paper_id == Paper.id)
        .where(Paper.ac_known_publication.is_(True))
    ).all()

    correct = [row for row in rows if row.label in AC_RELEVANT]
    failures = [row for row in rows if row.label not in AC_RELEVANT]
    false_pos = session.execute(
        select(Paper.id, Paper.title, PaperClassification.confidence)
        .join(PaperClassification, PaperClassification.paper_id == Paper.id)
        .where(PaperClassification.label.in_(AC_RELEVANT))
        .where(Paper.ac_known_publication.is_(False))
    ).all()
    total_predicted = len(correct) + len(false_pos)
    return {
        "gold_set_size": len(rows),
        "correct_on_gold": len(correct),
        "failures_on_gold": len(failures),
        "recall": round(len(correct) / len(rows), 3) if rows else None,
        "false_positives": len(false_pos),
        "precision": round(len(correct) / total_predicted, 3) if total_predicted else None,
        "failure_details": [
            {
                "paper_id": row.id,
                "title": row.title,
                "label": row.label,
                "confidence": row.confidence,
                "author_score": row.author_score,
                "topic_score": row.topic_score,
                "ac_members": row.ac_members_matched,
            }
            for row in failures
        ],
        "false_positive_details": [
            {
                "paper_id": row.id,
                "title": row.title,
                "confidence": row.confidence,
            }
            for row in false_pos[:50]
        ],
    }


def run_classification_autoresearch(
    session: Session,
    *,
    eval_labels_path: Path | None = None,
    k: int = 5,
    reclassify: bool = False,
    require_perfect_ac_gold: bool = True,
) -> dict:
    """Run fixed classification gates after a human-review gold-set update."""
    if reclassify:
        from app.services.relevance_classifier import classify_all

        classify_all(session)

    labels_path = eval_labels_path or settings.eval_labels_csv
    eval_report = run_evaluation(session, labels_path, k=k)
    ac_gold = _measure_ac_gold(session)
    human_reviews = session.scalar(select(func.count(HumanReview.id))) or 0

    gates: list[Gate] = [
        _gate(
            "frozen_holdout_dataset",
            eval_report.dataset_role == "frozen_holdout",
            eval_report.dataset_role,
            "frozen_holdout",
            "Release gates require the configured frozen holdout; custom label "
            "paths are diagnostic-only.",
        ),
        _gate(
            "human_gold_labels_present",
            eval_report.n_evaluated > 0,
            eval_report.n_evaluated,
            1,
            "At least one eval_labels.csv row must overlap classified papers.",
        ),
        _gate(
            "human_gold_accuracy_100",
            eval_report.accuracy == 1.0,
            eval_report.accuracy,
            1.0,
            "Manual gold labels are the highest-priority regression set.",
        ),
        _gate(
            "human_gold_macro_f1_100",
            eval_report.macro_f1 == 1.0,
            eval_report.macro_f1,
            1.0,
            "All labels, including EXCLUDE/ADJACENT, must stay exact.",
        ),
    ]
    if ac_gold["gold_set_size"] == 0:
        gates.append(
            _skip_gate(
                "ac_publications_recall_100",
                "No ac_known_publication=True papers are classified in this database.",
            )
        )
        gates.append(
            _skip_gate(
                "ac_publications_precision_100",
                "No AC Publications gold set is available for precision gating.",
            )
        )
    elif require_perfect_ac_gold:
        gates.append(
            _gate(
                "ac_publications_recall_100",
                ac_gold["recall"] == 1.0,
                ac_gold["recall"],
                1.0,
                "Every AC Publications gold paper must be CORE or RELATED.",
            )
        )
        gates.append(
            _gate(
                "ac_publications_precision_100",
                ac_gold["precision"] == 1.0,
                ac_gold["precision"],
                1.0,
                "No non-gold paper may be promoted to CORE/RELATED without review.",
            )
        )

    recommendations: list[str] = []
    if eval_report.dataset_role != "frozen_holdout":
        recommendations.append(
            "Re-run release gating against the configured frozen holdout. Keep "
            "custom or silver datasets diagnostic-only."
        )
    if eval_report.accuracy < 1.0:
        recommendations.append(
            "Inspect confusion rows in human_eval.confusion, then add/adjust rules or "
            "training examples for the mismatched labels."
        )
    if ac_gold["failures_on_gold"]:
        recommendations.append(
            "For AC Publications failures, protect missing member/funding/topic signals "
            "before lowering any threshold."
        )
    if ac_gold["false_positives"]:
        recommendations.append(
            "Route false positives to human review; accepted ones become new gold, "
            "rejected ones should add veto features or negative keywords."
        )

    report = {
        "target": "classification",
        "accepted": _accepted(gates),
        "human_reviews": human_reviews,
        "human_eval": _eval_summary(eval_report),
        "ac_publications_eval": ac_gold,
        "gates": [asdict(g) for g in gates],
        "recommendations": recommendations,
    }
    return report


def _rag_tasks(session: Session, evidence_types: set[str]) -> list[RagTask]:
    rows = session.execute(
        select(
            PaperEvidence.paper_id,
            PaperEvidence.evidence_type,
            PaperEvidence.chunk_id,
        ).where(PaperEvidence.chunk_id.is_not(None))
    ).all()
    grouped: dict[tuple[str, str], set[str]] = {}
    for paper_id, evidence_type, chunk_id in rows:
        if evidence_type not in evidence_types or not chunk_id:
            continue
        grouped.setdefault((paper_id, evidence_type), set()).add(chunk_id)

    tasks = []
    for (paper_id, evidence_type), chunk_ids in sorted(grouped.items()):
        tasks.append(
            RagTask(
                paper_id=paper_id,
                query=RAG_QUERY_BY_EVIDENCE_TYPE.get(
                    evidence_type,
                    "Acceleration Consortium self-driving laboratory evidence",
                ),
                evidence_types=[evidence_type],
                expected_chunk_ids=sorted(chunk_ids),
            )
        )
    return tasks


def _fulltext_coverage(session: Session) -> dict:
    total_papers = session.scalar(select(func.count(Paper.id))) or 0
    fulltext_papers = (
        session.scalar(select(func.count(Paper.id)).where(Paper.full_text_available.is_(True)))
        or 0
    )
    chunks = session.execute(
        select(PaperChunk.section_type, func.count(PaperChunk.id)).group_by(
            PaperChunk.section_type
        )
    ).all()
    by_section = {section_type: count for section_type, count in chunks}
    chunk_count = sum(by_section.values())
    return {
        "papers": total_papers,
        "fulltext_papers": fulltext_papers,
        "fulltext_paper_rate": round(fulltext_papers / total_papers, 3)
        if total_papers
        else 0.0,
        "chunks": chunk_count,
        "chunks_by_section_type": by_section,
        "abstract_chunks": by_section.get("abstract", 0),
        "non_abstract_chunks": chunk_count - by_section.get("abstract", 0),
    }


def run_rag_autoresearch(
    session: Session,
    *,
    top_k: int = 5,
    alpha: float = 0.5,
    section_types: list[str] | None = None,
    min_recall_at_k: float = 1.0,
    evidence_types: set[str] | None = None,
) -> dict:
    """Evaluate whether attribution RAG retrieves known evidence chunks."""
    from app.services.embedding_service import get_embedder
    from app.services.retrieval_service import HybridIndex

    task_rows = _rag_tasks(session, evidence_types or RAG_EVIDENCE_TYPES)
    coverage = _fulltext_coverage(session)
    gates: list[Gate] = [
        _gate(
            "fulltext_chunks_present",
            coverage["non_abstract_chunks"] > 0,
            coverage["non_abstract_chunks"],
            1,
            "RAG must be evaluated on fulltext chunks, not only abstracts.",
        ),
        _gate(
            "evidence_tasks_present",
            len(task_rows) > 0,
            len(task_rows),
            1,
            "At least one evidence-linked chunk is required for RAG evaluation.",
        ),
    ]

    if not task_rows or coverage["chunks"] == 0:
        gates.append(_skip_gate("rag_recall_at_k", "No runnable RAG tasks."))
        return {
            "target": "rag",
            "accepted": False,
            "config": {
                "top_k": top_k,
                "alpha": alpha,
                "section_types": section_types,
                "min_recall_at_k": min_recall_at_k,
            },
            "coverage": coverage,
            "metrics": {
                "tasks": len(task_rows),
                "hits": 0,
                "recall_at_k": None,
                "mrr": None,
                "average_rank": None,
            },
            "task_results": [],
            "gates": [asdict(g) for g in gates],
            "recommendations": [
                "Fetch and ingest fulltexts, then run evidence extraction before RAG evaluation."
            ],
        }

    embedder = get_embedder()
    index = HybridIndex.from_session(session, embedder)
    task_results = []
    hits = 0
    reciprocal_ranks: list[float] = []
    ranks: list[int] = []
    for task in task_rows:
        retrieved = index.search(
            task.query,
            paper_ids=[task.paper_id],
            section_types=section_types,
            top_k=top_k,
            alpha=alpha,
        )
        expected = set(task.expected_chunk_ids)
        rank = next(
            (idx for idx, result in enumerate(retrieved, start=1) if result.chunk_id in expected),
            None,
        )
        if rank is not None:
            hits += 1
            reciprocal_ranks.append(1.0 / rank)
            ranks.append(rank)
        task_results.append(
            {
                **asdict(task),
                "hit": rank is not None,
                "rank": rank,
                "retrieved_chunk_ids": [result.chunk_id for result in retrieved],
            }
        )

    recall = round(hits / len(task_rows), 3)
    mrr = round(mean(reciprocal_ranks), 3) if reciprocal_ranks else 0.0
    avg_rank = round(mean(ranks), 3) if ranks else None
    gates.append(
        _gate(
            "rag_recall_at_k",
            recall >= min_recall_at_k,
            recall,
            min_recall_at_k,
            "Known evidence chunks should appear in the top-k retrieval set.",
        )
    )

    recommendations = []
    if recall < min_recall_at_k:
        recommendations.append(
            "Inspect task_results with hit=false; tune alpha, section filters, "
            "contextual chunk prefixes, or evidence query templates."
        )
    if coverage["abstract_chunks"] and coverage["non_abstract_chunks"] == 0:
        recommendations.append(
            "Current corpus is abstract-only; run the fulltext fetch/ingest pipeline first."
        )

    return {
        "target": "rag",
        "accepted": _accepted(gates),
        "config": {
            "top_k": top_k,
            "alpha": alpha,
            "section_types": section_types,
            "min_recall_at_k": min_recall_at_k,
        },
        "coverage": coverage,
        "metrics": {
            "tasks": len(task_rows),
            "hits": hits,
            "recall_at_k": recall,
            "mrr": mrr,
            "average_rank": avg_rank,
        },
        "task_results": task_results,
        "gates": [asdict(g) for g in gates],
        "recommendations": recommendations,
    }


def write_autoresearch_report(report: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
