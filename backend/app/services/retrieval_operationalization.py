"""Canonical SDL retrieval vocabulary from the operationalization protocol."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml


def _as_terms(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(v).strip() for v in values if str(v).strip()]


@lru_cache(maxsize=1)
def load_retrieval_operationalization(path: str | Path | None = None) -> dict:
    from app.config import settings

    p = Path(path or settings.retrieval_operationalization_yaml)
    if not p.exists():
        return {
            "tier1_label_terms": [],
            "tier2_architecture_terms": {
                "ai_decision_making": [],
                "automated_experimentation": [],
                "iterative_closed_loop": [],
            },
            "tier_definitions": {},
        }
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    tier2 = raw.get("tier2_architecture_terms", {}) or {}
    tier_definitions = raw.get("tier_definitions", {}) or {}
    return {
        "tier1_label_terms": _as_terms(raw.get("tier1_label_terms")),
        "tier2_architecture_terms": {
            "ai_decision_making": _as_terms(tier2.get("ai_decision_making")),
            "automated_experimentation": _as_terms(tier2.get("automated_experimentation")),
            "iterative_closed_loop": _as_terms(tier2.get("iterative_closed_loop")),
        },
        "tier_definitions": {
            str(tier): {
                "corpus_source": str((definition or {}).get("corpus_source") or ""),
                "scopus_query": str((definition or {}).get("scopus_query") or "").strip(),
            }
            for tier, definition in tier_definitions.items()
        },
    }


def reset_retrieval_operationalization_cache() -> None:
    load_retrieval_operationalization.cache_clear()


def tier1_label_terms() -> list[str]:
    return list(load_retrieval_operationalization()["tier1_label_terms"])


def architecture_terms(component: str) -> list[str]:
    terms = load_retrieval_operationalization()["tier2_architecture_terms"]
    return list(terms.get(component, []))


def retrieval_query(tier: str) -> str:
    definitions = load_retrieval_operationalization().get("tier_definitions", {})
    return str((definitions.get(tier) or {}).get("scopus_query") or "")


def sdl_methodology_terms() -> list[str]:
    """Terms suitable for fulltext method/proposition evidence extraction."""
    return (
        tier1_label_terms()
        + architecture_terms("automated_experimentation")
        + architecture_terms("iterative_closed_loop")
        + architecture_terms("ai_decision_making")
    )
