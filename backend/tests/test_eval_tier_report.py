"""Per-availability-tier evaluation: the natural-missingness benchmark report.

Reporting one global accuracy hides that the classifier is confident-and-right
on FULLTEXT papers and guessing on METADATA_ONLY ones. Metrics must be grouped
by availability tier, with auto-label precision as a CI lower bound.
"""

from __future__ import annotations

import pytest

from app.services.eval_harness.tier_report import EvalItem, evaluate_by_tier


def _item(tier, gold, pred, conf, auto):
    return EvalItem(
        paper_id=f"p{id((tier, gold, pred, conf, auto))}",
        tier=tier,
        gold_label=gold,
        predicted_label=pred,
        confidence=conf,
        auto_decided=auto,
    )


def test_splits_metrics_by_tier_and_overall():
    items = [
        _item("FULLTEXT", "SDL", "SDL", 0.95, True),
        _item("FULLTEXT", "SDL", "SDL", 0.92, True),
        _item("METADATA_ONLY", "SDL", "NOT_SDL", 0.55, False),
    ]
    report = evaluate_by_tier(items)

    assert set(report) == {"FULLTEXT", "METADATA_ONLY", "__overall__"}
    assert report["FULLTEXT"].n == 2
    assert report["FULLTEXT"].coverage == 1.0
    assert report["FULLTEXT"].accuracy == 1.0
    assert report["METADATA_ONLY"].coverage == 0.0  # nothing auto-decided
    assert report["__overall__"].n == 3


def test_auto_precision_is_lower_bound_below_point_estimate():
    # 4 auto-decided, 3 correct -> point 0.75, LB below it.
    items = [
        _item("FULLTEXT", "SDL", "SDL", 0.9, True),
        _item("FULLTEXT", "SDL", "SDL", 0.9, True),
        _item("FULLTEXT", "SDL", "SDL", 0.9, True),
        _item("FULLTEXT", "SDL", "NOT_SDL", 0.9, True),
    ]
    m = evaluate_by_tier(items)["FULLTEXT"]
    assert m.auto_precision == pytest.approx(0.75)
    assert m.auto_precision_lb < m.auto_precision
    assert m.review_rate == 0.0


def test_review_rate_complements_coverage():
    items = [
        _item("PARTIAL_FULLTEXT", "SDL", "SDL", 0.9, True),
        _item("PARTIAL_FULLTEXT", "SDL", "SDL", 0.4, False),
    ]
    m = evaluate_by_tier(items)["PARTIAL_FULLTEXT"]
    assert m.coverage == 0.5
    assert m.review_rate == 0.5


def test_auto_precision_only_counts_auto_decided_items():
    # The wrong prediction is NOT auto-decided, so auto-precision stays perfect.
    items = [
        _item("FULLTEXT", "SDL", "SDL", 0.95, True),
        _item("FULLTEXT", "SDL", "NOT_SDL", 0.3, False),
    ]
    m = evaluate_by_tier(items)["FULLTEXT"]
    assert m.auto_precision == 1.0
    assert m.coverage == 0.5
    assert m.accuracy == 0.5  # overall accuracy still counts the miss


def test_empty_is_safe():
    assert evaluate_by_tier([]) == {}
