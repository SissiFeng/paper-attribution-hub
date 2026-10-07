"""Fail-closed evaluation contracts for a cross-domain NMI study.

Teacher consensus remains silver supervision. Scientific utility metrics require
an external, content-addressed truth source and are never inferred from model
agreement.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

from pydantic import Field, model_validator

from app.domain_adaptation.models import DomainModel
from app.domain_adaptation.package_graph import PackageReference


ExternalTruthSourceType = Literal[
    "structured_supplement",
    "curated_database",
    "experimental_measurement",
    "reviewed_question",
]
BeliefUpdateAction = Literal["revise", "retain", "abstain"]


class ScientificUtilityObservation(DomainModel):
    """One externally scored answer, including abstention and citation behavior."""

    schema_version: str = "domain-scientific-utility-observation-v0.1"
    task_id: str = Field(min_length=1)
    domain_package: PackageReference
    system_id: str = Field(min_length=1)
    configuration_id: str = Field(min_length=1)
    truth_source_type: ExternalTruthSourceType
    truth_source_id: str = Field(min_length=1)
    truth_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    answered: bool
    correct: bool
    citation_valid: bool
    abstain_expected: bool
    abstained: bool

    @model_validator(mode="after")
    def validate_outcome_state(self) -> "ScientificUtilityObservation":
        if self.answered == self.abstained:
            raise ValueError("Exactly one of answered and abstained must be true")
        if not self.answered and (self.correct or self.citation_valid):
            raise ValueError("Abstained observations cannot be correct or cited")
        return self


class ScientificBeliefUpdateObservation(DomainModel):
    """One belief revision scored against content-addressed experiment evidence."""

    schema_version: str = "domain-scientific-belief-update-observation-v0.1"
    task_id: str = Field(min_length=1)
    domain_package: PackageReference
    system_id: str = Field(min_length=1)
    configuration_id: str = Field(min_length=1)
    prior_claim_id: str = Field(min_length=1)
    feedback_bundle_id: str = Field(min_length=1)
    truth_source_type: ExternalTruthSourceType
    truth_source_id: str = Field(min_length=1)
    truth_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prior_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    updated_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_action: BeliefUpdateAction
    observed_action: BeliefUpdateAction
    evidence_citation_valid: bool

    @model_validator(mode="after")
    def require_experimental_truth(self) -> "ScientificBeliefUpdateObservation":
        if self.truth_source_type != "experimental_measurement":
            raise ValueError(
                "Belief update utility requires experimental_measurement truth"
            )
        return self


class ScientificBeliefUpdateReport(DomainModel):
    schema_version: str = "domain-scientific-belief-update-report-v0.1"
    domain_package: PackageReference
    system_id: str
    configuration_id: str
    task_count: int = Field(ge=0)
    update_accuracy: float = Field(ge=0, le=1)
    evidence_validity: float = Field(ge=0, le=1)
    revision_recall: float | None = Field(default=None, ge=0, le=1)
    retention_specificity: float | None = Field(default=None, ge=0, le=1)
    abstention_accuracy: float | None = Field(default=None, ge=0, le=1)
    action_counts: dict[str, int]
    feedback_bundle_count: int = Field(ge=1)
    claims_boundary: str = (
        "This report measures observable evidence-conditioned belief updates. "
        "It does not expose or validate a model's hidden chain of thought."
    )


class ScientificUtilityReport(DomainModel):
    schema_version: str = "domain-scientific-utility-report-v0.1"
    domain_package: PackageReference
    system_id: str
    configuration_id: str
    task_count: int = Field(ge=0)
    answer_coverage: float = Field(ge=0, le=1)
    conditional_accuracy: float | None = Field(default=None, ge=0, le=1)
    evidence_validity: float | None = Field(default=None, ge=0, le=1)
    abstain_accuracy: float = Field(ge=0, le=1)
    selective_error: float | None = Field(default=None, ge=0, le=1)
    truth_source_counts: dict[str, int]
    claims_boundary: str = (
        "Metrics use content-addressed external truth. Teacher or model consensus "
        "is silver supervision and is not accepted as scientific truth."
    )


class UtilityAblationComparison(DomainModel):
    schema_version: str = "domain-scientific-utility-ablation-v0.1"
    baseline_report: ScientificUtilityReport
    candidate_report: ScientificUtilityReport
    paired_task_count: int = Field(ge=1)
    conditional_accuracy_delta: float | None = None
    evidence_validity_delta: float | None = None
    answer_coverage_delta: float
    abstain_accuracy_delta: float
    claims_boundary: str = (
        "Deltas are paired descriptive effects for the recorded tasks and do "
        "not establish causal or cross-domain generalization."
    )


class CrossDomainTransferComparison(DomainModel):
    schema_version: str = "domain-cross-transfer-comparison-v0.1"
    source_adapter: PackageReference
    target_package: PackageReference
    baseline_configuration_id: str
    candidate_configuration_id: str
    paired_task_count: int = Field(ge=1)
    conditional_accuracy_delta: float | None = None
    evidence_validity_delta: float | None = None
    negative_transfer_detected: bool
    max_allowed_negative_delta: float = Field(le=0)
    claims_boundary: str = (
        "This is a paired target-domain interference test. A non-negative "
        "result does not prove transferable scientific knowledge."
    )


def _require_one_evaluation_group(
    observations: list[ScientificUtilityObservation],
) -> tuple[PackageReference, str, str]:
    if not observations:
        raise ValueError("Scientific utility evaluation requires observations")
    groups = {
        (
            item.domain_package.coordinate,
            item.system_id,
            item.configuration_id,
        )
        for item in observations
    }
    if len(groups) != 1:
        raise ValueError("Utility observations must belong to one evaluation group")
    task_ids = [item.task_id for item in observations]
    if len(task_ids) != len(set(task_ids)):
        raise ValueError("Utility observations contain duplicate task IDs")
    first = observations[0]
    return first.domain_package, first.system_id, first.configuration_id


def evaluate_scientific_utility(
    observations: list[ScientificUtilityObservation],
) -> ScientificUtilityReport:
    """Score external scientific tasks without treating consensus as truth."""
    package, system_id, configuration_id = _require_one_evaluation_group(
        observations
    )
    answered = [item for item in observations if item.answered]
    truth_source_counts: dict[str, int] = defaultdict(int)
    for item in observations:
        truth_source_counts[item.truth_source_type] += 1
    conditional_accuracy = (
        sum(item.correct for item in answered) / len(answered) if answered else None
    )
    evidence_validity = (
        sum(item.citation_valid for item in answered) / len(answered)
        if answered
        else None
    )
    return ScientificUtilityReport(
        domain_package=package,
        system_id=system_id,
        configuration_id=configuration_id,
        task_count=len(observations),
        answer_coverage=len(answered) / len(observations),
        conditional_accuracy=conditional_accuracy,
        evidence_validity=evidence_validity,
        abstain_accuracy=sum(
            item.abstained == item.abstain_expected for item in observations
        )
        / len(observations),
        selective_error=(
            sum(not item.correct for item in answered) / len(answered)
            if answered
            else None
        ),
        truth_source_counts=dict(sorted(truth_source_counts.items())),
    )


def evaluate_belief_update_utility(
    observations: list[ScientificBeliefUpdateObservation],
) -> ScientificBeliefUpdateReport:
    """Score whether conclusions track new experimental evidence."""
    if not observations:
        raise ValueError("Belief update evaluation requires observations")
    groups = {
        (
            item.domain_package.coordinate,
            item.system_id,
            item.configuration_id,
        )
        for item in observations
    }
    if len(groups) != 1:
        raise ValueError("Belief update observations require one evaluation group")
    task_ids = [item.task_id for item in observations]
    if len(task_ids) != len(set(task_ids)):
        raise ValueError("Belief update observations contain duplicate task IDs")

    def action_accuracy(action: BeliefUpdateAction) -> float | None:
        expected = [item for item in observations if item.expected_action == action]
        if not expected:
            return None
        return sum(item.observed_action == action for item in expected) / len(expected)

    first = observations[0]
    action_counts: dict[str, int] = defaultdict(int)
    for item in observations:
        action_counts[item.expected_action] += 1
    return ScientificBeliefUpdateReport(
        domain_package=first.domain_package,
        system_id=first.system_id,
        configuration_id=first.configuration_id,
        task_count=len(observations),
        update_accuracy=(
            sum(item.observed_action == item.expected_action for item in observations)
            / len(observations)
        ),
        evidence_validity=(
            sum(item.evidence_citation_valid for item in observations)
            / len(observations)
        ),
        revision_recall=action_accuracy("revise"),
        retention_specificity=action_accuracy("retain"),
        abstention_accuracy=action_accuracy("abstain"),
        action_counts=dict(sorted(action_counts.items())),
        feedback_bundle_count=len(
            {item.feedback_bundle_id for item in observations}
        ),
    )


def compare_utility_configurations(
    observations: list[ScientificUtilityObservation],
    *,
    baseline_configuration_id: str,
    candidate_configuration_id: str,
) -> UtilityAblationComparison:
    """Compare two configurations on exactly the same externally scored tasks."""
    grouped: dict[str, list[ScientificUtilityObservation]] = defaultdict(list)
    for item in observations:
        if item.configuration_id in {
            baseline_configuration_id,
            candidate_configuration_id,
        }:
            grouped[item.configuration_id].append(item)
    baseline = grouped.get(baseline_configuration_id, [])
    candidate = grouped.get(candidate_configuration_id, [])
    baseline_keys = {
        (item.domain_package.coordinate, item.system_id, item.task_id)
        for item in baseline
    }
    candidate_keys = {
        (item.domain_package.coordinate, item.system_id, item.task_id)
        for item in candidate
    }
    if not baseline_keys or baseline_keys != candidate_keys:
        raise ValueError("Ablation configurations require identical paired tasks")
    baseline_report = evaluate_scientific_utility(baseline)
    candidate_report = evaluate_scientific_utility(candidate)

    def delta(candidate_value: float | None, baseline_value: float | None):
        if candidate_value is None or baseline_value is None:
            return None
        return candidate_value - baseline_value

    return UtilityAblationComparison(
        baseline_report=baseline_report,
        candidate_report=candidate_report,
        paired_task_count=len(baseline_keys),
        conditional_accuracy_delta=delta(
            candidate_report.conditional_accuracy,
            baseline_report.conditional_accuracy,
        ),
        evidence_validity_delta=delta(
            candidate_report.evidence_validity,
            baseline_report.evidence_validity,
        ),
        answer_coverage_delta=(
            candidate_report.answer_coverage - baseline_report.answer_coverage
        ),
        abstain_accuracy_delta=(
            candidate_report.abstain_accuracy - baseline_report.abstain_accuracy
        ),
    )


def compare_cross_domain_transfer(
    observations: list[ScientificUtilityObservation],
    *,
    source_adapter: PackageReference,
    baseline_configuration_id: str,
    candidate_configuration_id: str,
    max_allowed_negative_delta: float = -0.02,
) -> CrossDomainTransferComparison:
    """Measure whether one domain adapter harms a different target domain."""
    if max_allowed_negative_delta > 0:
        raise ValueError("Allowed negative-transfer delta must be non-positive")
    comparison = compare_utility_configurations(
        observations,
        baseline_configuration_id=baseline_configuration_id,
        candidate_configuration_id=candidate_configuration_id,
    )
    target_package = comparison.candidate_report.domain_package
    if source_adapter.coordinate == target_package.coordinate:
        raise ValueError("Cross-domain transfer requires distinct source and target")
    accuracy_delta = comparison.conditional_accuracy_delta
    evidence_delta = comparison.evidence_validity_delta
    negative_transfer = any(
        value is not None and value < max_allowed_negative_delta
        for value in (accuracy_delta, evidence_delta)
    )
    return CrossDomainTransferComparison(
        source_adapter=source_adapter,
        target_package=target_package,
        baseline_configuration_id=baseline_configuration_id,
        candidate_configuration_id=candidate_configuration_id,
        paired_task_count=comparison.paired_task_count,
        conditional_accuracy_delta=accuracy_delta,
        evidence_validity_delta=evidence_delta,
        negative_transfer_detected=negative_transfer,
        max_allowed_negative_delta=max_allowed_negative_delta,
    )


class NmiDomainEvidence(DomainModel):
    schema_version: str = "domain-nmi-evidence-v0.1"
    domain: str = Field(min_length=1)
    package: PackageReference
    total_paper_count: int = Field(ge=1)
    primary_paper_count: int = Field(ge=0)
    teacher_evaluated_paper_count: int = Field(ge=0)
    independent_model_family_count: int = Field(ge=0)
    occurrence_slot_count: int = Field(ge=0)
    perturbation_tested_count: int = Field(ge=0)
    tier_a_silver_count: int = Field(ge=0)
    prompt_configuration_count: int = Field(ge=0)
    negative_control_count: int = Field(ge=0)
    deterministic_rebuild_verified: bool
    external_utility: ScientificUtilityReport | None = None

    @model_validator(mode="after")
    def validate_counts(self) -> "NmiDomainEvidence":
        if self.primary_paper_count > self.total_paper_count:
            raise ValueError("Primary paper count exceeds total paper count")
        if self.teacher_evaluated_paper_count > self.total_paper_count:
            raise ValueError("Teacher-evaluated paper count exceeds total paper count")
        if self.perturbation_tested_count > self.occurrence_slot_count:
            raise ValueError("Perturbation count exceeds occurrence slot count")
        return self


class NmiStudyPolicy(DomainModel):
    schema_version: str = "domain-nmi-study-policy-v0.1"
    min_domains: int = Field(default=2, ge=2)
    min_primary_papers_per_domain: int = Field(default=20, ge=1)
    min_teacher_paper_coverage: float = Field(default=0.8, ge=0, le=1)
    min_independent_model_families: int = Field(default=3, ge=2)
    min_occurrence_slots: int = Field(default=100, ge=1)
    min_perturbation_tests: int = Field(default=100, ge=1)
    min_tier_a_silver: int = Field(default=50, ge=1)
    min_prompt_configurations: int = Field(default=2, ge=2)
    min_negative_controls: int = Field(default=30, ge=1)
    min_external_tasks: int = Field(default=30, ge=1)
    min_external_accuracy: float = Field(default=0.8, ge=0, le=1)
    min_external_evidence_validity: float = Field(default=0.95, ge=0, le=1)
    min_cross_domain_transfer_tasks: int = Field(default=30, ge=1)
    max_allowed_negative_transfer_delta: float = Field(default=-0.02, le=0)


class NmiDomainDecision(DomainModel):
    package: PackageReference
    meets_evidence_policy: bool
    failed_gates: list[str]


class NmiReadinessReport(DomainModel):
    schema_version: str = "domain-nmi-readiness-report-v0.1"
    meets_evidence_policy: bool
    failed_global_gates: list[str]
    domain_decisions: list[NmiDomainDecision]
    transfer_comparisons: list[CrossDomainTransferComparison]
    policy: NmiStudyPolicy
    claims_boundary: str = (
        "This report checks engineering evidence completeness against a declared "
        "policy. It does not establish scientific validity or publication acceptance."
    )


class NmiStudyInput(DomainModel):
    schema_version: str = "domain-nmi-study-input-v0.1"
    policy: NmiStudyPolicy = Field(default_factory=NmiStudyPolicy)
    domains: list[NmiDomainEvidence]
    transfer_comparisons: list[CrossDomainTransferComparison] = Field(
        default_factory=list
    )


def evaluate_nmi_readiness(
    domains: list[NmiDomainEvidence],
    policy: NmiStudyPolicy,
    *,
    transfer_comparisons: list[CrossDomainTransferComparison] | None = None,
) -> NmiReadinessReport:
    """Report missing publication evidence without relaxing absent metrics."""
    coordinates = [item.package.coordinate for item in domains]
    if len(coordinates) != len(set(coordinates)):
        raise ValueError("NMI evidence contains duplicate package coordinates")
    failed_global: list[str] = []
    if len({item.domain for item in domains}) < policy.min_domains:
        failed_global.append("cross_domain_count")
    transfers = transfer_comparisons or []
    package_coordinates = set(coordinates)
    expected_transfer_pairs = {
        (source, target)
        for source in package_coordinates
        for target in package_coordinates
        if source != target
    }
    observed_transfer_pairs: dict[tuple[str, str], CrossDomainTransferComparison] = {}
    for comparison in transfers:
        pair = (
            comparison.source_adapter.coordinate,
            comparison.target_package.coordinate,
        )
        if pair[0] not in package_coordinates or pair[1] not in package_coordinates:
            raise ValueError("Cross-domain transfer references an unknown package")
        if pair in observed_transfer_pairs:
            raise ValueError("Duplicate directed cross-domain transfer comparison")
        observed_transfer_pairs[pair] = comparison
    if expected_transfer_pairs and any(
        pair not in observed_transfer_pairs
        or observed_transfer_pairs[pair].paired_task_count
        < policy.min_cross_domain_transfer_tasks
        for pair in expected_transfer_pairs
    ):
        failed_global.append("cross_domain_transfer_coverage")
    if any(
        comparison.negative_transfer_detected
        or any(
            value is not None
            and value < policy.max_allowed_negative_transfer_delta
            for value in (
                comparison.conditional_accuracy_delta,
                comparison.evidence_validity_delta,
            )
        )
        for comparison in transfers
    ):
        failed_global.append("negative_transfer")
    decisions: list[NmiDomainDecision] = []
    for evidence in sorted(domains, key=lambda item: item.package.coordinate):
        failed: list[str] = []
        if evidence.primary_paper_count < policy.min_primary_papers_per_domain:
            failed.append("primary_paper_count")
        if (
            evidence.teacher_evaluated_paper_count / evidence.total_paper_count
            < policy.min_teacher_paper_coverage
        ):
            failed.append("teacher_paper_coverage")
        if (
            evidence.independent_model_family_count
            < policy.min_independent_model_families
        ):
            failed.append("independent_model_families")
        if evidence.occurrence_slot_count < policy.min_occurrence_slots:
            failed.append("occurrence_slot_count")
        if evidence.perturbation_tested_count < policy.min_perturbation_tests:
            failed.append("perturbation_coverage")
        if evidence.tier_a_silver_count < policy.min_tier_a_silver:
            failed.append("tier_a_silver")
        if evidence.prompt_configuration_count < policy.min_prompt_configurations:
            failed.append("prompt_robustness")
        if evidence.negative_control_count < policy.min_negative_controls:
            failed.append("negative_controls")
        utility = evidence.external_utility
        if utility is None or utility.task_count < policy.min_external_tasks:
            failed.append("external_scientific_utility")
        else:
            if (
                utility.conditional_accuracy is None
                or utility.conditional_accuracy < policy.min_external_accuracy
            ):
                failed.append("external_accuracy")
            if (
                utility.evidence_validity is None
                or utility.evidence_validity
                < policy.min_external_evidence_validity
            ):
                failed.append("external_evidence_validity")
        if not evidence.deterministic_rebuild_verified:
            failed.append("deterministic_rebuild")
        decisions.append(
            NmiDomainDecision(
                package=evidence.package,
                meets_evidence_policy=not failed,
                failed_gates=failed,
            )
        )
    return NmiReadinessReport(
        meets_evidence_policy=(
            bool(domains)
            and not failed_global
            and all(item.meets_evidence_policy for item in decisions)
        ),
        failed_global_gates=failed_global,
        domain_decisions=decisions,
        transfer_comparisons=sorted(
            transfers,
            key=lambda item: (
                item.source_adapter.coordinate,
                item.target_package.coordinate,
            ),
        ),
        policy=policy,
    )
