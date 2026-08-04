"""Report corpus evidence policy (D21).

Stakeholder contract: which papers may back externally reported SDL/AC
figures. This is a report-generation contract only — it never changes the
training corpus, the review queue, or any shared analytics filter.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.review_contract import SDL_JUDGEMENTS

EVIDENCE_MODE = Literal[
    "human_only",
    "human_high_confidence",
    "human_plus_probable",
    "all_threshold",
]

DEFAULT_CONFIDENCE_THRESHOLD = 0.8
DEFAULT_SDL_JUDGEMENTS = (
    "CONFIRMED_SDL",
    "PROBABLE_SDL",
    "SDL_ADJACENT",
)


class _PolicyQueryParamsMixin:
    def query_params(self) -> dict[str, object]:
        """Explicit URL params that fully replay this policy on report endpoints."""
        params: dict[str, object] = {
            "report_evidence_mode": self.mode,
            "report_evidence_confidence_threshold": self.confidence_threshold,
            "report_evidence_include_model_only": "true"
            if self.include_model_only_separately
            else "false",
            "report_evidence_allow_needs_fulltext": "true"
            if self.allow_needs_fulltext
            else "false",
            "report_evidence_allow_abstract_only": "true"
            if self.allow_abstract_only
            else "false",
            "report_evidence_exclude_unreviewed_broad": "true"
            if self.exclude_unreviewed_broad_retrieval
            else "false",
        }
        if self.sdl_judgements:
            params["report_evidence_sdl_judgements"] = sorted(
                set(self.sdl_judgements)
            )
        return params


class ReportEvidencePolicy(_PolicyQueryParamsMixin, BaseModel):
    """Which papers may back externally reported figures.

    mode:
      human_only            — human-confirmed SDL papers only.
      human_high_confidence — human-confirmed SDL papers plus model-SDL
                              papers (unreviewed) at confidence_threshold.
      human_plus_probable   — human-confirmed plus PROBABLE_SDL/SDL_ADJACENT
                              human judgement or model-equivalent label.
      all_threshold         — any SDL-relevant paper (unreviewed) at or above
                              confidence_threshold.

    Flags:
      include_model_only_separately   — also expose a model-only breakdown.
      allow_needs_fulltext            — NEEDS_FULLTEXT reviews may count.
      allow_abstract_only             — abstract-only evidence may count.
      exclude_unreviewed_broad_retrieval — drop ARCHITECTURE_BROAD_RETRIEVAL
                                           papers with no review at all.
    """

    mode: EVIDENCE_MODE = "human_plus_probable"
    confidence_threshold: float = Field(
        default=DEFAULT_CONFIDENCE_THRESHOLD, ge=0.0, le=1.0
    )
    sdl_judgements: list[str] = Field(default_factory=list)
    include_model_only_separately: bool = False
    allow_needs_fulltext: bool = False
    allow_abstract_only: bool = False
    exclude_unreviewed_broad_retrieval: bool = True

    @model_validator(mode="after")
    def _validate(self) -> "ReportEvidencePolicy":
        allowed = set(SDL_JUDGEMENTS)
        normalized: list[str] = []
        for value in self.sdl_judgements:
            label = str(value or "").strip().upper()
            if label and label in allowed and label not in normalized:
                normalized.append(label)
        self.sdl_judgements = normalized
        return self

    def effective_sdl_judgements(self) -> list[str]:
        if self.sdl_judgements:
            return list(self.sdl_judgements)
        if self.mode == "human_only":
            return ["CONFIRMED_SDL"]
        if self.mode in {"human_high_confidence", "all_threshold"}:
            return ["CONFIRMED_SDL", "PROBABLE_SDL", "SDL_ADJACENT"]
        return list(DEFAULT_SDL_JUDGEMENTS)

    def canonical(self) -> dict:
        """Explicit, stable representation for audit and replay."""
        return {
            "mode": self.mode,
            "confidence_threshold": self.confidence_threshold,
            "sdl_judgements": sorted(set(self.effective_sdl_judgements())),
            "include_model_only_separately": self.include_model_only_separately,
            "allow_needs_fulltext": self.allow_needs_fulltext,
            "allow_abstract_only": self.allow_abstract_only,
            "exclude_unreviewed_broad_retrieval": self.exclude_unreviewed_broad_retrieval,
        }
