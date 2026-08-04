from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from app.attribution_skill_contract import (
    AttributionFailure,
    AttributionDeterminationOutcome,
    AttributionDecisionResult,
    AttributionEvidencePacket,
    AttributionSkillInvocation,
    EvidenceCollectionOutcome,
    AuditableAttributionEvidence,
    EvidenceSourceProvenance,
    EvidenceTemporalValidity,
)


def _evidence(evidence_id: str, polarity: str) -> AuditableAttributionEvidence:
    return AuditableAttributionEvidence(
        evidence_id=evidence_id,
        evidence_type="membership",
        polarity=polarity,
        claim="The author had a documented AC relationship at publication time.",
        confidence=0.9,
        provenance=EvidenceSourceProvenance(
            provider="ac_membership_registry",
            source_record_id="membership-123",
            content_hash="0123456789abcdef",
        ),
        temporal_validity=EvidenceTemporalValidity(
            status="valid",
            valid_from=date(2022, 1, 1),
            valid_to=date(2024, 12, 31),
            basis="Registry membership interval",
        ),
    )


def test_packet_keeps_attribution_and_relevance_as_independent_axes():
    packet = AttributionEvidencePacket(
        packet_id="packet-1",
        paper_id="paper-1",
        paper_snapshot_id="snapshot-1",
        generated_at=datetime.now(UTC),
        evidence=[_evidence("e-support", "supporting")],
        decision=AttributionDecisionResult(
            decision="ATTRIBUTED",
            relevance_label="ADJACENT",
            confidence=0.9,
            authority="machine_provisional",
            policy_version="policy-v1",
            supporting_evidence_ids=["e-support"],
        ),
    )

    assert packet.decision.decision == "ATTRIBUTED"
    assert packet.decision.relevance_label == "ADJACENT"


def test_review_required_decision_requires_recommended_action():
    with pytest.raises(ValidationError, match="recommended review action"):
        AttributionDecisionResult(
            decision="REVIEW_REQUIRED",
            confidence=0.4,
            authority="machine_provisional",
            policy_version="policy-v1",
        )


def test_packet_rejects_missing_evidence_reference():
    with pytest.raises(ValidationError, match="missing from packet"):
        AttributionEvidencePacket(
            packet_id="packet-1",
            paper_id="paper-1",
            paper_snapshot_id="snapshot-1",
            generated_at=datetime.now(UTC),
            decision=AttributionDecisionResult(
                decision="ATTRIBUTED",
                confidence=0.8,
                authority="machine_provisional",
                policy_version="policy-v1",
                supporting_evidence_ids=["missing"],
            ),
        )


def test_packet_rejects_reference_with_wrong_polarity():
    with pytest.raises(ValidationError, match="must match evidence polarity"):
        AttributionEvidencePacket(
            packet_id="packet-1",
            paper_id="paper-1",
            paper_snapshot_id="snapshot-1",
            generated_at=datetime.now(UTC),
            evidence=[_evidence("e-negative", "contradicting")],
            decision=AttributionDecisionResult(
                decision="NOT_ATTRIBUTED",
                confidence=0.8,
                authority="machine_provisional",
                policy_version="policy-v1",
                supporting_evidence_ids=["e-negative"],
            ),
        )


def test_packet_rejects_duplicate_evidence_ids():
    with pytest.raises(ValidationError, match="evidence ids must be unique"):
        AttributionEvidencePacket(
            packet_id="packet-1",
            paper_id="paper-1",
            paper_snapshot_id="snapshot-1",
            generated_at=datetime.now(UTC),
            evidence=[
                _evidence("duplicate", "supporting"),
                _evidence("duplicate", "supporting"),
            ],
        )


def test_temporal_validity_rejects_reversed_interval():
    with pytest.raises(ValidationError, match="valid_from"):
        EvidenceTemporalValidity(
            status="conflicting",
            valid_from=date(2024, 1, 1),
            valid_to=date(2023, 1, 1),
        )


def test_packet_requires_timezone_aware_generation_time():
    with pytest.raises(ValidationError, match="timezone"):
        AttributionEvidencePacket(
            packet_id="packet-1",
            paper_id="paper-1",
            paper_snapshot_id="snapshot-1",
            generated_at=datetime(2024, 1, 1),
        )


def _packet(decision: AttributionDecisionResult | None = None):
    return AttributionEvidencePacket(
        packet_id="packet-1",
        paper_id="paper-1",
        paper_snapshot_id="snapshot-1",
        generated_at=datetime.now(UTC),
        decision=decision,
    )


def test_invocation_envelope_identifies_skill_input_and_budget():
    now = datetime.now(UTC)
    invocation = AttributionSkillInvocation(
        invocation_id="invocation-1",
        skill_name="collect_auditable_attribution_evidence",
        skill_version="0.1.0",
        policy_version="policy-v1",
        status="succeeded",
        paper_id="paper-1",
        input_snapshot_id="snapshot-1",
        input_content_hash="0" * 64,
        invocation_reason="Collect the evidence packet for attribution.",
        budget={"max_retrieval_api_calls": 3, "max_model_calls": 1},
        started_at=now,
        completed_at=now,
        output_packet=_packet(),
        skill_outcome=EvidenceCollectionOutcome(
            outcome_type="evidence_collection",
            evidence_count=0,
            supporting_count=0,
            contradicting_count=0,
        ),
    )

    assert invocation.skill_name == "collect_auditable_attribution_evidence"
    assert invocation.budget.max_model_calls == 1


def test_review_invocation_requires_matching_review_decision():
    now = datetime.now(UTC)
    with pytest.raises(ValidationError, match="REVIEW_REQUIRED decision"):
        AttributionSkillInvocation(
            invocation_id="invocation-1",
            skill_name="determine_ac_paper_attribution",
            skill_version="0.1.0",
            policy_version="policy-v1",
            status="review_required",
            paper_id="paper-1",
            input_snapshot_id="snapshot-1",
            input_content_hash="0" * 64,
            invocation_reason="Determine attribution.",
            started_at=now,
            completed_at=now,
            output_packet=_packet(),
            skill_outcome=AttributionDeterminationOutcome(
                outcome_type="attribution_determination",
                decision="REVIEW_REQUIRED",
            ),
        )


def test_failed_invocation_requires_failure():
    now = datetime.now(UTC)
    with pytest.raises(ValidationError, match="must include a failure"):
        AttributionSkillInvocation(
            invocation_id="invocation-1",
            skill_name="resolve_ambiguous_author_identity",
            skill_version="0.1.0",
            policy_version="policy-v1",
            status="failed",
            paper_id="paper-1",
            input_snapshot_id="snapshot-1",
            input_content_hash="0" * 64,
            invocation_reason="Resolve an ambiguous author.",
            started_at=now,
            completed_at=now,
        )

    failure = AttributionFailure(
        stage="identity",
        category="ambiguous_author_identity",
    )
    assert failure.retryable is False


def test_failed_invocation_cannot_carry_a_final_decision():
    now = datetime.now(UTC)
    final_decision = AttributionDecisionResult(
        decision="NOT_ATTRIBUTED",
        confidence=0.9,
        authority="machine_provisional",
        policy_version="policy-v1",
    )

    with pytest.raises(ValidationError, match="partial packet without a decision"):
        AttributionSkillInvocation(
            invocation_id="invocation-1",
            skill_name="determine_ac_paper_attribution",
            skill_version="0.1.0",
            policy_version="policy-v1",
            status="failed",
            paper_id="paper-1",
            input_snapshot_id="snapshot-1",
            input_content_hash="0" * 64,
            invocation_reason="Determine attribution.",
            started_at=now,
            completed_at=now,
            output_packet=_packet(final_decision),
            failure=AttributionFailure(
                stage="system",
                category="retry_exhausted",
            ),
        )
