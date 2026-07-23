"""Group evaluation results by content-availability tier.

The natural-missingness benchmark exists because masking only OA/full-text
papers is selection-biased. Reporting per tier (FULLTEXT ... METADATA_ONLY)
exposes where the classifier is confident-and-right versus guessing.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.eval_harness.selective_metrics import aurc, wilson_lower_bound

_OVERALL = "__overall__"


@dataclass(frozen=True)
class EvalItem:
    paper_id: str
    tier: str
    gold_label: str
    predicted_label: str
    confidence: float
    auto_decided: bool


@dataclass(frozen=True)
class TierMetrics:
    tier: str
    n: int
    coverage: float  # fraction auto-decided
    review_rate: float  # 1 - coverage
    accuracy: float  # predicted == gold over all items in the tier
    auto_precision: float  # correct fraction among auto-decided (point estimate)
    auto_precision_lb: float  # Wilson lower bound of auto_precision
    aurc: float  # area under risk-coverage over all items by confidence


def _metrics_for(tier: str, items: list[EvalItem]) -> TierMetrics:
    n = len(items)
    auto = [i for i in items if i.auto_decided]
    auto_correct = sum(1 for i in auto if i.predicted_label == i.gold_label)
    correct = sum(1 for i in items if i.predicted_label == i.gold_label)
    scored = [(i.confidence, i.predicted_label == i.gold_label) for i in items]
    coverage = len(auto) / n if n else 0.0
    return TierMetrics(
        tier=tier,
        n=n,
        coverage=coverage,
        review_rate=1.0 - coverage,
        accuracy=correct / n if n else 0.0,
        auto_precision=auto_correct / len(auto) if auto else 0.0,
        auto_precision_lb=wilson_lower_bound(auto_correct, len(auto)),
        aurc=aurc(scored),
    )


def evaluate_by_tier(items: list[EvalItem]) -> dict[str, TierMetrics]:
    """Return per-tier metrics plus an ``__overall__`` roll-up. Empty -> {}."""
    if not items:
        return {}
    by_tier: dict[str, list[EvalItem]] = {}
    for item in items:
        by_tier.setdefault(item.tier, []).append(item)

    report = {tier: _metrics_for(tier, rows) for tier, rows in by_tier.items()}
    report[_OVERALL] = _metrics_for(_OVERALL, items)
    return report
