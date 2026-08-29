"""Human-review queues and honest field-level gold-set scoring."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from typing import Literal

from pydantic import Field

from app.domain_adaptation.models import DomainModel, EvidenceSpan, ProtocolUnit


EntityType = Literal[
    "material",
    "instrument",
    "software",
    "step",
    "characterization",
    "result",
    "caveat",
]
ReviewStatus = Literal["pending", "reviewed", "rejected"]


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:16]}"


def normalize_gold_value(value: str) -> str:
    """Normalize presentation differences without adding domain knowledge."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = normalized.replace("\u00ad", "")
    normalized = re.sub(r"[‐‑‒–—―−﹘﹣－]", "-", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return re.sub(r"(?<=\d)\s+(?=[a-zμµ°%])", "", normalized)


class CandidateClaim(DomainModel):
    schema_version: str = "domain-adapter-candidate-claim-v0.1"
    candidate_claim_id: str
    paper_id: str
    protocol_id: str
    source_entity_id: str
    entity_type: EntityType
    field_name: str
    source_value: str
    normalized_value: str
    evidence_ids: list[str] = Field(min_length=1)
    evidence_chunk_id: str
    evidence_quote: str
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)


class GoldProtocolAnnotation(DomainModel):
    schema_version: str = "domain-adapter-gold-protocol-v0.1"
    gold_protocol_id: str
    paper_id: str
    protocol_id: str
    review_status: ReviewStatus = "pending"
    annotation_complete: bool = False
    reviewer: str | None = None
    notes: str | None = None


class GoldEntityAnnotation(DomainModel):
    schema_version: str = "domain-adapter-gold-entity-v0.1"
    gold_entity_id: str
    paper_id: str
    protocol_id: str
    entity_type: EntityType
    field_name: str
    source_value: str
    normalized_value: str | None = None
    evidence_chunk_id: str
    evidence_quote: str
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    review_status: ReviewStatus = "pending"
    reviewer: str | None = None
    notes: str | None = None


class GoldMetricSlice(DomainModel):
    candidate_count: int = Field(ge=0)
    gold_count: int = Field(ge=0)
    true_positive_count: int = Field(ge=0)
    precision: float | None
    recall: float | None


class GoldScoreReport(DomainModel):
    schema_version: str = "domain-adapter-gold-score-v0.1"
    reviewed_protocol_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    gold_count: int = Field(ge=0)
    true_positive_count: int = Field(ge=0)
    precision: float | None
    recall: float | None
    span_alignment_rate: float | None
    by_entity_type: dict[str, GoldMetricSlice]


def _primary_evidence(
    protocol: ProtocolUnit, evidence_ids: list[str]
) -> EvidenceSpan:
    evidence_by_id = {item.evidence_id: item for item in protocol.evidence}
    for evidence_id in evidence_ids:
        if evidence_id in evidence_by_id:
            return evidence_by_id[evidence_id]
    raise ValueError(
        f"Structured field in {protocol.protocol_id} has no resolvable evidence"
    )


def build_candidate_claims(protocols: list[ProtocolUnit]) -> list[CandidateClaim]:
    """Flatten structured protocol fields into evidence-bound review claims."""
    claims: list[CandidateClaim] = []

    def add(
        protocol: ProtocolUnit,
        *,
        source_entity_id: str,
        entity_type: EntityType,
        field_name: str,
        value: str | None,
        evidence_ids: list[str],
    ) -> None:
        if value is None or not value.strip():
            return
        evidence = _primary_evidence(protocol, evidence_ids)
        source_value = value.strip()
        claims.append(
            CandidateClaim(
                candidate_claim_id=_stable_id(
                    "claim",
                    protocol.protocol_id,
                    source_entity_id,
                    field_name,
                    source_value,
                ),
                paper_id=protocol.paper_id,
                protocol_id=protocol.protocol_id,
                source_entity_id=source_entity_id,
                entity_type=entity_type,
                field_name=field_name,
                source_value=source_value,
                normalized_value=normalize_gold_value(source_value),
                evidence_ids=evidence_ids,
                evidence_chunk_id=evidence.chunk_id,
                evidence_quote=evidence.quote,
                char_start=evidence.char_start,
                char_end=evidence.char_end,
            )
        )

    for protocol in sorted(protocols, key=lambda item: item.protocol_id):
        for material in protocol.materials:
            for field_name in (
                "name",
                "role",
                "amount",
                "purity",
                "supplier",
                "pretreatment",
            ):
                add(
                    protocol,
                    source_entity_id=material.entity_id,
                    entity_type="material",
                    field_name=field_name,
                    value=getattr(material, field_name),
                    evidence_ids=material.evidence_ids,
                )
        for instrument in protocol.instruments:
            for field_name in ("name", "model", "manufacturer"):
                add(
                    protocol,
                    source_entity_id=instrument.entity_id,
                    entity_type="instrument",
                    field_name=field_name,
                    value=getattr(instrument, field_name),
                    evidence_ids=instrument.evidence_ids,
                )
            for key, value in sorted(instrument.settings.items()):
                add(
                    protocol,
                    source_entity_id=instrument.entity_id,
                    entity_type="instrument",
                    field_name=f"settings.{key}",
                    value=value,
                    evidence_ids=instrument.evidence_ids,
                )
        for software in protocol.software:
            for field_name in ("name", "version"):
                add(
                    protocol,
                    source_entity_id=software.entity_id,
                    entity_type="software",
                    field_name=field_name,
                    value=getattr(software, field_name),
                    evidence_ids=software.evidence_ids,
                )
            for key, value in sorted(software.settings.items()):
                add(
                    protocol,
                    source_entity_id=software.entity_id,
                    entity_type="software",
                    field_name=f"settings.{key}",
                    value=value,
                    evidence_ids=software.evidence_ids,
                )
        for step in protocol.steps:
            add(
                protocol,
                source_entity_id=step.step_id,
                entity_type="step",
                field_name="action",
                value=step.action,
                evidence_ids=step.evidence_ids,
            )
            for index, condition in enumerate(step.conditions):
                add(
                    protocol,
                    source_entity_id=step.step_id,
                    entity_type="step",
                    field_name=f"conditions[{index}]",
                    value=condition,
                    evidence_ids=step.evidence_ids,
                )
            add(
                protocol,
                source_entity_id=step.step_id,
                entity_type="step",
                field_name="notes",
                value=step.notes,
                evidence_ids=step.evidence_ids,
            )
        for characterization in protocol.characterization:
            add(
                protocol,
                source_entity_id=characterization.entity_id,
                entity_type="characterization",
                field_name="technique",
                value=characterization.technique,
                evidence_ids=characterization.evidence_ids,
            )
            for key, value in sorted(characterization.settings.items()):
                add(
                    protocol,
                    source_entity_id=characterization.entity_id,
                    entity_type="characterization",
                    field_name=f"settings.{key}",
                    value=value,
                    evidence_ids=characterization.evidence_ids,
                )
            add(
                protocol,
                source_entity_id=characterization.entity_id,
                entity_type="characterization",
                field_name="output",
                value=characterization.output,
                evidence_ids=characterization.evidence_ids,
            )
        for result in protocol.results:
            for field_name in ("metric", "raw_value", "context"):
                add(
                    protocol,
                    source_entity_id=result.result_id,
                    entity_type="result",
                    field_name=field_name,
                    value=getattr(result, field_name),
                    evidence_ids=result.evidence_ids,
                )
        for caveat in protocol.caveats:
            add(
                protocol,
                source_entity_id=caveat.caveat_id,
                entity_type="caveat",
                field_name="text",
                value=caveat.text,
                evidence_ids=caveat.evidence_ids,
            )
    return sorted(claims, key=lambda item: item.candidate_claim_id)


def build_gold_annotation_queue(
    protocols: list[ProtocolUnit],
) -> tuple[list[GoldProtocolAnnotation], list[GoldEntityAnnotation]]:
    protocol_queue = [
        GoldProtocolAnnotation(
            gold_protocol_id=_stable_id("gold_protocol", item.protocol_id),
            paper_id=item.paper_id,
            protocol_id=item.protocol_id,
        )
        for item in sorted(protocols, key=lambda value: value.protocol_id)
    ]
    entity_queue = [
        GoldEntityAnnotation(
            gold_entity_id=_stable_id(
                "gold_entity", candidate.candidate_claim_id
            ),
            paper_id=candidate.paper_id,
            protocol_id=candidate.protocol_id,
            entity_type=candidate.entity_type,
            field_name=candidate.field_name,
            source_value=candidate.source_value,
            normalized_value=candidate.normalized_value,
            evidence_chunk_id=candidate.evidence_chunk_id,
            evidence_quote=candidate.evidence_quote,
            char_start=candidate.char_start,
            char_end=candidate.char_end,
        )
        for candidate in build_candidate_claims(protocols)
    ]
    return protocol_queue, entity_queue


def _semantic_key(
    *,
    protocol_id: str,
    entity_type: str,
    field_name: str,
    value: str,
) -> tuple[str, str, str, str]:
    return (
        protocol_id,
        entity_type,
        field_name,
        normalize_gold_value(value),
    )


def _metric_slice(candidate_count: int, gold_count: int, tp: int) -> GoldMetricSlice:
    return GoldMetricSlice(
        candidate_count=candidate_count,
        gold_count=gold_count,
        true_positive_count=tp,
        precision=round(tp / candidate_count, 6) if candidate_count else None,
        recall=round(tp / gold_count, 6) if gold_count else None,
    )


def score_gold_entities(
    *,
    gold_protocols: list[GoldProtocolAnnotation],
    gold_entities: list[GoldEntityAnnotation],
    candidate_claims: list[CandidateClaim],
) -> GoldScoreReport:
    """Score only scopes explicitly marked reviewed and annotation-complete."""
    complete_protocol_ids = {
        item.protocol_id
        for item in gold_protocols
        if item.review_status == "reviewed" and item.annotation_complete
    }
    pending_in_complete_scope = [
        item
        for item in gold_entities
        if item.protocol_id in complete_protocol_ids
        and item.review_status == "pending"
    ]
    if pending_in_complete_scope:
        raise ValueError(
            "A complete review scope contains a pending gold entity"
        )

    scoped_candidates = [
        item
        for item in candidate_claims
        if item.protocol_id in complete_protocol_ids
    ]
    scoped_gold = [
        item
        for item in gold_entities
        if item.protocol_id in complete_protocol_ids
        and item.review_status == "reviewed"
    ]

    candidate_keys = Counter(
        _semantic_key(
            protocol_id=item.protocol_id,
            entity_type=item.entity_type,
            field_name=item.field_name,
            value=item.normalized_value,
        )
        for item in scoped_candidates
    )
    gold_keys = Counter(
        _semantic_key(
            protocol_id=item.protocol_id,
            entity_type=item.entity_type,
            field_name=item.field_name,
            value=item.normalized_value or item.source_value,
        )
        for item in scoped_gold
    )
    true_positive_count = sum((candidate_keys & gold_keys).values())

    def span_key(item, value: str) -> tuple:
        return (
            *_semantic_key(
                protocol_id=item.protocol_id,
                entity_type=item.entity_type,
                field_name=item.field_name,
                value=value,
            ),
            item.evidence_chunk_id,
            item.evidence_quote,
            item.char_start,
            item.char_end,
        )

    candidate_span_keys = Counter(
        span_key(item, item.normalized_value) for item in scoped_candidates
    )
    gold_span_keys = Counter(
        span_key(item, item.normalized_value or item.source_value)
        for item in scoped_gold
    )
    span_match_count = sum(
        (candidate_span_keys & gold_span_keys).values()
    )

    entity_types = sorted(
        {item.entity_type for item in scoped_candidates}
        | {item.entity_type for item in scoped_gold}
    )
    by_entity_type: dict[str, GoldMetricSlice] = {}
    for entity_type in entity_types:
        candidate_count = sum(
            item.entity_type == entity_type for item in scoped_candidates
        )
        gold_count = sum(item.entity_type == entity_type for item in scoped_gold)
        candidate_type_keys = Counter(
            _semantic_key(
                protocol_id=item.protocol_id,
                entity_type=item.entity_type,
                field_name=item.field_name,
                value=item.normalized_value,
            )
            for item in scoped_candidates
            if item.entity_type == entity_type
        )
        gold_type_keys = Counter(
            _semantic_key(
                protocol_id=item.protocol_id,
                entity_type=item.entity_type,
                field_name=item.field_name,
                value=item.normalized_value or item.source_value,
            )
            for item in scoped_gold
            if item.entity_type == entity_type
        )
        type_tp = sum((candidate_type_keys & gold_type_keys).values())
        by_entity_type[entity_type] = _metric_slice(
            candidate_count, gold_count, type_tp
        )

    overall = _metric_slice(
        len(scoped_candidates), len(scoped_gold), true_positive_count
    )
    return GoldScoreReport(
        reviewed_protocol_count=len(complete_protocol_ids),
        candidate_count=overall.candidate_count,
        gold_count=overall.gold_count,
        true_positive_count=overall.true_positive_count,
        precision=overall.precision,
        recall=overall.recall,
        span_alignment_rate=(
            round(span_match_count / true_positive_count, 6)
            if true_positive_count
            else None
        ),
        by_entity_type=by_entity_type,
    )
