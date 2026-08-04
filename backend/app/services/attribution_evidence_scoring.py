"""Persistence-neutral Attribution Evidence Path construction and scoring."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Protocol, Sequence

from pydantic import ValidationError

from app.attribution_evidence_contract import (
    ATTRIBUTION_EVIDENCE_METADATA_NAMESPACE,
    AttributionCentrality,
    AttributionEvidenceMetadata,
    AttributionMetadataStatus,
    AttributionPolarity,
)

SCORING_VERSION = "aet-score-v0.1"
_AC_FUNDING_PATTERNS = (
    r"acceleration\s+consortium",
    r"accelerat\w*\s+consortium",
    r"canada\s+first\s+research\s+excellence\s+fund",
    r"\bCFREF\b.*accel",
    r"\bA[Cc]\b.{0,20}(?:fund|grant|support|fellowship)",
    r"AC\s+(?:PDF|Core\s+Development|Research\s+Moonshot|Translation)\s+Grant",
    r"(?:fund|support)\w*\s+by\s+the\s+(?:Acceleration|AC\b)",
)

_CENTRALITY_BY_TYPE: dict[str, AttributionCentrality] = {
    "funding_acknowledgement": "core_contribution",
    "sdl_methodology": "core_contribution",
    "figure_caption_sdl": "supporting_method",
    "partner_institution_acknowledgement": "supporting_method",
    "disqualifying": "unrelated",
}
_METADATA_KEYS = {
    "centrality",
    "polarity",
    "confidence",
    "detector_type",
}


class EvidenceRow(Protocol):
    id: str
    paper_id: str
    chunk_id: str | None
    evidence_type: str
    evidence_source: str
    evidence_text: str
    score: float
    extra: dict | None


@dataclass(frozen=True)
class NormalizedAttributionEvidencePath:
    generation_id: str
    path_id: str
    path: tuple[str, ...]
    evidence_type: str
    polarity: AttributionPolarity
    centrality: AttributionCentrality
    raw_score: float
    weight: float
    source_evidence_id: str | None = None
    source_chunk_ids: tuple[str, ...] = ()
    quote: str | None = None
    confidence: float | None = None
    detector_type: str = "classifier_signal"
    metadata_status: AttributionMetadataStatus = "not_applicable"

    def to_dict(self) -> dict:
        return {
            "generation_id": self.generation_id,
            "path_id": self.path_id,
            "path": list(self.path),
            "evidence_type": self.evidence_type,
            "polarity": self.polarity,
            "centrality": self.centrality,
            "raw_score": self.raw_score,
            "weight": self.weight,
            "source_evidence_id": self.source_evidence_id,
            "source_chunk_ids": list(self.source_chunk_ids),
            "quote": self.quote,
            "confidence": self.confidence,
            "detector_type": self.detector_type,
            "metadata_status": self.metadata_status,
        }


@dataclass(frozen=True)
class AttributionEvidenceSignals:
    generation_id: str
    paths: tuple[NormalizedAttributionEvidencePath, ...]
    score: float
    positive_score: float
    negative_score: float
    has_strong_ac_evidence: bool
    has_partner_affiliation: bool
    has_core_topic: bool
    has_sdl_method: bool
    has_collaboration: bool
    conflicting: bool

    @property
    def positive_path_ids(self) -> list[str]:
        return [
            path.path_id
            for path in self.paths
            if path.polarity == "positive" and path.weight > 0
        ]

    @property
    def negative_path_ids(self) -> list[str]:
        return [
            path.path_id
            for path in self.paths
            if path.polarity == "negative" and path.weight > 0
        ]

    def to_summary(self) -> dict:
        return {
            "type": "attribution_evidence_decision",
            "version": SCORING_VERSION,
            "generation_id": self.generation_id,
            "score": self.score,
            "positive_score": self.positive_score,
            "negative_score": self.negative_score,
            "conflicting": self.conflicting,
            "positive_path_ids": self.positive_path_ids,
            "negative_path_ids": self.negative_path_ids,
            "paths": [path.to_dict() for path in self.paths],
        }


def has_ac_funding_in_text(*texts: str | None) -> bool:
    """Return whether metadata text contains an AC funding acknowledgement."""
    combined = " ".join(text for text in texts if text)
    return bool(
        combined
        and any(
            re.search(pattern, combined, re.IGNORECASE)
            for pattern in _AC_FUNDING_PATTERNS
        )
    )


def parse_attribution_metadata(
    extra: dict | None,
) -> tuple[AttributionEvidenceMetadata, AttributionMetadataStatus]:
    raw = extra or {}
    if ATTRIBUTION_EVIDENCE_METADATA_NAMESPACE in raw:
        try:
            metadata = AttributionEvidenceMetadata.model_validate(
                raw[ATTRIBUTION_EVIDENCE_METADATA_NAMESPACE]
            )
        except ValidationError:
            return AttributionEvidenceMetadata(), "invalid_fallback"
        return metadata, "versioned_validated"

    legacy_payload = {key: raw[key] for key in _METADATA_KEYS if key in raw}
    if not legacy_payload:
        return AttributionEvidenceMetadata(), "legacy_fallback"
    try:
        metadata = AttributionEvidenceMetadata.model_validate(legacy_payload)
    except ValidationError:
        return AttributionEvidenceMetadata(), "invalid_fallback"
    return metadata, "legacy_validated"


def attribution_centrality(
    evidence: EvidenceRow, metadata: AttributionEvidenceMetadata
) -> AttributionCentrality:
    if metadata.centrality is not None:
        return metadata.centrality
    return _CENTRALITY_BY_TYPE.get(evidence.evidence_type, "incidental_mention")


def attribution_polarity(
    evidence: EvidenceRow, metadata: AttributionEvidenceMetadata
) -> AttributionPolarity:
    if metadata.polarity is not None:
        return metadata.polarity
    if evidence.evidence_type == "disqualifying" or evidence.score < 0:
        return "negative"
    return "positive"


def score_attribution_evidence(
    *,
    evidence_rows: Sequence[EvidenceRow],
    author_score: float,
    institution_score: float,
    topic_score: float,
    network_score: float,
    citation_score: float,
    has_funding_evidence: bool,
    has_second_degree: bool,
    cites_ac_core: bool,
    has_core_topic_match: bool,
) -> AttributionEvidenceSignals:
    """Build one normalized path set and summarize its decision strength."""
    sorted_rows = sorted(
        evidence_rows,
        key=lambda row: (
            row.evidence_type,
            -abs(row.score),
            row.chunk_id or "",
            row.evidence_text,
            row.id,
        ),
    )
    source_snapshot = {
        "version": SCORING_VERSION,
        "signals": {
            "author_score": round(author_score, 6),
            "institution_score": round(institution_score, 6),
            "topic_score": round(topic_score, 6),
            "network_score": round(network_score, 6),
            "citation_score": round(citation_score, 6),
            "has_funding_evidence": has_funding_evidence,
            "has_second_degree": has_second_degree,
            "cites_ac_core": cites_ac_core,
            "has_core_topic_match": has_core_topic_match,
        },
        "evidence": [_evidence_snapshot(row) for row in sorted_rows],
    }
    generation_id = _content_hash(source_snapshot, length=24)
    paths: list[NormalizedAttributionEvidencePath] = []

    def add_signal(
        evidence_type: str,
        path_label: str,
        weight: float,
        *,
        centrality: AttributionCentrality = "supporting_method",
    ) -> None:
        paths.append(
            NormalizedAttributionEvidencePath(
                generation_id=generation_id,
                path_id=f"aet-path:{generation_id}:signal:{evidence_type}",
                path=("Paper", "Signals", path_label),
                evidence_type=evidence_type,
                polarity="positive",
                centrality=centrality,
                raw_score=weight,
                weight=weight,
                quote=f"Derived classifier signal: {evidence_type}",
            )
        )

    if author_score >= 0.9:
        add_signal("ac_author", "AC author", 0.25, centrality="core_contribution")
    if institution_score >= 0.5:
        add_signal("ac_affiliation", "AC affiliation", 0.30)
    if has_core_topic_match and topic_score >= 0.7:
        add_signal(
            "topic_relevance",
            "Core topic relevance",
            0.12,
            centrality="core_contribution",
        )
    if has_second_degree and network_score > 0:
        add_signal("collaborator_link", "Collaboration link", 0.10)
    if cites_ac_core and citation_score > 0:
        add_signal("citation_link", "Citation link", 0.08)

    seen_content: set[str] = set()
    counted_types: set[str] = set()
    saw_funding_row = False
    for evidence in sorted_rows:
        snapshot = _evidence_snapshot(evidence)
        content_id = _content_hash(snapshot, length=16)
        if content_id in seen_content:
            continue
        seen_content.add(content_id)
        metadata, metadata_status = parse_attribution_metadata(evidence.extra)
        polarity = attribution_polarity(evidence, metadata)
        centrality = attribution_centrality(evidence, metadata)
        counted = evidence.evidence_type not in counted_types
        counted_types.add(evidence.evidence_type)
        weight = _normalized_weight(
            evidence,
            polarity=polarity,
            centrality=centrality,
            counted=counted,
        )
        if evidence.evidence_type == "funding_acknowledgement":
            saw_funding_row = True
        paths.append(
            NormalizedAttributionEvidencePath(
                generation_id=generation_id,
                path_id=f"aet-path:{generation_id}:evidence:{content_id}",
                path=(
                    "Paper",
                    _display_name(evidence.evidence_source),
                    evidence.evidence_type,
                ),
                evidence_type=evidence.evidence_type,
                polarity=polarity,
                centrality=centrality,
                raw_score=round(evidence.score, 3),
                weight=weight,
                source_evidence_id=evidence.id,
                source_chunk_ids=(evidence.chunk_id,) if evidence.chunk_id else (),
                quote=evidence.evidence_text,
                confidence=metadata.confidence,
                detector_type=metadata.detector_type or "legacy_rule",
                metadata_status=metadata_status,
            )
        )

    if has_funding_evidence and not saw_funding_row:
        add_signal(
            "ac_funding",
            "AC funding",
            0.35,
            centrality="core_contribution",
        )

    positive_score = round(
        sum(
            path.weight
            for path in paths
            if path.polarity == "positive" and path.weight > 0
        ),
        3,
    )
    negative_score = round(
        sum(
            path.weight
            for path in paths
            if path.polarity == "negative" and path.weight > 0
        ),
        3,
    )
    score = round(max(0.0, min(1.0, positive_score - negative_score)), 3)
    has_sdl_method = any(
        path.polarity == "positive"
        and path.weight > 0
        and path.evidence_type in {"sdl_methodology", "figure_caption_sdl"}
        for path in paths
    )
    return AttributionEvidenceSignals(
        generation_id=generation_id,
        paths=tuple(paths),
        score=score,
        positive_score=positive_score,
        negative_score=negative_score,
        has_strong_ac_evidence=any(
            path.polarity == "positive"
            and path.weight > 0
            and path.evidence_type
            in {"ac_author", "ac_funding", "funding_acknowledgement"}
            for path in paths
        ),
        has_partner_affiliation=institution_score >= 0.5,
        has_core_topic=has_core_topic_match and topic_score >= 0.7,
        has_sdl_method=has_sdl_method,
        has_collaboration=has_second_degree and network_score > 0,
        conflicting=positive_score > 0 and negative_score > 0,
    )


def _normalized_weight(
    evidence: EvidenceRow,
    *,
    polarity: AttributionPolarity,
    centrality: AttributionCentrality,
    counted: bool,
) -> float:
    if not counted:
        return 0.0
    if polarity == "negative":
        return round(min(abs(evidence.score), 0.25), 3)
    if centrality not in {"core_contribution", "supporting_method"}:
        return 0.0
    if evidence.evidence_type == "funding_acknowledgement":
        return 0.35
    if evidence.evidence_type == "sdl_methodology":
        return 0.30 if centrality == "core_contribution" else 0.18
    if evidence.evidence_type in {
        "figure_caption_sdl",
        "partner_institution_acknowledgement",
    }:
        return 0.18
    return 0.0


def _evidence_snapshot(evidence: EvidenceRow) -> dict:
    return {
        "paper_id": evidence.paper_id,
        "chunk_id": evidence.chunk_id,
        "evidence_type": evidence.evidence_type,
        "evidence_source": evidence.evidence_source,
        "evidence_text": evidence.evidence_text,
        "score": round(evidence.score, 6),
        "extra": evidence.extra,
    }


def _content_hash(value: dict, *, length: int) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return hashlib.sha256(encoded).hexdigest()[:length]


def _display_name(value: str) -> str:
    return value.replace("_", " ").strip().title() or "Unlocated Evidence"
