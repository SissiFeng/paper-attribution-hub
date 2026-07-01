"""Quantitative evaluation against a hand-labeled gold standard.

Loads `data/eval_labels.csv`, compares against the latest classifier labels,
and reports per-label precision / recall / F1, a confusion matrix, and a
top-k evidence-recall figure for CORE/RELATED papers (does the top-k retrieval
hit at least one of the chunks the evidence extractor flagged as funding /
methodology?).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Paper, PaperEvidence


@dataclass
class LabelMetric:
    label: str
    precision: float
    recall: float
    f1: float
    support: int


@dataclass
class EvalReport:
    per_label: list[LabelMetric] = field(default_factory=list)
    macro_precision: float = 0.0
    macro_recall: float = 0.0
    macro_f1: float = 0.0
    accuracy: float = 0.0
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)
    evidence_recall_at_k: float | None = None
    k: int = 5
    n_evaluated: int = 0


def load_gold_labels(path: Path, silver_path: Path | None = None) -> dict[str, str]:
    """Load gold labels; optionally merge silver labels (hand labels win)."""
    df = pd.read_csv(path)
    gold = {str(row["paper_id"]).strip(): str(row["gold_label"]).strip() for _, row in df.iterrows()}
    if silver_path is not None:
        silver = pd.read_csv(silver_path)
        for _, row in silver.iterrows():
            gold.setdefault(str(row["paper_id"]).strip(), str(row["gold_label"]).strip())
    return gold


def _precision_recall_f1(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return round(p, 3), round(r, 3), round(f1, 3)


def compute_metrics(
    pred_by_paper: dict[str, str], gold_by_paper: dict[str, str]
) -> EvalReport:
    paper_ids = sorted(set(pred_by_paper) & set(gold_by_paper))
    labels = sorted({*pred_by_paper.values(), *gold_by_paper.values()})

    confusion = {gold: {pred: 0 for pred in labels} for gold in labels}
    correct = 0
    for pid in paper_ids:
        g = gold_by_paper[pid]
        p = pred_by_paper[pid]
        confusion[g][p] = confusion[g].get(p, 0) + 1
        if g == p:
            correct += 1

    per_label: list[LabelMetric] = []
    macro_p = macro_r = macro_f1 = 0.0
    for label in labels:
        tp = confusion.get(label, {}).get(label, 0)
        fp = sum(confusion[g][label] for g in labels if g != label)
        fn = sum(confusion[label].get(p, 0) for p in labels if p != label)
        p, r, f1 = _precision_recall_f1(tp, fp, fn)
        support = sum(confusion[label].values()) if label in confusion else 0
        per_label.append(
            LabelMetric(label=label, precision=p, recall=r, f1=f1, support=support)
        )
        macro_p += p
        macro_r += r
        macro_f1 += f1

    denom = len(labels) or 1
    n = len(paper_ids) or 1
    return EvalReport(
        per_label=per_label,
        macro_precision=round(macro_p / denom, 3),
        macro_recall=round(macro_r / denom, 3),
        macro_f1=round(macro_f1 / denom, 3),
        accuracy=round(correct / n, 3),
        confusion=confusion,
        n_evaluated=len(paper_ids),
    )


def evidence_recall_at_k(
    session: Session,
    gold: dict[str, str],
    *,
    queries: dict[str, str] | None = None,
    k: int = 5,
) -> float | None:
    """For papers labeled CORE_RELEVANT or RELATED_RELEVANT in the gold set,
    check whether top-k retrieval surfaces a chunk that the evidence extractor
    flagged as `funding_acknowledgement` or `sdl_methodology`."""
    from app.services.embedding_service import get_embedder
    from app.services.retrieval_service import HybridIndex

    target_papers = [
        pid for pid, label in gold.items() if label in {"CORE_RELEVANT", "RELATED_RELEVANT"}
    ]
    if not target_papers:
        return None

    # Build a chunk-level retrieval index covering all corpora.
    embedder = get_embedder()
    # Re-fit on the entire chunk corpus so this report is independent of
    # whatever build_chunk_embeddings produced.
    from app.models import PaperChunk

    chunks = list(session.execute(select(PaperChunk)).scalars())
    if not chunks:
        return None
    embedder.fit([c.chunk_text for c in chunks])
    matrix = embedder.encode([c.chunk_text for c in chunks])
    for chunk, vec in zip(chunks, matrix):
        chunk.embedding = vec.tolist()
        chunk.embedding_backend = embedder.backend
    session.flush()
    index = HybridIndex.from_session(session, embedder)

    default_query = (
        "Acceleration Consortium funding acknowledgement self-driving lab "
        "closed-loop Bayesian optimization"
    )
    hits = 0
    evaluated = 0
    for paper_id in target_papers:
        evidence_chunks = {
            ev.chunk_id
            for ev in session.execute(
                select(PaperEvidence).where(PaperEvidence.paper_id == paper_id)
            ).scalars()
            if ev.evidence_type in {"funding_acknowledgement", "sdl_methodology"}
            and ev.chunk_id
        }
        if not evidence_chunks:
            continue
        query = (queries or {}).get(paper_id, default_query)
        retrieved = index.search(query, paper_ids=[paper_id], top_k=k)
        if any(r.chunk_id in evidence_chunks for r in retrieved):
            hits += 1
        evaluated += 1
    if evaluated == 0:
        return None
    return round(hits / evaluated, 3)


def run_evaluation(
    session: Session,
    eval_labels_path: Path,
    k: int = 5,
    silver_labels_path: Path | None = None,
) -> EvalReport:
    gold = load_gold_labels(eval_labels_path, silver_path=silver_labels_path)
    papers = list(session.execute(select(Paper)).scalars())
    pred = {p.id: p.classification.label for p in papers if p.classification}
    report = compute_metrics(pred, gold)
    report.k = k
    report.evidence_recall_at_k = evidence_recall_at_k(session, gold, k=k)
    return report


def print_report(report: EvalReport) -> None:
    print(f"Evaluated {report.n_evaluated} papers")
    print(
        f"Accuracy: {report.accuracy:.3f} | macro P/R/F1: "
        f"{report.macro_precision:.3f}/{report.macro_recall:.3f}/{report.macro_f1:.3f}"
    )
    if report.evidence_recall_at_k is not None:
        print(f"Evidence recall@{report.k}: {report.evidence_recall_at_k:.3f}")
    print(f"{'Label':<20} {'P':>6} {'R':>6} {'F1':>6} {'support':>8}")
    for m in report.per_label:
        print(
            f"{m.label:<20} {m.precision:>6.3f} {m.recall:>6.3f} "
            f"{m.f1:>6.3f} {m.support:>8d}"
        )
    print("\nConfusion (rows=gold, cols=pred):")
    labels = list(report.confusion.keys())
    print(" " * 22 + " ".join(f"{l[:14]:>14}" for l in labels))
    for gold_label in labels:
        row = report.confusion[gold_label]
        print(
            f"{gold_label[:20]:<20}  "
            + " ".join(f"{row.get(l, 0):>14d}" for l in labels)
        )
