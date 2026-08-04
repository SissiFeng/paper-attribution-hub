"""Selective-classification metrics.

* ``wilson_lower_bound`` — a confidence-interval lower bound for a proportion
  (e.g. auto-label precision). Report this, not the point estimate, so a lucky
  validation run cannot claim a precision it hasn't earned.
* ``risk_coverage_curve`` / ``aurc`` — the risk vs coverage trade-off of a
  selective classifier that abstains on low-confidence items.
* ``coverage_at_max_risk`` — the largest fraction of items that can be
  auto-decided while keeping empirical risk under a ceiling.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

_Z_95 = 1.959963984540054


def wilson_lower_bound(successes: int, n: int, z: float = _Z_95) -> float:
    """Wilson score interval lower bound for a binomial proportion.

    Returns 0.0 for an empty sample (no evidence of any precision).
    """
    if n < 0 or successes < 0:
        raise ValueError("counts must be non-negative")
    if successes > n:
        raise ValueError("successes cannot exceed n")
    if n == 0:
        return 0.0

    p = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = p + z2 / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z2 / (4 * n)) / n)
    return max(0.0, (center - margin) / denom)


@dataclass(frozen=True)
class RiskCoveragePoint:
    coverage: float
    risk: float
    threshold: float  # the confidence at this coverage level (the abstain cutoff)


def _sorted_desc(scored: list[tuple[float, bool]]) -> list[tuple[float, bool]]:
    # Most-confident first; that is the order a selective classifier keeps.
    return sorted(scored, key=lambda item: item[0], reverse=True)


def risk_coverage_curve(scored: list[tuple[float, bool]]) -> list[RiskCoveragePoint]:
    """Each point: cover the top-k most confident items, report (coverage, risk).

    ``scored`` is a list of ``(confidence, is_correct)``.
    """
    ordered = _sorted_desc(scored)
    n = len(ordered)
    points: list[RiskCoveragePoint] = []
    errors = 0
    for k, (conf, correct) in enumerate(ordered, start=1):
        if not correct:
            errors += 1
        points.append(
            RiskCoveragePoint(coverage=k / n, risk=errors / k, threshold=conf)
        )
    return points


def aurc(scored: list[tuple[float, bool]]) -> float:
    """Area under the risk-coverage curve (lower is better)."""
    curve = risk_coverage_curve(scored)
    if not curve:
        return 0.0
    return sum(point.risk for point in curve) / len(curve)


def coverage_at_max_risk(scored: list[tuple[float, bool]], max_risk: float) -> float:
    """Largest coverage whose selective risk stays <= ``max_risk``.

    This is the auto-decide operating point: for auto-label precision >= 0.95,
    call with ``max_risk=0.05``.
    """
    best = 0.0
    for point in risk_coverage_curve(scored):
        if point.risk <= max_risk:
            best = max(best, point.coverage)
    return best
