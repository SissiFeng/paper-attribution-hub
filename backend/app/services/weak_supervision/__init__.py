"""Programmatic weak supervision: fuse noisy, abstaining labeling functions
into probabilistic labels by learning per-LF reliability from agreement.

Correlation beyond source-level deduplication is not yet modeled (a Snorkel
MeTaL-style correlation structure is future work); the current model handles
the dominant correlation — several APIs echoing one underlying record — via
provenance-key dedup.
"""

from app.services.weak_supervision.label_model import (
    ABSTAIN,
    NEGATIVE,
    POSITIVE,
    LabelModel,
    LabelModelResult,
    LFVote,
    dedup_votes,
)

__all__ = [
    "ABSTAIN",
    "NEGATIVE",
    "POSITIVE",
    "LabelModel",
    "LabelModelResult",
    "LFVote",
    "dedup_votes",
]
