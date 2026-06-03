"""Explainable node-importance scoring profiles.

The graph layer computes raw structural metrics; this module turns them into
report-specific scores with component contributions that can be rendered as
radar charts or weighting controls.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping


AUTHOR_DIMENSIONS = [
    "ac_proximity",
    "relationship_strength",
    "excess_centrality",
    "cross_sdl_diversity",
    "citation_affinity",
    "recency",
]


AUTHOR_PROFILES: dict[str, dict[str, float]] = {
    "ac_attribution": {
        "ac_proximity": 0.55,
        "relationship_strength": 0.20,
        "citation_affinity": 0.15,
        "recency": 0.10,
    },
    "bridge_builders": {
        "ac_proximity": 0.35,
        "excess_centrality": 0.30,
        "cross_sdl_diversity": 0.25,
        "relationship_strength": 0.10,
    },
    "institution_hubs": {
        "relationship_strength": 0.30,
        "excess_centrality": 0.25,
        "cross_sdl_diversity": 0.20,
        "ac_proximity": 0.15,
        "citation_affinity": 0.10,
    },
    "emerging_connectors": {
        "recency": 0.30,
        "excess_centrality": 0.25,
        "cross_sdl_diversity": 0.20,
        "ac_proximity": 0.15,
        "relationship_strength": 0.10,
    },
    "topic_diffusion": {
        "cross_sdl_diversity": 0.35,
        "relationship_strength": 0.20,
        "excess_centrality": 0.20,
        "ac_proximity": 0.15,
        "recency": 0.10,
    },
}


@dataclass(frozen=True)
class ImportanceResult:
    score: float
    profile: str
    components: dict[str, dict[str, float]]
    radar_axes: list[dict[str, float | str]]
    explanation: str
    weights: dict[str, float]


def normalize_weights(weights: Mapping[str, float]) -> dict[str, float]:
    clean = {
        name: max(0.0, float(weights.get(name, 0.0)))
        for name in AUTHOR_DIMENSIONS
    }
    total = sum(clean.values())
    if total <= 0:
        return {name: 0.0 for name in AUTHOR_DIMENSIONS}
    return {name: value / total for name, value in clean.items()}


def author_profile_weights(
    profile: str = "bridge_builders",
    overrides: Mapping[str, float] | None = None,
) -> tuple[str, dict[str, float]]:
    resolved_profile = profile if profile in AUTHOR_PROFILES else "bridge_builders"
    weights = dict(AUTHOR_PROFILES[resolved_profile])
    if overrides:
        for name, value in overrides.items():
            if name in AUTHOR_DIMENSIONS:
                weights[name] = float(value)
    return resolved_profile, normalize_weights(weights)


def compute_author_importance(
    *,
    metrics: Mapping[str, float],
    profile: str = "bridge_builders",
    weights_override: Mapping[str, float] | None = None,
) -> ImportanceResult:
    resolved_profile, weights = author_profile_weights(profile, weights_override)
    components: dict[str, dict[str, float]] = {}
    score = 0.0
    for name in AUTHOR_DIMENSIONS:
        value = _clamp01(float(metrics.get(name, 0.0)))
        weight = weights.get(name, 0.0)
        contribution = value * weight
        score += contribution
        components[name] = {
            "value": round(value, 4),
            "weight": round(weight, 4),
            "contribution": round(contribution, 4),
        }

    radar_axes = [
        {
            "key": name,
            "label": _DIMENSION_LABELS[name],
            "value": components[name]["value"],
            "weight": components[name]["weight"],
        }
        for name in AUTHOR_DIMENSIONS
    ]

    rounded_score = round(_clamp01(score), 4)
    return ImportanceResult(
        score=rounded_score,
        profile=resolved_profile,
        components=components,
        radar_axes=radar_axes,
        explanation=_explain(resolved_profile, components, rounded_score),
        weights={name: round(weight, 4) for name, weight in weights.items()},
    )


def author_metrics_from_graph(
    *,
    ppr_score: float,
    c_norm: float,
    cross_sdl_diversity: float,
    relationship_strength: float,
    citation_affinity: float = 0.0,
    recency: float = 1.0,
) -> dict[str, float]:
    return {
        "ac_proximity": _clamp01(ppr_score),
        "relationship_strength": _clamp01(relationship_strength),
        "excess_centrality": _clamp01(max(0.0, c_norm - 1.0) / 1.0),
        "cross_sdl_diversity": _clamp01(cross_sdl_diversity),
        "citation_affinity": _clamp01(citation_affinity),
        "recency": _clamp01(recency),
    }


def recency_from_years(active_years: list[int], *, now_year: int | None = None, tau: float = 4.0) -> float:
    if not active_years:
        return 0.0
    latest = max(active_years)
    if now_year is None:
        from datetime import UTC, datetime

        now_year = datetime.now(UTC).year
    age = max(0, now_year - latest)
    return _clamp01(math.exp(-age / max(tau, 1e-6)))


_DIMENSION_LABELS = {
    "ac_proximity": "AC proximity",
    "relationship_strength": "Relationship strength",
    "excess_centrality": "Excess centrality",
    "cross_sdl_diversity": "Cross-SDL diversity",
    "citation_affinity": "Citation affinity",
    "recency": "Recency",
}


def _explain(profile: str, components: Mapping[str, Mapping[str, float]], score: float) -> str:
    active = [
        (name, vals["contribution"], vals["value"])
        for name, vals in components.items()
        if vals["contribution"] > 0
    ]
    active.sort(key=lambda item: item[1], reverse=True)
    if not active:
        return f"{profile} score is {score:.2f}; no strong importance dimensions are active."
    top = [
        _DIMENSION_LABELS[name].lower()
        for name, _contribution, value in active[:3]
        if value >= 0.15
    ]
    if not top:
        return f"{profile} score is {score:.2f}; all dimensions are weak."
    return f"{profile} score is {score:.2f}, driven by " + ", ".join(top) + "."


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
