"""Field-level evidence provenance and human-review annotations."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Literal

from pydantic import Field, model_validator

from app.domain_adaptation.alignment import normalized_text_contains
from app.domain_adaptation.gold import CandidateClaim, GoldProtocolAnnotation
from app.domain_adaptation.models import DomainModel, EvidenceSpan, ProtocolUnit


EvidenceOrigin = Literal[
    "author_reported_primary_experiment",
    "cited_method",
    "secondary_summary",
    "unknown",
]
EvidenceSupport = Literal[
    "exact",
    "deterministically_aligned",
    "explicitly_derived",
    "unsupported",
]
EvidenceModification = Literal[
    "none",
    "explicitly_modified",
    "unspecified",
]
DependencyReviewStatus = Literal["pending", "reviewed"]


_CITED_METHOD_RE = re.compile(
    r"\b(?:according to|adapted from|as (?:previously )?reported|"
    r"following|literature|previous(?:ly)?|ref\.?\s*\d|references?)\b|"
    r"\[(?:\d+[\s,;–-]*)+\]",
    re.IGNORECASE,
)
_EXPLICIT_MODIFICATION_RE = re.compile(
    r"\b(?:with (?:minor |slight )?modifications?|modified|adapted)\b",
    re.IGNORECASE,
)


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:16]}"


class EvidenceDependencyLabels(DomainModel):
    origin: EvidenceOrigin
    support: EvidenceSupport
    modification: EvidenceModification


class DirectEvidenceReference(DomainModel):
    evidence_id: str
    chunk_id: str
    quote: str
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    source_sha256: str


class FieldDerivation(DomainModel):
    rule_id: str = Field(min_length=1)
    expression: str = Field(min_length=1)
    input_dependency_ids: list[str] = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)


class EvidenceDependencyAnnotation(DomainModel):
    schema_version: str = "domain-adapter-evidence-dependency-v0.1"
    evidence_dependency_id: str
    candidate_claim_id: str
    paper_id: str
    protocol_id: str
    source_entity_id: str
    entity_type: str
    field_name: str
    source_value: str
    normalized_value: str
    direct_evidence: list[DirectEvidenceReference]
    depends_on_dependency_ids: list[str] = Field(default_factory=list)
    derivation: FieldDerivation | None = None
    proposed_labels: EvidenceDependencyLabels
    proposal_method: str = "deterministic_evidence_dependency_v0.1"
    review_status: DependencyReviewStatus = "pending"
    reviewed_labels: EvidenceDependencyLabels | None = None
    reviewer: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_review_state(self) -> "EvidenceDependencyAnnotation":
        if self.review_status == "pending" and self.reviewed_labels is not None:
            raise ValueError("Pending dependency cannot contain reviewed labels")
        if self.review_status == "reviewed" and self.reviewed_labels is None:
            raise ValueError("Reviewed dependency requires reviewed labels")
        if self.review_status == "reviewed" and not self.reviewer:
            raise ValueError("Reviewed dependency requires a reviewer")
        labels = self.reviewed_labels or self.proposed_labels
        if (
            labels.support in {"exact", "deterministically_aligned"}
            and not self.direct_evidence
        ):
            raise ValueError("Direct support requires at least one evidence span")
        if labels.support == "explicitly_derived" and self.derivation is None:
            raise ValueError("Derived support requires a derivation record")
        return self


def _proposed_origin(protocol: ProtocolUnit, quote: str) -> EvidenceOrigin:
    if protocol.evidence_scope == "secondary_report":
        return "secondary_summary"
    if _CITED_METHOD_RE.search(quote):
        return "cited_method"
    if protocol.evidence_scope == "primary_report":
        return "author_reported_primary_experiment"
    return "unknown"


def _proposed_modification(
    origin: EvidenceOrigin, quote: str
) -> EvidenceModification:
    if _EXPLICIT_MODIFICATION_RE.search(quote):
        return "explicitly_modified"
    if origin in {"cited_method", "secondary_summary"}:
        return "unspecified"
    return "none"


def _proposed_support(value: str, evidence: list[EvidenceSpan]) -> EvidenceSupport:
    if any(value in item.quote for item in evidence):
        return "exact"
    if any(normalized_text_contains(value, item.quote) for item in evidence):
        return "deterministically_aligned"
    return "unsupported"


def build_evidence_dependency_annotations(
    protocols: list[ProtocolUnit],
    candidate_claims: list[CandidateClaim],
) -> list[EvidenceDependencyAnnotation]:
    """Create deterministic proposals while leaving every record unreviewed."""
    protocol_by_id = {item.protocol_id: item for item in protocols}
    annotations: list[EvidenceDependencyAnnotation] = []
    for claim in sorted(candidate_claims, key=lambda item: item.candidate_claim_id):
        protocol = protocol_by_id.get(claim.protocol_id)
        if protocol is None:
            raise ValueError(
                f"Candidate claim references an unknown protocol: {claim.protocol_id}"
            )
        evidence_by_id = {item.evidence_id: item for item in protocol.evidence}
        evidence: list[EvidenceSpan] = []
        for evidence_id in claim.evidence_ids:
            item = evidence_by_id.get(evidence_id)
            if item is None:
                raise ValueError(
                    f"Candidate claim has unresolved evidence: {evidence_id}"
                )
            evidence.append(item)
        combined_quote = "\n".join(item.quote for item in evidence)
        origin = _proposed_origin(protocol, combined_quote)
        annotations.append(
            EvidenceDependencyAnnotation(
                evidence_dependency_id=_stable_id(
                    "evidence_dependency", claim.candidate_claim_id
                ),
                candidate_claim_id=claim.candidate_claim_id,
                paper_id=claim.paper_id,
                protocol_id=claim.protocol_id,
                source_entity_id=claim.source_entity_id,
                entity_type=claim.entity_type,
                field_name=claim.field_name,
                source_value=claim.source_value,
                normalized_value=claim.normalized_value,
                direct_evidence=[
                    DirectEvidenceReference(
                        evidence_id=item.evidence_id,
                        chunk_id=item.chunk_id,
                        quote=item.quote,
                        char_start=item.char_start,
                        char_end=item.char_end,
                        source_sha256=item.source_sha256,
                    )
                    for item in evidence
                ],
                proposed_labels=EvidenceDependencyLabels(
                    origin=origin,
                    support=_proposed_support(claim.source_value, evidence),
                    modification=_proposed_modification(origin, combined_quote),
                ),
            )
        )
    return annotations


def summarize_evidence_dependency_annotations(
    *,
    annotations: list[EvidenceDependencyAnnotation],
    gold_protocols: list[GoldProtocolAnnotation],
    candidate_claims: list[CandidateClaim],
) -> dict:
    """Validate queue coverage and summarize proposals versus reviewed labels."""
    candidate_ids = {item.candidate_claim_id for item in candidate_claims}
    annotation_ids = [item.candidate_claim_id for item in annotations]
    if len(annotation_ids) != len(set(annotation_ids)):
        raise ValueError("Duplicate evidence dependency for a candidate claim")
    if set(annotation_ids) != candidate_ids:
        missing = sorted(candidate_ids - set(annotation_ids))
        unexpected = sorted(set(annotation_ids) - candidate_ids)
        raise ValueError(
            "Evidence dependency queue does not cover candidate claims: "
            f"missing={missing}, unexpected={unexpected}"
        )

    complete_protocol_ids = {
        item.protocol_id
        for item in gold_protocols
        if item.review_status == "reviewed" and item.annotation_complete
    }
    pending_in_complete_scope = [
        item.evidence_dependency_id
        for item in annotations
        if item.protocol_id in complete_protocol_ids
        and item.review_status == "pending"
    ]
    if pending_in_complete_scope:
        raise ValueError(
            "A complete protocol scope contains a pending evidence dependency"
        )

    reviewed = [item for item in annotations if item.review_status == "reviewed"]

    def counts(labels) -> dict[str, dict[str, int]]:
        return {
            "origin": dict(sorted(Counter(item.origin for item in labels).items())),
            "support": dict(
                sorted(Counter(item.support for item in labels).items())
            ),
            "modification": dict(
                sorted(Counter(item.modification for item in labels).items())
            ),
        }

    return {
        "schema_version": "domain-adapter-evidence-dependency-summary-v0.1",
        "candidate_claim_count": len(candidate_claims),
        "annotation_count": len(annotations),
        "pending_count": len(annotations) - len(reviewed),
        "reviewed_count": len(reviewed),
        "complete_protocol_count": len(complete_protocol_ids),
        "proposed_label_counts": counts(
            [item.proposed_labels for item in annotations]
        ),
        "reviewed_label_counts": counts(
            [item.reviewed_labels for item in reviewed]
        ),
        "claims_boundary": (
            "Proposed labels are deterministic review aids, not human gold. "
            "Only reviewed_labels contribute to reviewed distributions."
        ),
    }
