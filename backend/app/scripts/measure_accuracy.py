"""Measure classifier accuracy against the AC Publications gold set.

Usage:
    python -m app.scripts.measure_accuracy [--reclassify]

Prints a precision/recall report against the 463 ac_known_publication papers.
Pass --reclassify to re-run classify_all() before measuring (slow, ~5 min).
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Paper, PaperClassification

AC_RELEVANT = {"CORE_RELEVANT", "RELATED_RELEVANT"}


def measure(session) -> dict:
    rows = session.execute(
        select(
            Paper.id, Paper.title, Paper.ac_members_matched,
            PaperClassification.label, PaperClassification.confidence,
            PaperClassification.author_score, PaperClassification.topic_score,
        )
        .join(PaperClassification, PaperClassification.paper_id == Paper.id)
        .where(Paper.ac_known_publication == True)
    ).all()

    dist = Counter(r.label for r in rows)
    correct = [r for r in rows if r.label in AC_RELEVANT]
    failures = [r for r in rows if r.label not in AC_RELEVANT]
    recall = len(correct) / len(rows) if rows else 0.0

    # Precision: CORE/RELATED papers NOT in gold set
    false_pos = session.execute(
        select(Paper.id, Paper.title, PaperClassification.confidence)
        .join(PaperClassification, PaperClassification.paper_id == Paper.id)
        .where(PaperClassification.label.in_(AC_RELEVANT))
        .where(Paper.ac_known_publication == False)
    ).all()

    total_predicted = len(correct) + len(false_pos)
    precision = len(correct) / total_predicted if total_predicted else 0.0

    return {
        "gold_set_size": len(rows),
        "label_distribution": dict(dist),
        "correct_on_gold": len(correct),
        "failures_on_gold": len(failures),
        "recall": recall,
        "false_positives": len(false_pos),
        "precision": precision,
        "failure_details": [
            {
                "paper_id": r.id,
                "title": r.title[:70],
                "label": r.label,
                "confidence": r.confidence,
                "author_score": r.author_score,
                "topic_score": r.topic_score,
                "ac_members": r.ac_members_matched,
            }
            for r in failures
        ],
        "false_positive_details": [
            {"paper_id": r.id, "title": r.title[:70], "confidence": r.confidence}
            for r in false_pos[:10]
        ],
    }


def print_report(result: dict) -> None:
    print("=" * 65)
    print("AC CLASSIFICATION ACCURACY REPORT")
    print("=" * 65)
    print(f"Gold set (ac_known_publication=True): {result['gold_set_size']} papers")
    print(f"\nLabel distribution on gold set:")
    for label, count in sorted(result["label_distribution"].items(), key=lambda x: -x[1]):
        bar = "█" * (count // 5)
        print(f"  {label:<25} {count:4d}  {bar}")

    print(f"\n── Recall ──────────────────────────────────────────")
    print(f"  Correct (>= RELATED): {result['correct_on_gold']}/{result['gold_set_size']}")
    print(f"  Recall:  {result['recall']:.1%}")

    if result["failure_details"]:
        print(f"\n  ⚠  Failures ({len(result['failure_details'])} papers below RELATED):")
        for f in result["failure_details"]:
            print(f"    [{f['label']} {f['confidence']:.0%}] {f['title']}")
            print(f"      author={f['author_score']:.2f} topic={f['topic_score']:.2f}"
                  f"  ac_members={f['ac_members']}")
    else:
        print(f"\n  ✓  No failures — all gold-set papers >= RELATED_RELEVANT")

    print(f"\n── Precision ───────────────────────────────────────")
    print(f"  False positives (CORE/RELATED not in gold set): {result['false_positives']}")
    print(f"  Precision: {result['precision']:.1%}")
    if result["false_positive_details"]:
        print("  (first 10):")
        for fp in result["false_positive_details"]:
            print(f"    [{fp['confidence']:.0%}] {fp['title']}")

    print(f"\n── Summary ─────────────────────────────────────────")
    print(f"  Precision: {result['precision']:.1%}   Recall: {result['recall']:.1%}")
    f1 = (2 * result["precision"] * result["recall"] /
          (result["precision"] + result["recall"])
          if (result["precision"] + result["recall"]) > 0 else 0.0)
    print(f"  F1 score:  {f1:.1%}")
    print("=" * 65)


def run(reclassify: bool = False) -> None:
    with SessionLocal() as session:
        if reclassify:
            print("Re-running classify_all()... (this takes ~5 minutes)")
            from app.services.relevance_classifier import classify_all
            classify_all(session)
            print("Done.")

        result = measure(session)
        print_report(result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reclassify", action="store_true",
                        help="Re-run classify_all() before measuring")
    args = parser.parse_args()
    run(reclassify=args.reclassify)
    sys.exit(0)
