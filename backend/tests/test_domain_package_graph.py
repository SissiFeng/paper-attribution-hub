from __future__ import annotations

import pytest


def _ref(package_id: str, version: str = "1.0.0"):
    from app.domain_adaptation.package_graph import PackageReference

    return PackageReference(package_id=package_id, package_version=version)


def _dependency(
    package_id: str,
    dependency_kind: str,
    version: str = "1.0.0",
):
    from app.domain_adaptation.package_graph import PackageDependency

    return PackageDependency(
        package_id=package_id,
        package_version=version,
        dependency_kind=dependency_kind,
    )


def test_package_graph_resolves_multi_parent_domain_dependencies():
    from app.domain_adaptation.package_graph import (
        PackageDescriptor,
        resolve_package_graph,
    )

    core = PackageDescriptor(
        package_id="scientific-core",
        package_version="1.0.0",
        package_kind="scientific_core",
        domain="general scientific evidence and tool use",
    )
    characterization = PackageDescriptor(
        package_id="materials-characterization",
        package_version="1.0.0",
        package_kind="capability",
        domain="materials characterization",
        dependencies=[_dependency("scientific-core", "scientific_core")],
    )
    electrocatalysis = PackageDescriptor(
        package_id="electrocatalysis-core",
        package_version="1.0.0",
        package_kind="domain",
        domain="electrocatalysis",
        dependencies=[_dependency("scientific-core", "scientific_core")],
    )
    oer = PackageDescriptor(
        package_id="oer-electrocatalysis",
        package_version="1.0.0",
        package_kind="domain",
        domain="oxygen evolution electrocatalysis",
        dependencies=[
            _dependency("electrocatalysis-core", "parent_domain"),
            _dependency("materials-characterization", "capability"),
        ],
        facets=["oxygen-evolution", "electrochemical-testing"],
    )

    report = resolve_package_graph(
        [oer, characterization, core, electrocatalysis],
        root=_ref("oer-electrocatalysis"),
    )

    assert report.valid is True
    assert report.resolution_order[-1] == "oer-electrocatalysis@1.0.0"
    assert set(report.dependency_closure) == {
        "scientific-core@1.0.0",
        "materials-characterization@1.0.0",
        "electrocatalysis-core@1.0.0",
    }


def test_package_graph_fails_closed_on_missing_or_cyclic_dependencies():
    from app.domain_adaptation.package_graph import (
        PackageDescriptor,
        PackageGraphError,
        resolve_package_graph,
    )

    missing = PackageDescriptor(
        package_id="oer",
        package_version="1.0.0",
        package_kind="domain",
        domain="OER",
        dependencies=[_dependency("scientific-core", "scientific_core")],
    )
    with pytest.raises(PackageGraphError, match="Missing package dependency"):
        resolve_package_graph([missing], root=_ref("oer"))

    left = PackageDescriptor(
        package_id="left",
        package_version="1.0.0",
        package_kind="domain",
        domain="left",
        dependencies=[_dependency("right", "parent_domain")],
    )
    right = PackageDescriptor(
        package_id="right",
        package_version="1.0.0",
        package_kind="domain",
        domain="right",
        dependencies=[_dependency("left", "parent_domain")],
    )
    with pytest.raises(PackageGraphError, match="cycle"):
        resolve_package_graph([left, right], root=_ref("left"))


def test_skill_promotion_requires_cross_domain_support_and_no_negative_transfer():
    from app.domain_adaptation.promotion import (
        PromotionCandidate,
        PromotionMetrics,
        PromotionPolicy,
        evaluate_promotion,
    )

    candidate = PromotionCandidate(
        promotion_id="promotion-skill-1",
        promotion_kind="scientific_skill",
        target_layer="scientific_core_tasks",
        source_package=_ref("oer-electrocatalysis"),
        target_package=_ref("scientific-core"),
        source_record_ids=["task-1"],
        evidence_ids=["evidence-1"],
        reviewed_gold_ids=["gold-1"],
        supporting_packages=[
            _ref("oer-electrocatalysis"),
            _ref("photocatalysis"),
        ],
        human_reviewed=True,
        deterministic_rebuild_verified=True,
        metrics=PromotionMetrics(
            gold_precision=0.9,
            evidence_validity=1.0,
            rag_answer_f1=0.82,
            retrieval_recall=0.9,
            evaluated_question_count=40,
            domain_eval_deltas={
                "oer-electrocatalysis": 0.03,
                "photocatalysis": 0.01,
            },
            negative_transfer_failure_count=0,
        ),
    )

    accepted = evaluate_promotion(candidate, PromotionPolicy())
    rejected = evaluate_promotion(
        candidate.model_copy(
            update={
                "metrics": candidate.metrics.model_copy(
                    update={
                        "domain_eval_deltas": {
                            "oer-electrocatalysis": 0.03,
                            "photocatalysis": -0.08,
                        }
                    }
                )
            }
        ),
        PromotionPolicy(),
    )

    assert accepted.eligible_for_human_approval is True
    assert accepted.failed_gates == []
    assert rejected.eligible_for_human_approval is False
    assert "negative_transfer" in rejected.failed_gates


def test_weight_consolidation_requires_adapter_replay_and_general_retention():
    from app.domain_adaptation.promotion import (
        PromotionCandidate,
        PromotionMetrics,
        PromotionPolicy,
        evaluate_promotion,
    )

    candidate = PromotionCandidate(
        promotion_id="promotion-weight-1",
        promotion_kind="weight_consolidation",
        target_layer="scientific_base_weights",
        source_package=_ref("oer-electrocatalysis"),
        target_package=_ref("scientific-base", "2.0.0"),
        source_record_ids=["adapter-manifest-1"],
        evidence_ids=["evidence-1"],
        reviewed_gold_ids=["gold-1"],
        supporting_packages=[
            _ref("oer-electrocatalysis"),
            _ref("photocatalysis"),
        ],
        human_reviewed=True,
        deterministic_rebuild_verified=True,
        adapter_artifact_sha256="a" * 64,
        metrics=PromotionMetrics(
            gold_precision=0.9,
            evidence_validity=1.0,
            rag_answer_f1=0.85,
            retrieval_recall=0.9,
            evaluated_question_count=50,
            replay_evaluation_count=200,
            general_capability_retention=0.99,
            domain_eval_deltas={
                "oer-electrocatalysis": 0.02,
                "photocatalysis": 0.0,
            },
            negative_transfer_failure_count=0,
        ),
    )

    accepted = evaluate_promotion(candidate, PromotionPolicy())
    rejected = evaluate_promotion(
        candidate.model_copy(update={"adapter_artifact_sha256": None}),
        PromotionPolicy(),
    )

    assert accepted.eligible_for_human_approval is True
    assert rejected.eligible_for_human_approval is False
    assert "adapter_artifact" in rejected.failed_gates


def test_incomplete_promotion_proposal_reports_all_missing_evidence_gates():
    from app.domain_adaptation.promotion import (
        PromotionCandidate,
        PromotionPolicy,
        evaluate_promotion,
    )

    proposal = PromotionCandidate(
        promotion_id="promotion-pending-1",
        promotion_kind="shared_knowledge",
        target_layer="shared_knowledge",
        source_package=_ref("oer-electrocatalysis"),
        target_package=_ref("scientific-core"),
    )

    decision = evaluate_promotion(proposal, PromotionPolicy())

    assert decision.eligible_for_human_approval is False
    assert set(decision.failed_gates) >= {
        "human_review",
        "provenance",
        "reviewed_gold",
        "deterministic_rebuild",
        "gold_precision",
        "evidence_validity",
        "rag_utility",
        "retrieval_coverage",
        "evaluation_size",
    }
