"""Typed P0 contract for auditable AC paper-attribution skills."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

ATTRIBUTION_SKILL_CONTRACT_VERSION = "ac-attribution-skill-v0.1"

AttributionDecision = Literal[
    "ATTRIBUTED",
    "NOT_ATTRIBUTED",
    "REVIEW_REQUIRED",
]
AttributionRelevanceLabel = Literal[
    "CORE_RELEVANT",
    "RELATED_RELEVANT",
    "SDL_FIELD_RELEVANT",
    "ADJACENT",
    "EXCLUDE",
]
AttributionDecisionAuthority = Literal[
    "machine_provisional",
    "human_confirmed",
    "policy_override",
]
AttributionEvidencePolarity = Literal["supporting", "contradicting"]
AttributionTemporalStatus = Literal[
    "valid",
    "invalid",
    "unknown",
    "conflicting",
    "not_applicable",
]
AttributionFailureStage = Literal[
    "retrieval",
    "extraction",
    "identity",
    "membership",
    "topic",
    "citation",
    "model",
    "graph",
    "human_review",
    "system",
]
AttributionFailureCategory = Literal[
    "metadata_missing",
    "fulltext_unavailable",
    "fulltext_parse_failed",
    "ambiguous_author_identity",
    "affiliation_alias_unresolved",
    "membership_temporal_conflict",
    "topic_false_positive",
    "citation_only_weak_evidence",
    "funding_acknowledgement_ambiguous",
    "classifier_disagreement",
    "graph_propagation_conflict",
    "budget_exhausted",
    "upstream_unavailable",
    "retry_exhausted",
    "internal_error",
]
FulltextRetrievalStatus = Literal[
    "not_requested",
    "cache_hit",
    "retrieved",
    "unavailable",
    "failed",
]
AttributionReadSkillName = Literal[
    "determine_ac_paper_attribution",
    "resolve_ambiguous_author_identity",
    "verify_membership_at_publication_time",
    "collect_auditable_attribution_evidence",
    "adjudicate_classifier_disagreement",
]
AttributionSkillInvocationStatus = Literal[
    "in_progress",
    "succeeded",
    "review_required",
    "failed",
    "budget_exhausted",
]


class _StrictContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EvidenceSourceProvenance(_StrictContractModel):
    """Stable pointer back to the record from which evidence was derived."""

    provider: str = Field(min_length=1, max_length=100)
    source_record_id: str = Field(min_length=1, max_length=500)
    source_uri: str | None = Field(default=None, max_length=2000)
    retrieved_at: AwareDatetime | None = None
    content_hash: str | None = Field(default=None, min_length=8, max_length=128)


class EvidenceTemporalValidity(_StrictContractModel):
    """Time interval over which an evidence claim is applicable."""

    status: AttributionTemporalStatus
    valid_from: date | None = None
    valid_to: date | None = None
    basis: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_interval(self) -> "EvidenceTemporalValidity":
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_from > self.valid_to
        ):
            raise ValueError("valid_from must not be later than valid_to")
        return self


class AuditableAttributionEvidence(_StrictContractModel):
    evidence_id: str = Field(min_length=1, max_length=200)
    evidence_type: str = Field(min_length=1, max_length=100)
    polarity: AttributionEvidencePolarity
    claim: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: EvidenceSourceProvenance
    temporal_validity: EvidenceTemporalValidity
    quote: str | None = None
    source_chunk_id: str | None = Field(default=None, max_length=200)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    detector_type: str | None = Field(default=None, max_length=100)
    detector_version: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_pages(self) -> "AuditableAttributionEvidence":
        if (
            self.page_start is not None
            and self.page_end is not None
            and self.page_start > self.page_end
        ):
            raise ValueError("page_start must not be later than page_end")
        return self


class AttributionFailure(_StrictContractModel):
    stage: AttributionFailureStage
    category: AttributionFailureCategory
    detail: str | None = Field(default=None, max_length=2000)
    retryable: bool = False


class AttributionCostSummary(_StrictContractModel):
    retrieval_api_calls: int = Field(default=0, ge=0)
    fulltext_retrieval_status: FulltextRetrievalStatus = "not_requested"
    extraction_seconds: float = Field(default=0.0, ge=0.0)
    model_calls: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0.0, ge=0.0)
    graph_queries: int = Field(default=0, ge=0)
    human_review_seconds: float = Field(default=0.0, ge=0.0)
    retries: int = Field(default=0, ge=0)


class AttributionInvocationBudget(_StrictContractModel):
    max_wall_seconds: float | None = Field(default=None, gt=0.0)
    max_retrieval_api_calls: int | None = Field(default=None, ge=0)
    max_model_calls: int | None = Field(default=None, ge=0)
    max_input_tokens: int | None = Field(default=None, ge=0)
    max_estimated_cost_usd: float | None = Field(default=None, ge=0.0)


class AttributionDecisionResult(_StrictContractModel):
    decision: AttributionDecision
    relevance_label: AttributionRelevanceLabel | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    authority: AttributionDecisionAuthority
    policy_version: str = Field(min_length=1, max_length=100)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    unresolved_ambiguities: list[str] = Field(default_factory=list)
    recommended_review_action: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_decision(self) -> "AttributionDecisionResult":
        overlap = set(self.supporting_evidence_ids) & set(
            self.contradicting_evidence_ids
        )
        if overlap:
            raise ValueError(
                "supporting and contradicting evidence ids must be disjoint"
            )
        if self.decision == "REVIEW_REQUIRED" and not self.recommended_review_action:
            raise ValueError(
                "REVIEW_REQUIRED decisions must include a recommended review action"
            )
        return self


class AttributionDeterminationOutcome(_StrictContractModel):
    outcome_type: Literal["attribution_determination"]
    decision: AttributionDecision


class AuthorIdentityResolutionOutcome(_StrictContractModel):
    outcome_type: Literal["author_identity_resolution"]
    resolved: bool
    resolved_author_ids: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)


class MembershipVerificationOutcome(_StrictContractModel):
    outcome_type: Literal["membership_verification"]
    verified: bool
    publication_year: int | None = None
    valid_membership_evidence_ids: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)


class EvidenceCollectionOutcome(_StrictContractModel):
    outcome_type: Literal["evidence_collection"]
    evidence_count: int = Field(ge=0)
    supporting_count: int = Field(ge=0)
    contradicting_count: int = Field(ge=0)


class ClassifierDisagreementOutcome(_StrictContractModel):
    outcome_type: Literal["classifier_disagreement"]
    disagreement_detected: bool
    adjudicated: bool
    ambiguities: list[str] = Field(default_factory=list)


AttributionSkillOutcome = Annotated[
    AttributionDeterminationOutcome
    | AuthorIdentityResolutionOutcome
    | MembershipVerificationOutcome
    | EvidenceCollectionOutcome
    | ClassifierDisagreementOutcome,
    Field(discriminator="outcome_type"),
]


class AttributionEvidencePacket(_StrictContractModel):
    """Replayable aggregate of evidence and an optional attribution decision."""

    contract_version: Literal["ac-attribution-skill-v0.1"] = (
        ATTRIBUTION_SKILL_CONTRACT_VERSION
    )
    packet_id: str = Field(min_length=1, max_length=200)
    paper_id: str = Field(min_length=1, max_length=200)
    paper_snapshot_id: str = Field(min_length=1, max_length=200)
    generated_at: AwareDatetime
    evidence: list[AuditableAttributionEvidence] = Field(default_factory=list)
    decision: AttributionDecisionResult | None = None

    @model_validator(mode="after")
    def validate_evidence_references(self) -> "AttributionEvidencePacket":
        evidence_by_id = {item.evidence_id: item for item in self.evidence}
        if len(evidence_by_id) != len(self.evidence):
            raise ValueError("evidence ids must be unique within a packet")
        if self.decision is None:
            return self

        supporting = set(self.decision.supporting_evidence_ids)
        contradicting = set(self.decision.contradicting_evidence_ids)
        missing = (supporting | contradicting) - evidence_by_id.keys()
        if missing:
            raise ValueError(
                f"decision references evidence ids missing from packet: {sorted(missing)}"
            )
        wrong_support = {
            evidence_id
            for evidence_id in supporting
            if evidence_by_id[evidence_id].polarity != "supporting"
        }
        wrong_contradiction = {
            evidence_id
            for evidence_id in contradicting
            if evidence_by_id[evidence_id].polarity != "contradicting"
        }
        if wrong_support or wrong_contradiction:
            raise ValueError(
                "decision evidence references must match evidence polarity"
            )
        return self


class AttributionSkillInvocation(_StrictContractModel):
    """Self-describing execution envelope for one read-only attribution Skill."""

    contract_version: Literal["ac-attribution-skill-v0.1"] = (
        ATTRIBUTION_SKILL_CONTRACT_VERSION
    )
    invocation_id: str = Field(min_length=1, max_length=200)
    skill_name: AttributionReadSkillName
    skill_version: str = Field(min_length=1, max_length=100)
    policy_version: str = Field(min_length=1, max_length=100)
    status: AttributionSkillInvocationStatus
    paper_id: str = Field(min_length=1, max_length=200)
    input_snapshot_id: str = Field(min_length=1, max_length=200)
    input_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    invocation_reason: str = Field(min_length=1, max_length=1000)
    budget: AttributionInvocationBudget = Field(
        default_factory=AttributionInvocationBudget
    )
    started_at: AwareDatetime
    completed_at: AwareDatetime | None = None
    output_packet: AttributionEvidencePacket | None = None
    skill_outcome: AttributionSkillOutcome | None = None
    failure: AttributionFailure | None = None
    cost: AttributionCostSummary = Field(default_factory=AttributionCostSummary)
    resolution_path: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_invocation(self) -> "AttributionSkillInvocation":
        terminal = self.status != "in_progress"
        if terminal and self.completed_at is None:
            raise ValueError("terminal invocations must include completed_at")
        if not terminal and self.completed_at is not None:
            raise ValueError("in-progress invocations must not include completed_at")
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("completed_at must not be earlier than started_at")

        if self.status in {"succeeded", "review_required"}:
            if self.output_packet is None:
                raise ValueError(
                    "successful or review-required invocations need an output packet"
                )
            if self.failure is not None:
                raise ValueError(
                    "successful or review-required invocations must not include a failure"
                )
            if self.skill_outcome is None:
                raise ValueError(
                    "successful or review-required invocations need a typed skill outcome"
                )
        if self.status == "in_progress" and (
            self.output_packet is not None
            or self.skill_outcome is not None
            or self.failure is not None
        ):
            raise ValueError(
                "in-progress invocations must not include output or failure"
            )
        if self.status in {"failed", "budget_exhausted"} and self.failure is None:
            raise ValueError("failed invocations must include a failure")
        if (
            self.status in {"failed", "budget_exhausted"}
            and self.skill_outcome is not None
        ):
            raise ValueError("failed invocations must not carry a skill outcome")
        if (
            self.status in {"failed", "budget_exhausted"}
            and self.output_packet is not None
            and self.output_packet.decision is not None
        ):
            raise ValueError(
                "failed invocations may only carry a partial packet without a decision"
            )
        if (
            self.status == "budget_exhausted"
            and self.failure is not None
            and self.failure.category != "budget_exhausted"
        ):
            raise ValueError(
                "budget-exhausted invocation must use budget_exhausted failure"
            )
        if self.status == "review_required":
            decision = self.output_packet.decision if self.output_packet else None
            if decision is None or decision.decision != "REVIEW_REQUIRED":
                raise ValueError(
                    "review-required invocation must carry a REVIEW_REQUIRED decision"
                )
        if (
            self.status == "succeeded"
            and self.skill_name == "determine_ac_paper_attribution"
            and (
                self.output_packet is None
                or self.output_packet.decision is None
                or self.output_packet.decision.decision == "REVIEW_REQUIRED"
            )
        ):
            raise ValueError(
                "successful determine invocation must carry a final attribution decision"
            )

        expected_outcome_type = {
            "determine_ac_paper_attribution": "attribution_determination",
            "resolve_ambiguous_author_identity": "author_identity_resolution",
            "verify_membership_at_publication_time": "membership_verification",
            "collect_auditable_attribution_evidence": "evidence_collection",
            "adjudicate_classifier_disagreement": "classifier_disagreement",
        }[self.skill_name]
        if (
            self.skill_outcome is not None
            and self.skill_outcome.outcome_type != expected_outcome_type
        ):
            raise ValueError("skill outcome type must match skill_name")
        if (
            isinstance(
                self.skill_outcome,
                AttributionDeterminationOutcome,
            )
            and self.output_packet is not None
            and self.output_packet.decision is not None
            and self.skill_outcome.decision != self.output_packet.decision.decision
        ):
            raise ValueError("attribution outcome must match the packet decision")

        if self.output_packet is not None:
            if self.output_packet.paper_id != self.paper_id:
                raise ValueError(
                    "output packet paper_id must match invocation paper_id"
                )
            if self.output_packet.paper_snapshot_id != self.input_snapshot_id:
                raise ValueError(
                    "output packet snapshot must match invocation input snapshot"
                )
            if (
                self.output_packet.decision is not None
                and self.output_packet.decision.policy_version != self.policy_version
            ):
                raise ValueError(
                    "decision policy_version must match invocation policy_version"
                )
        return self
