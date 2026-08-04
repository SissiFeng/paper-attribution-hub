"""Canonical paper-classification labels and review-label normalization."""

from __future__ import annotations

LABEL_CORE = "CORE_RELEVANT"
LABEL_RELATED = "RELATED_RELEVANT"
LABEL_SDL_FIELD = "SDL_FIELD_RELEVANT"
LABEL_ADJACENT = "ADJACENT"
LABEL_UNCERTAIN = "UNCERTAIN"
LABEL_EXCLUDE = "EXCLUDE"

CLASSIFICATION_LABEL_ORDER = (
    LABEL_CORE,
    LABEL_RELATED,
    LABEL_SDL_FIELD,
    LABEL_ADJACENT,
    LABEL_UNCERTAIN,
    LABEL_EXCLUDE,
)

CLASSIFICATION_LABELS = frozenset(CLASSIFICATION_LABEL_ORDER)
REVIEW_LABEL_ALIASES = {"INCLUDE": LABEL_RELATED}
REVIEW_LABELS = CLASSIFICATION_LABELS | REVIEW_LABEL_ALIASES.keys()


def normalize_classification_label(label: object) -> str | None:
    """Map a production/review label to the canonical classifier taxonomy."""
    normalized = str(label or "").strip().upper()
    if normalized in CLASSIFICATION_LABELS:
        return normalized
    return REVIEW_LABEL_ALIASES.get(normalized)
