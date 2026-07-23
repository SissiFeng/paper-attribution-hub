"""Selective-classification metrics: CI lower bounds and risk-coverage / AURC.

Auto-label precision must be reported as a confidence-interval lower bound, not
a validation-set point estimate, and the FINAL/NEEDS_REVIEW operating point is a
risk-coverage trade-off.
"""

from __future__ import annotations

import pytest

from app.services.eval_harness.selective_metrics import (
    aurc,
    coverage_at_max_risk,
    risk_coverage_curve,
    wilson_lower_bound,
)


def test_wilson_lower_bound_is_below_point_estimate():
    # 19/20 correct -> point estimate 0.95, LB strictly below it.
    lb = wilson_lower_bound(19, 20)
    assert 0.75 < lb < 0.95


def test_wilson_lower_bound_perfect_sample_still_below_one():
    lb = wilson_lower_bound(10, 10)
    assert 0.6 < lb < 1.0


def test_wilson_lower_bound_more_data_tightens():
    assert wilson_lower_bound(95, 100) > wilson_lower_bound(19, 20)


def test_wilson_lower_bound_empty_is_zero():
    assert wilson_lower_bound(0, 0) == 0.0


def test_wilson_lower_bound_rejects_bad_counts():
    with pytest.raises(ValueError):
        wilson_lower_bound(5, 3)


def test_risk_coverage_all_correct_is_zero_risk_everywhere():
    scored = [(0.9, True), (0.8, True), (0.7, True)]
    curve = risk_coverage_curve(scored)
    assert [round(p.coverage, 3) for p in curve] == [0.333, 0.667, 1.0]
    assert all(p.risk == 0.0 for p in curve)
    assert aurc(scored) == 0.0


def test_risk_coverage_orders_by_confidence_desc():
    # The one wrong item has the LOWEST confidence, so risk stays 0 until full coverage.
    scored = [(0.9, True), (0.8, True), (0.3, False)]
    curve = risk_coverage_curve(scored)
    assert curve[0].risk == 0.0  # top-1 covered, correct
    assert curve[1].risk == 0.0  # top-2 covered, both correct
    assert round(curve[2].risk, 3) == 0.333  # full coverage, 1/3 wrong


def test_aurc_penalizes_low_confidence_errors_less():
    # Error at high confidence is worse (higher AURC) than error at low confidence.
    err_high = [(0.9, False), (0.8, True), (0.7, True)]
    err_low = [(0.9, True), (0.8, True), (0.7, False)]
    assert aurc(err_high) > aurc(err_low)


def test_coverage_at_max_risk_selects_confident_prefix():
    # Sorted desc: T,T,T,F -> can cover 3/4 at 0 risk; adding the 4th -> 0.25 risk.
    scored = [(0.9, True), (0.8, True), (0.7, True), (0.6, False)]
    assert coverage_at_max_risk(scored, 0.05) == pytest.approx(0.75)
    assert coverage_at_max_risk(scored, 0.30) == pytest.approx(1.0)


def test_coverage_at_max_risk_zero_when_top_item_wrong():
    scored = [(0.9, False), (0.8, True), (0.7, True)]
    assert coverage_at_max_risk(scored, 0.05) == 0.0


def test_empty_inputs_are_safe():
    assert risk_coverage_curve([]) == []
    assert aurc([]) == 0.0
    assert coverage_at_max_risk([], 0.05) == 0.0
