"""Shared contracts for corpus provenance and independent human judgements."""

from __future__ import annotations

from collections.abc import Iterable

SDL_JUDGEMENTS = frozenset(
    {
        "CONFIRMED_SDL",
        "PROBABLE_SDL",
        "SDL_ADJACENT",
        "NOT_SDL",
        "INSUFFICIENT_EVIDENCE",
    }
)
AC_RELEVANCE_JUDGEMENTS = frozenset(
    {
        "AC_RELEVANT",
        "NOT_AC_RELEVANT",
        "INSUFFICIENT_EVIDENCE",
    }
)
AI_FOR_SCIENCE_JUDGEMENTS = frozenset(
    {
        "AI_FOR_SCIENCE",
        "NOT_AI_FOR_SCIENCE",
        "INSUFFICIENT_EVIDENCE",
    }
)
REVIEW_STATUSES = frozenset({"PENDING", "PARTIAL", "COMPLETED", "NEEDS_FULLTEXT"})
EVIDENCE_LEVELS = frozenset(
    {
        "TITLE_ONLY",
        "ABSTRACT",
        "FULLTEXT",
        "SUPPORTING_INFORMATION",
        "UNKNOWN",
    }
)
JUDGEMENT_BASES = frozenset({"DUAL_REVIEW", "AC_REPORTING", "STRICT_SDL", "OTHER"})

CORPUS_SOURCES = frozenset(
    {
        "AC_MEMBER_CORPUS",
        "STRICT_SDL_KEYWORD",
        "ARCHITECTURE_BROAD_RETRIEVAL",
        "MANUALLY_ADDED",
        "CITATION_EXPANSION",
        "SEMANTIC_EXPANSION",
        "LEGACY_IMPORT",
        "OTHER",
    }
)


def normalize_corpus_sources(values: Iterable[object]) -> list[str]:
    """Return a stable, deduplicated list of supported corpus-source labels."""
    normalized: list[str] = []
    for value in values:
        label = str(value or "").strip().upper()
        if not label:
            continue
        if label not in CORPUS_SOURCES:
            label = "OTHER"
        if label not in normalized:
            normalized.append(label)
    return normalized


def infer_corpus_sources(
    *,
    provenance: str | None,
    source: str | None = None,
    retrieval_tier: str | None = None,
    ac_known_publication: bool = False,
    trigger_strategies: Iterable[str] = (),
) -> list[str]:
    """Map legacy ingestion metadata onto the explicit corpus-source contract."""
    inferred: list[str] = []
    provenance_value = str(provenance or "").strip().lower()
    source_value = str(source or "").strip().lower()
    tier_value = str(retrieval_tier or "").strip().lower()

    if ac_known_publication or provenance_value == "ac_gold":
        inferred.append("AC_MEMBER_CORPUS")
    if provenance_value in {"manual", "manual_upload"} or source_value == "manual":
        inferred.append("MANUALLY_ADDED")
    if "tier1" in tier_value:
        inferred.append("STRICT_SDL_KEYWORD")
    if "tier2" in tier_value:
        inferred.append("ARCHITECTURE_BROAD_RETRIEVAL")

    trigger_map = {
        "cite_of_core": "CITATION_EXPANSION",
        "ac_coauthor": "AC_MEMBER_CORPUS",
        "s2_recommend": "SEMANTIC_EXPANSION",
    }
    for strategy in trigger_strategies:
        mapped = trigger_map.get(str(strategy or "").strip().lower())
        if mapped:
            inferred.append(mapped)

    if not inferred:
        inferred.append(
            "LEGACY_IMPORT"
            if provenance_value in {"", "csv"} or source_value == "csv"
            else "OTHER"
        )
    return normalize_corpus_sources(inferred)
