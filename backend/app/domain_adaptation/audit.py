"""Field-level audit records for teacher extraction and evidence repair."""

from __future__ import annotations

from enum import StrEnum

from app.domain_adaptation.models import DomainModel


class RejectionReason(StrEnum):
    """Stable reason codes for rejected or deterministically repaired fields."""

    NO_SPAN = "no_span"
    SPAN_NOT_IN_SOURCE = "span_not_in_source"
    WHITESPACE_MISMATCH = "whitespace_mismatch"
    HYPHENATION = "hyphenation"
    NORMALIZATION = "normalization"
    VALUE_ELSEWHERE = "value_elsewhere"
    OVER_GENERALIZED = "over_generalized"
    SCHEMA_INVALID = "schema_invalid"


class FieldAuditOutcome(StrEnum):
    REPAIRED = "repaired"
    REJECTED = "rejected"


class TeacherFieldAuditRecord(DomainModel):
    schema_version: str = "teacher-field-audit-v0.1"
    outcome: FieldAuditOutcome
    paper_id: str
    protocol_index: int
    entity_type: str
    field_path: str
    proposed_value: str | None
    cited_span: str | None
    rejection_reason: RejectionReason
    nearest_source_span: str | None = None
    repair_attempted: bool = False
    repair_succeeded: bool = False
    diagnostic: str | None = None
