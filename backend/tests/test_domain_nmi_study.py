import pytest
from pydantic import ValidationError


def _observation(
    *,
    task_id: str,
    configuration_id: str,
    correct: bool,
    citation_valid: bool = True,
):
    from app.domain_adaptation.nmi_study import ScientificUtilityObservation
    from app.domain_adaptation.package_graph import PackageReference

    return ScientificUtilityObservation(
        task_id=task_id,
        domain_package=PackageReference(
            package_id="oer-electrocatalysis",
            package_version="0.3.3-pre-review",
        ),
        system_id="paper-knowledge-adapter",
        configuration_id=configuration_id,
        truth_source_type="structured_supplement",
        truth_source_id=f"supplement:{task_id}",
        truth_source_sha256="a" * 64,
        answered=True,
        correct=correct,
        citation_valid=citation_valid,
        abstain_expected=False,
        abstained=False,
    )


def test_scientific_utility_requires_external_non_model_truth():
    from app.domain_adaptation.nmi_study import ScientificUtilityObservation
    from app.domain_adaptation.package_graph import PackageReference

    with pytest.raises(ValidationError):
        ScientificUtilityObservation(
            task_id="q-1",
            domain_package=PackageReference(
                package_id="oer-electrocatalysis",
                package_version="0.3.3-pre-review",
            ),
            system_id="paper-knowledge-adapter",
            configuration_id="consensus",
            truth_source_type="model_consensus",
            truth_source_id="silver:decision-1",
            truth_source_sha256="a" * 64,
            answered=True,
            correct=True,
            citation_valid=True,
            abstain_expected=False,
            abstained=False,
        )


def test_scientific_utility_and_ablation_are_paired_and_auditable():
    from app.domain_adaptation.nmi_study import (
        compare_utility_configurations,
        evaluate_scientific_utility,
    )

    observations = [
        _observation(task_id="q-1", configuration_id="single_teacher", correct=True),
        _observation(task_id="q-2", configuration_id="single_teacher", correct=False),
        _observation(
            task_id="q-1",
            configuration_id="consensus_plus_perturbation",
            correct=True,
        ),
        _observation(
            task_id="q-2",
            configuration_id="consensus_plus_perturbation",
            correct=True,
        ),
    ]

    report = evaluate_scientific_utility(observations[:2])
    assert report.task_count == 2
    assert report.answer_coverage == 1.0
    assert report.conditional_accuracy == 0.5
    assert report.evidence_validity == 1.0
    assert "model consensus" in report.claims_boundary

    comparison = compare_utility_configurations(
        observations,
        baseline_configuration_id="single_teacher",
        candidate_configuration_id="consensus_plus_perturbation",
    )
    assert comparison.paired_task_count == 2
    assert comparison.conditional_accuracy_delta == 0.5
    assert comparison.candidate_report.conditional_accuracy == 1.0


def test_experimental_belief_update_utility_scores_revision_and_retention():
    from app.domain_adaptation.nmi_study import (
        ScientificBeliefUpdateObservation,
        evaluate_belief_update_utility,
    )
    from app.domain_adaptation.package_graph import PackageReference

    package = PackageReference(
        package_id="oer-electrocatalysis",
        package_version="0.4.0",
    )
    observations = [
        ScientificBeliefUpdateObservation(
            task_id="belief-1",
            domain_package=package,
            system_id="paper-knowledge-adapter",
            configuration_id="shared-plus-oer",
            prior_claim_id="claim-1",
            feedback_bundle_id="oer-experimental-feedback@2026.09.03",
            truth_source_type="experimental_measurement",
            truth_source_id="exp-evidence-1",
            truth_source_sha256="a" * 64,
            prior_state_sha256="b" * 64,
            updated_evidence_sha256="c" * 64,
            expected_action="revise",
            observed_action="revise",
            evidence_citation_valid=True,
        ),
        ScientificBeliefUpdateObservation(
            task_id="belief-2",
            domain_package=package,
            system_id="paper-knowledge-adapter",
            configuration_id="shared-plus-oer",
            prior_claim_id="claim-2",
            feedback_bundle_id="oer-experimental-feedback@2026.09.03",
            truth_source_type="experimental_measurement",
            truth_source_id="exp-evidence-2",
            truth_source_sha256="d" * 64,
            prior_state_sha256="e" * 64,
            updated_evidence_sha256="f" * 64,
            expected_action="retain",
            observed_action="revise",
            evidence_citation_valid=False,
        ),
    ]

    report = evaluate_belief_update_utility(observations)

    assert report.task_count == 2
    assert report.update_accuracy == 0.5
    assert report.evidence_validity == 0.5
    assert report.revision_recall == 1.0
    assert report.retention_specificity == 0.0


def test_belief_update_observation_rejects_non_experimental_truth():
    from app.domain_adaptation.nmi_study import ScientificBeliefUpdateObservation
    from app.domain_adaptation.package_graph import PackageReference

    with pytest.raises(ValidationError, match="experimental_measurement"):
        ScientificBeliefUpdateObservation(
            task_id="belief-1",
            domain_package=PackageReference(
                package_id="oer-electrocatalysis",
                package_version="0.4.0",
            ),
            system_id="paper-knowledge-adapter",
            configuration_id="shared-plus-oer",
            prior_claim_id="claim-1",
            feedback_bundle_id="oer-feedback@1.0.0",
            truth_source_type="structured_supplement",
            truth_source_id="supplement-1",
            truth_source_sha256="a" * 64,
            prior_state_sha256="b" * 64,
            updated_evidence_sha256="c" * 64,
            expected_action="revise",
            observed_action="revise",
            evidence_citation_valid=True,
        )


def test_nmi_readiness_fails_closed_on_single_domain_and_missing_utility():
    from app.domain_adaptation.nmi_study import (
        NmiDomainEvidence,
        NmiStudyPolicy,
        evaluate_nmi_readiness,
    )
    from app.domain_adaptation.package_graph import PackageReference

    oer = NmiDomainEvidence(
        domain="oer-electrocatalysis",
        package=PackageReference(
            package_id="oer-electrocatalysis",
            package_version="0.3.3-pre-review",
        ),
        total_paper_count=20,
        primary_paper_count=7,
        teacher_evaluated_paper_count=4,
        independent_model_family_count=3,
        occurrence_slot_count=273,
        perturbation_tested_count=95,
        tier_a_silver_count=63,
        prompt_configuration_count=1,
        negative_control_count=0,
        deterministic_rebuild_verified=True,
        external_utility=None,
    )

    report = evaluate_nmi_readiness([oer], NmiStudyPolicy())
    assert report.meets_evidence_policy is False
    assert "cross_domain_count" in report.failed_global_gates
    assert report.domain_decisions[0].package == oer.package
    assert set(report.domain_decisions[0].failed_gates) >= {
        "primary_paper_count",
        "teacher_paper_coverage",
        "perturbation_coverage",
        "prompt_robustness",
        "negative_controls",
        "external_scientific_utility",
    }
    assert "publication acceptance" in report.claims_boundary


def test_cross_domain_transfer_detects_adapter_interference():
    from app.domain_adaptation.nmi_study import compare_cross_domain_transfer
    from app.domain_adaptation.package_graph import PackageReference

    observations = [
        _observation(task_id="q-1", configuration_id="general_base", correct=True),
        _observation(task_id="q-2", configuration_id="general_base", correct=True),
        _observation(task_id="q-1", configuration_id="with_battery_adapter", correct=True),
        _observation(task_id="q-2", configuration_id="with_battery_adapter", correct=False),
    ]
    comparison = compare_cross_domain_transfer(
        observations,
        source_adapter=PackageReference(
            package_id="battery-electrolyte-optimization",
            package_version="0.1.0-pilot",
        ),
        baseline_configuration_id="general_base",
        candidate_configuration_id="with_battery_adapter",
        max_allowed_negative_delta=-0.02,
    )

    assert comparison.target_package.package_id == "oer-electrocatalysis"
    assert comparison.conditional_accuracy_delta == -0.5
    assert comparison.negative_transfer_detected is True


def test_nmi_readiness_requires_both_directed_cross_domain_tests():
    from app.domain_adaptation.nmi_study import (
        CrossDomainTransferComparison,
        NmiDomainEvidence,
        NmiStudyPolicy,
        ScientificUtilityReport,
        evaluate_nmi_readiness,
    )
    from app.domain_adaptation.package_graph import PackageReference

    def ready_domain(package_id: str):
        package = PackageReference(package_id=package_id, package_version="1.0.0")
        utility = ScientificUtilityReport(
            domain_package=package,
            system_id="paper-knowledge-adapter",
            configuration_id="consensus_plus_perturbation",
            task_count=30,
            answer_coverage=1.0,
            conditional_accuracy=0.9,
            evidence_validity=1.0,
            abstain_accuracy=1.0,
            selective_error=0.1,
            truth_source_counts={"structured_supplement": 30},
        )
        return NmiDomainEvidence(
            domain=package_id,
            package=package,
            total_paper_count=25,
            primary_paper_count=20,
            teacher_evaluated_paper_count=25,
            independent_model_family_count=3,
            occurrence_slot_count=200,
            perturbation_tested_count=150,
            tier_a_silver_count=100,
            prompt_configuration_count=2,
            negative_control_count=30,
            deterministic_rebuild_verified=True,
            external_utility=utility,
        )

    oer = ready_domain("oer-electrocatalysis")
    battery = ready_domain("battery-electrolyte-optimization")
    no_transfer = evaluate_nmi_readiness([oer, battery], NmiStudyPolicy())
    assert no_transfer.failed_global_gates == ["cross_domain_transfer_coverage"]

    def transfer(source, target):
        return CrossDomainTransferComparison(
            source_adapter=source.package,
            target_package=target.package,
            baseline_configuration_id="general_base",
            candidate_configuration_id=f"with_{source.domain}",
            paired_task_count=30,
            conditional_accuracy_delta=0.0,
            evidence_validity_delta=0.0,
            negative_transfer_detected=False,
            max_allowed_negative_delta=-0.02,
        )

    complete = evaluate_nmi_readiness(
        [oer, battery],
        NmiStudyPolicy(),
        transfer_comparisons=[transfer(oer, battery), transfer(battery, oer)],
    )
    assert complete.meets_evidence_policy is True
    assert complete.failed_global_gates == []


def test_nmi_report_builder_is_deterministic(tmp_path):
    import json

    from app.scripts.build_nmi_study_report import build_nmi_study_report

    spec = {
        "domains": [
            {
                "domain": "oer-electrocatalysis",
                "package": {
                    "package_id": "oer-electrocatalysis",
                    "package_version": "0.3.3-pre-review",
                },
                "total_paper_count": 20,
                "primary_paper_count": 7,
                "teacher_evaluated_paper_count": 4,
                "independent_model_family_count": 3,
                "occurrence_slot_count": 273,
                "perturbation_tested_count": 95,
                "tier_a_silver_count": 63,
                "prompt_configuration_count": 1,
                "negative_control_count": 0,
                "deterministic_rebuild_verified": False,
                "external_utility": None,
            }
        ],
        "transfer_comparisons": [],
    }
    input_path = tmp_path / "study.json"
    output_path = tmp_path / "readiness.json"
    input_path.write_text(json.dumps(spec))

    first = build_nmi_study_report(input_path, output_path)
    second = build_nmi_study_report(input_path, output_path)

    assert first["changed"] is True
    assert second["changed"] is False
    report = json.loads(output_path.read_text())
    assert report["meets_evidence_policy"] is False
    assert report["failed_global_gates"] == ["cross_domain_count"]
