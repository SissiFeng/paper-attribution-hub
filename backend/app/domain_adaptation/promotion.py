"""Fail-closed gates for knowledge, skill, and weight promotion."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.domain_adaptation.models import DomainModel
from app.domain_adaptation.package_graph import PackageReference


PromotionKind = Literal[
    "shared_knowledge",
    "scientific_skill",
    "weight_consolidation",
]
TargetLayer = Literal[
    "shared_knowledge",
    "scientific_core_tasks",
    "scientific_base_weights",
]
PromotionBasis = Literal["reviewed_corpus", "experimental_feedback"]


class PromotionMetrics(DomainModel):
    gold_precision: float | None = Field(default=None, ge=0, le=1)
    evidence_validity: float | None = Field(default=None, ge=0, le=1)
    rag_answer_f1: float | None = Field(default=None, ge=0, le=1)
    retrieval_recall: float | None = Field(default=None, ge=0, le=1)
    evaluated_question_count: int = Field(default=0, ge=0)
    domain_eval_deltas: dict[str, float] = Field(default_factory=dict)
    negative_transfer_failure_count: int = Field(default=0, ge=0)
    replay_evaluation_count: int = Field(default=0, ge=0)
    general_capability_retention: float | None = Field(
        default=None, ge=0, le=1
    )
    experimental_feedback_bundle_count: int = Field(default=0, ge=0)
    belief_update_task_count: int = Field(default=0, ge=0)
    belief_update_accuracy: float | None = Field(default=None, ge=0, le=1)
    belief_update_evidence_validity: float | None = Field(
        default=None, ge=0, le=1
    )


class PromotionCandidate(DomainModel):
    schema_version: str = "domain-promotion-candidate-v0.2"
    promotion_id: str = Field(min_length=1)
    promotion_kind: PromotionKind
    promotion_basis: PromotionBasis = "reviewed_corpus"
    target_layer: TargetLayer
    source_package: PackageReference
    target_package: PackageReference
    source_record_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    source_feedback_bundle_ids: list[str] = Field(default_factory=list)
    reviewed_gold_ids: list[str] = Field(default_factory=list)
    supporting_packages: list[PackageReference] = Field(default_factory=list)
    human_reviewed: bool = False
    deterministic_rebuild_verified: bool = False
    adapter_artifact_sha256: str | None = None
    metrics: PromotionMetrics = Field(default_factory=PromotionMetrics)


class PromotionPolicy(DomainModel):
    schema_version: str = "domain-promotion-policy-v0.2"
    min_gold_precision: float = Field(default=0.85, ge=0, le=1)
    min_evidence_validity: float = Field(default=1.0, ge=0, le=1)
    min_rag_answer_f1: float = Field(default=0.7, ge=0, le=1)
    min_retrieval_recall: float = Field(default=0.8, ge=0, le=1)
    min_evaluated_questions: int = Field(default=30, ge=1)
    min_cross_domain_packages: int = Field(default=2, ge=2)
    max_allowed_negative_delta: float = Field(default=-0.02, le=0)
    min_replay_evaluations: int = Field(default=100, ge=1)
    min_general_capability_retention: float = Field(
        default=0.98, ge=0, le=1
    )
    min_experimental_feedback_bundles: int = Field(default=1, ge=1)
    min_belief_update_tasks: int = Field(default=20, ge=1)
    min_belief_update_accuracy: float = Field(default=0.8, ge=0, le=1)
    min_belief_update_evidence_validity: float = Field(
        default=1.0, ge=0, le=1
    )


class PromotionDecision(DomainModel):
    schema_version: str = "domain-promotion-decision-v0.2"
    promotion_id: str
    eligible_for_human_approval: bool
    failed_gates: list[str]
    evaluated_metrics: PromotionMetrics
    claims_boundary: str = (
        "Gate eligibility does not approve or apply a promotion. A separate "
        "human decision and versioned release are required."
    )


def _below(value: float | None, threshold: float) -> bool:
    return value is None or value < threshold


def evaluate_promotion(
    candidate: PromotionCandidate, policy: PromotionPolicy
) -> PromotionDecision:
    """Evaluate promotion evidence without mutating any package or model."""
    failed: list[str] = []
    expected_layer: dict[PromotionKind, TargetLayer] = {
        "shared_knowledge": "shared_knowledge",
        "scientific_skill": "scientific_core_tasks",
        "weight_consolidation": "scientific_base_weights",
    }
    if candidate.target_layer != expected_layer[candidate.promotion_kind]:
        failed.append("target_layer")
    if not candidate.human_reviewed:
        failed.append("human_review")
    if not candidate.source_record_ids or not candidate.evidence_ids:
        failed.append("provenance")
    if not candidate.reviewed_gold_ids:
        failed.append("reviewed_gold")
    if not candidate.deterministic_rebuild_verified:
        failed.append("deterministic_rebuild")
    if _below(candidate.metrics.gold_precision, policy.min_gold_precision):
        failed.append("gold_precision")
    if _below(
        candidate.metrics.evidence_validity, policy.min_evidence_validity
    ):
        failed.append("evidence_validity")
    if _below(candidate.metrics.rag_answer_f1, policy.min_rag_answer_f1):
        failed.append("rag_utility")
    if _below(
        candidate.metrics.retrieval_recall, policy.min_retrieval_recall
    ):
        failed.append("retrieval_coverage")
    if candidate.metrics.evaluated_question_count < policy.min_evaluated_questions:
        failed.append("evaluation_size")

    if candidate.promotion_basis == "experimental_feedback":
        if not candidate.source_feedback_bundle_ids:
            failed.append("experimental_feedback_provenance")
        if (
            candidate.metrics.experimental_feedback_bundle_count
            < policy.min_experimental_feedback_bundles
        ):
            failed.append("experimental_feedback_coverage")
        if (
            candidate.metrics.belief_update_task_count
            < policy.min_belief_update_tasks
        ):
            failed.append("belief_update_evaluation_size")
        if _below(
            candidate.metrics.belief_update_accuracy,
            policy.min_belief_update_accuracy,
        ):
            failed.append("belief_update_accuracy")
        if _below(
            candidate.metrics.belief_update_evidence_validity,
            policy.min_belief_update_evidence_validity,
        ):
            failed.append("belief_update_evidence_validity")

    supporting_coordinates = {
        item.coordinate for item in candidate.supporting_packages
    }
    if (
        candidate.promotion_kind
        in {"scientific_skill", "weight_consolidation"}
        and len(supporting_coordinates) < policy.min_cross_domain_packages
    ):
        failed.append("cross_domain_support")
    if (
        candidate.metrics.negative_transfer_failure_count > 0
        or any(
            delta < policy.max_allowed_negative_delta
            for delta in candidate.metrics.domain_eval_deltas.values()
        )
    ):
        failed.append("negative_transfer")

    if candidate.promotion_kind == "weight_consolidation":
        artifact = candidate.adapter_artifact_sha256 or ""
        if len(artifact) != 64 or any(
            character not in "0123456789abcdef" for character in artifact.casefold()
        ):
            failed.append("adapter_artifact")
        if (
            candidate.metrics.replay_evaluation_count
            < policy.min_replay_evaluations
        ):
            failed.append("replay_evaluation")
        if _below(
            candidate.metrics.general_capability_retention,
            policy.min_general_capability_retention,
        ):
            failed.append("general_retention")

    return PromotionDecision(
        promotion_id=candidate.promotion_id,
        eligible_for_human_approval=not failed,
        failed_gates=failed,
        evaluated_metrics=candidate.metrics,
    )
