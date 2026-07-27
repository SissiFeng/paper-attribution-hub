"""Typed metadata contract for derived attribution evidence paths."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ATTRIBUTION_EVIDENCE_METADATA_VERSION = "aet-evidence-meta-v0.1"
ATTRIBUTION_EVIDENCE_METADATA_NAMESPACE = "attribution_evidence"

AttributionCentrality = Literal[
    "core_contribution",
    "supporting_method",
    "background_only",
    "incidental_mention",
    "unrelated",
]
AttributionPolarity = Literal["positive", "negative"]
AttributionMetadataStatus = Literal[
    "versioned_validated",
    "legacy_validated",
    "legacy_fallback",
    "invalid_fallback",
    "not_applicable",
]


class AttributionEvidenceMetadata(BaseModel):
    """Versioned metadata accepted from ``PaperEvidence.extra``."""

    model_config = ConfigDict(extra="forbid", strict=True)

    contract_version: Literal["aet-evidence-meta-v0.1"] = (
        ATTRIBUTION_EVIDENCE_METADATA_VERSION
    )
    centrality: AttributionCentrality | None = None
    polarity: AttributionPolarity | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    detector_type: str | None = Field(default=None, max_length=100)
