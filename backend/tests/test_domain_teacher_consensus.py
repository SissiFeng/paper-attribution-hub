from __future__ import annotations

import json


def _proposal(
    *,
    alias: str,
    family: str,
    value: str = "10 mg",
    evidence_valid: bool = True,
    perturbation_status: str = "passed",
    evidence_start: int = 0,
):
    from app.domain_adaptation.consensus import (
        ModelFieldProposal,
        ProposalEvidence,
    )

    evidence = (
        ProposalEvidence(
            evidence_id=f"evidence-{alias}-{evidence_start}",
            source_chunk_id="methods-1",
            quote="10 mg of NiFe catalyst was dispersed in ethanol.",
            char_start=evidence_start,
            char_end=evidence_start + 48,
            document_char_start=100 + evidence_start,
            document_char_end=148 + evidence_start,
            source_sha256="0" * 64,
        )
        if evidence_valid
        else None
    )
    return ModelFieldProposal(
        model_alias=alias,
        model_family=family,
        model_id=f"{family}.model",
        paper_id="DOI:10.1000_consensus",
        evidence_scope="primary_report",
        protocol_name="catalyst ink preparation",
        entity_type="materials",
        entity_key="NiFe catalyst",
        field_name="amount",
        field_path="materials[0].amount",
        source_value=value,
        evidence=evidence,
        evidence_valid=evidence_valid,
        validation_reason=None if evidence_valid else "span_not_in_source",
        perturbation_status=perturbation_status,
    )


def test_two_independent_families_with_stable_evidence_create_tier_a_silver():
    from app.domain_adaptation.consensus import build_source_grounded_consensus

    result = build_source_grounded_consensus(
        [
            _proposal(alias="kimi", family="moonshot"),
            _proposal(alias="opus", family="anthropic", value="10  mg"),
        ]
    )

    assert len(result.accepted) == 1
    assert result.disputed == []
    assert result.abstained == []
    decision = result.accepted[0]
    assert decision.tier == "A"
    assert decision.decision == "accepted_silver"
    assert decision.normalized_value == "10 mg"
    assert decision.supporting_model_aliases == ["kimi", "opus"]
    assert decision.supporting_model_families == ["anthropic", "moonshot"]
    assert decision.training_eligible is True
    assert result.report.accepted_count == 1
    assert result.report.claims_boundary.startswith("Consensus silver is not")


def test_valid_competing_values_remain_disputed_instead_of_using_majority_vote():
    from app.domain_adaptation.consensus import build_source_grounded_consensus

    result = build_source_grounded_consensus(
        [
            _proposal(alias="kimi", family="moonshot"),
            _proposal(alias="opus", family="anthropic"),
            _proposal(alias="sol", family="openai", value="20 mg"),
        ]
    )

    assert result.accepted == []
    assert len(result.disputed) == 1
    decision = result.disputed[0]
    assert decision.decision == "disputed"
    assert decision.tier == "B"
    assert decision.training_eligible is False
    assert decision.reasons == ["valid_value_contradiction"]
    assert [item.normalized_value for item in decision.alternatives] == [
        "10 mg",
        "20 mg",
    ]


def test_duplicate_aliases_from_one_model_family_do_not_create_consensus():
    from app.domain_adaptation.consensus import build_source_grounded_consensus

    result = build_source_grounded_consensus(
        [
            _proposal(alias="opus-run-1", family="anthropic"),
            _proposal(alias="opus-run-2", family="anthropic"),
        ]
    )

    assert result.accepted == []
    assert len(result.disputed) == 1
    assert result.disputed[0].reasons == ["insufficient_independent_families"]


def test_untested_perturbation_keeps_agreement_out_of_training_tier():
    from app.domain_adaptation.consensus import build_source_grounded_consensus

    result = build_source_grounded_consensus(
        [
            _proposal(
                alias="kimi",
                family="moonshot",
                perturbation_status="not_tested",
            ),
            _proposal(
                alias="sol",
                family="openai",
                perturbation_status="not_tested",
            ),
        ]
    )

    assert result.accepted == []
    assert len(result.disputed) == 1
    assert result.disputed[0].reasons == ["perturbation_not_verified"]
    assert result.disputed[0].training_eligible is False


def test_unsupported_model_proposals_create_an_auditable_abstention():
    from app.domain_adaptation.consensus import build_source_grounded_consensus

    result = build_source_grounded_consensus(
        [
            _proposal(
                alias="kimi",
                family="moonshot",
                evidence_valid=False,
            ),
            _proposal(
                alias="opus",
                family="anthropic",
                evidence_valid=False,
            ),
        ]
    )

    assert result.accepted == []
    assert result.disputed == []
    assert len(result.abstained) == 1
    decision = result.abstained[0]
    assert decision.decision == "abstained"
    assert decision.tier == "C"
    assert decision.reasons == ["no_deterministically_valid_evidence"]


def test_non_overlapping_single_family_occurrences_do_not_create_consensus():
    from app.domain_adaptation.consensus import build_source_grounded_consensus

    result = build_source_grounded_consensus(
        [
            _proposal(alias="kimi", family="moonshot", evidence_start=0),
            _proposal(alias="sol", family="openai", evidence_start=200),
        ]
    )

    assert result.accepted == []
    assert len(result.disputed) == 2
    assert {item.reasons[0] for item in result.disputed} == {
        "insufficient_independent_families"
    }


def test_distinct_supported_occurrences_are_not_mislabeled_as_value_conflicts():
    from app.domain_adaptation.consensus import build_source_grounded_consensus

    result = build_source_grounded_consensus(
        [
            _proposal(
                alias="kimi",
                family="moonshot",
                value="1 M",
                evidence_start=0,
            ),
            _proposal(
                alias="opus",
                family="anthropic",
                value="1 M",
                evidence_start=0,
            ),
            _proposal(
                alias="kimi",
                family="moonshot",
                value="6 M",
                evidence_start=200,
            ),
            _proposal(
                alias="opus",
                family="anthropic",
                value="6 M",
                evidence_start=200,
            ),
        ]
    )

    assert result.disputed == []
    assert [item.normalized_value for item in result.accepted] == ["1 m", "6 m"]


def test_consensus_compiles_numeric_claims_into_counterfactual_cases():
    from app.domain_adaptation.consensus import (
        build_source_grounded_consensus,
        generate_perturbation_cases,
    )

    proposals = [
        _proposal(
            alias="kimi",
            family="moonshot",
            perturbation_status="not_tested",
        ),
        _proposal(
            alias="opus",
            family="anthropic",
            perturbation_status="not_tested",
        ),
    ]
    consensus = build_source_grounded_consensus(proposals)

    cases = generate_perturbation_cases(
        proposals=proposals,
        decisions=consensus.disputed,
    )

    assert [item.perturbation_type for item in cases] == [
        "evidence_deletion",
        "numeric_replacement",
    ]
    assert cases[0].expected_behavior == "omit_or_abstain"
    assert cases[0].mutated_quote == " of NiFe catalyst was dispersed in ethanol."
    assert cases[1].expected_behavior == "extract_replacement"
    assert cases[1].expected_source_value == "11 mg"
    assert cases[1].mutated_quote == (
        "11 mg of NiFe catalyst was dispersed in ethanol."
    )


def test_step_counterfactuals_mutate_only_atomic_params():
    from app.domain_adaptation.consensus import (
        ModelFieldProposal,
        ProposalEvidence,
        build_source_grounded_consensus,
        generate_perturbation_cases,
    )

    quote = (
        "The ink was prepared by sonicating a mixture of 3 mg catalyst and "
        "500 μL DI water."
    )

    def step_proposal(*, alias: str, family: str, field: str, value: str):
        return ModelFieldProposal(
            model_alias=alias,
            model_family=family,
            model_id=f"{family}.model",
            paper_id="paper-atomic-step",
            evidence_scope="primary_report",
            protocol_name="ink preparation",
            entity_type="steps",
            entity_key="sonicating|mixture",
            field_name=field,
            field_path=f"protocol/steps/step-1/{field}",
            source_value=value,
            evidence=ProposalEvidence(
                evidence_id="evidence-atomic-step",
                source_chunk_id="methods-1",
                quote=quote,
                char_start=0,
                char_end=len(quote),
                source_sha256="a" * 64,
            ),
            evidence_valid=True,
        )

    proposals = [
        step_proposal(alias=alias, family=family, field=field, value=value)
        for alias, family in (("kimi", "moonshot"), ("opus", "anthropic"))
        for field, value in (("verb", "sonicating"), ("param:amount", "3 mg"))
    ]
    consensus = build_source_grounded_consensus(proposals)

    cases = generate_perturbation_cases(
        proposals=proposals,
        decisions=consensus.disputed,
    )

    verb_cases = [item for item in cases if item.field_name == "verb"]
    param_cases = [item for item in cases if item.field_name == "param:amount"]
    assert [item.perturbation_type for item in verb_cases] == [
        "evidence_deletion"
    ]
    assert [item.perturbation_type for item in param_cases] == [
        "evidence_deletion",
        "numeric_replacement",
    ]
    replacement = param_cases[1]
    assert replacement.original_source_value == "3 mg"
    assert replacement.expected_source_value == "4 mg"
    assert replacement.mutated_quote == quote.replace("3 mg", "4 mg", 1)
    assert replacement.expected_source_value != replacement.mutated_quote
    assert replacement.source_value_char_start == quote.index("3 mg")
    assert replacement.source_value_char_end == quote.index("3 mg") + 4


def test_counterfactual_compilation_abstains_on_ambiguous_value_occurrence():
    from app.domain_adaptation.consensus import (
        ModelFieldProposal,
        ProposalEvidence,
        build_source_grounded_consensus,
        generate_perturbation_cases,
    )

    quote = "A mixture of 3 mg catalyst and 3 mg support was sonicated."
    proposals = []
    for alias, family in (("kimi", "moonshot"), ("opus", "anthropic")):
        proposals.append(
            ModelFieldProposal(
                model_alias=alias,
                model_family=family,
                model_id=f"{family}.model",
                paper_id="paper-ambiguous-step",
                evidence_scope="primary_report",
                protocol_name="mixture preparation",
                entity_type="steps",
                entity_key="sonicated|support",
                field_name="param:support_amount",
                field_path="protocol/steps/step-1/param:support_amount",
                source_value="3 mg",
                evidence=ProposalEvidence(
                    evidence_id="evidence-ambiguous-step",
                    source_chunk_id="methods-1",
                    quote=quote,
                    char_start=0,
                    char_end=len(quote),
                    source_sha256="b" * 64,
                ),
                evidence_valid=True,
            )
        )

    consensus = build_source_grounded_consensus(proposals)

    assert generate_perturbation_cases(
        proposals=proposals,
        decisions=consensus.disputed,
    ) == []


def test_counterfactual_results_promote_only_models_that_pass_both_cases():
    from app.domain_adaptation.consensus import (
        ModelClaimPerturbationResult,
        apply_perturbation_results,
        build_source_grounded_consensus,
    )

    proposals = [
        _proposal(
            alias="kimi",
            family="moonshot",
            perturbation_status="not_tested",
        ),
        _proposal(
            alias="opus",
            family="anthropic",
            perturbation_status="not_tested",
        ),
    ]
    initial = build_source_grounded_consensus(proposals)
    results = [
        ModelClaimPerturbationResult(
            model_alias=item.model_alias,
            decision_id=initial.disputed[0].decision_id,
            evidence_deletion_passed=True,
            numeric_replacement_passed=True,
        )
        for item in proposals
    ]

    updated = apply_perturbation_results(
        proposals,
        decisions=initial.disputed,
        results=results,
    )
    consensus = build_source_grounded_consensus(updated)

    assert all(item.perturbation_status == "passed" for item in updated)
    assert len(consensus.accepted) == 1
    assert consensus.accepted[0].training_eligible is True


def test_perturbation_result_promotes_only_its_source_occurrence():
    from app.domain_adaptation.consensus import (
        ModelClaimPerturbationResult,
        apply_perturbation_results,
        build_source_grounded_consensus,
    )

    proposals = [
        _proposal(
            alias=alias,
            family=family,
            perturbation_status="not_tested",
            evidence_start=evidence_start,
        )
        for evidence_start in (0, 200)
        for alias, family in (("kimi", "moonshot"), ("opus", "anthropic"))
    ]
    initial = build_source_grounded_consensus(proposals)
    first_decision = initial.disputed[0]
    results = [
        ModelClaimPerturbationResult(
            model_alias=alias,
            decision_id=first_decision.decision_id,
            evidence_deletion_passed=True,
            numeric_replacement_passed=True,
        )
        for alias in ("kimi", "opus")
    ]

    updated = apply_perturbation_results(
        proposals,
        decisions=initial.disputed,
        results=results,
    )
    final = build_source_grounded_consensus(updated)

    assert len(final.accepted) == 1
    assert len(final.disputed) == 1
    assert final.disputed[0].reasons == ["perturbation_not_verified"]


def test_teacher_package_loader_emits_validated_fields_with_source_locators(
    tmp_path,
):
    from app.domain_adaptation.consensus import load_model_proposals_from_package
    from app.domain_adaptation.models import EvidenceSpan, MaterialInput, ProtocolUnit

    package = tmp_path / "kimi-package"
    (package / "knowledge").mkdir(parents=True)
    (package / "reports").mkdir()
    (package / "manifest.json").write_text(
        json.dumps(
            {
                "extraction": {
                    "mode": "teacher",
                    "model": "moonshotai.kimi-k2.5",
                }
            }
        )
    )
    evidence = EvidenceSpan(
        evidence_id="ev-package",
        paper_id="DOI:10.1000_consensus",
        chunk_id="methods-1",
        quote="10 mg of NiFe catalyst was dispersed in ethanol.",
        char_start=0,
        char_end=48,
        document_char_start=100,
        document_char_end=148,
        source_sha256="0" * 64,
    )
    protocol = ProtocolUnit(
        protocol_id="protocol-package",
        paper_id=evidence.paper_id,
        protocol_name="catalyst ink preparation",
        protocol_type="electrode_preparation",
        source_paper_tier="primary_oer",
        evidence_scope="primary_report",
        source_chunk_ids=[evidence.chunk_id],
        materials=[
            MaterialInput(
                entity_id="material-package",
                name="NiFe catalyst",
                amount="10 mg",
                evidence_ids=[evidence.evidence_id],
            )
        ],
        evidence=[evidence],
    )
    (package / "knowledge/protocols.jsonl").write_text(
        json.dumps(
            {
                "schema_version": "domain-adapter-knowledge-v0.1",
                **protocol.model_dump(mode="json"),
            }
        )
        + "\n"
    )
    (package / "reports/teacher_field_audit.jsonl").write_text("")

    proposals = load_model_proposals_from_package(
        package,
        model_alias="kimi",
        model_family="moonshot",
    )

    assert [(item.field_name, item.source_value) for item in proposals] == [
        ("amount", "10 mg"),
        ("name", "NiFe catalyst"),
    ]
    assert all(item.model_id == "moonshotai.kimi-k2.5" for item in proposals)
    assert all(item.evidence_valid for item in proposals)
    assert all(item.evidence.evidence_id == "ev-package" for item in proposals if item.evidence)
    assert all(item.perturbation_status == "not_tested" for item in proposals)
    by_field = {item.field_name: item for item in proposals}
    assert by_field["amount"].source_value_occurrence == "exact_unique"
    assert by_field["amount"].source_value_char_start == 0
    assert by_field["amount"].source_value_char_end == 5
    assert by_field["name"].source_value_occurrence == "exact_unique"


def test_teacher_package_loader_covers_protocol_knowledge_entity_types(tmp_path):
    from app.domain_adaptation.consensus import load_model_proposals_from_package
    from app.domain_adaptation.models import (
        Caveat,
        CharacterizationUse,
        EvidenceSpan,
        InstrumentUse,
        ProtocolStep,
        ProtocolUnit,
        ReportedResult,
        SoftwareUse,
    )

    package = tmp_path / "opus-package"
    (package / "knowledge").mkdir(parents=True)
    (package / "reports").mkdir()
    (package / "manifest.json").write_text(
        json.dumps(
            {
                "extraction": {
                    "mode": "teacher",
                    "model": "us.anthropic.claude-opus-5",
                }
            }
        )
    )
    quote = "VSP-300 with EC-Lab 11.0 measured OER at 10 mV s-1."
    evidence = EvidenceSpan(
        evidence_id="ev-all-types",
        paper_id="DOI:10.1000_all_types",
        chunk_id="methods-all",
        quote=quote,
        char_start=0,
        char_end=len(quote),
        source_sha256="1" * 64,
    )
    protocol = ProtocolUnit(
        protocol_id="protocol-all-types",
        paper_id=evidence.paper_id,
        protocol_name="OER measurement",
        protocol_type="electrochemistry",
        evidence_scope="primary_report",
        source_chunk_ids=[evidence.chunk_id],
        instruments=[
            InstrumentUse(
                entity_id="instrument-all",
                name="potentiostat",
                model="VSP-300",
                settings={"scan rate": "10 mV s-1"},
                evidence_ids=[evidence.evidence_id],
            )
        ],
        software=[
            SoftwareUse(
                entity_id="software-all",
                name="EC-Lab",
                version="11.0",
                evidence_ids=[evidence.evidence_id],
            )
        ],
        steps=[
            ProtocolStep(
                step_id="step-all",
                order=1,
                action="measured",
                verb="measured",
                targets=["OER"],
                params={"scan rate": "10 mV s-1"},
                notes="corrected for resistance",
                evidence_ids=[evidence.evidence_id],
            )
        ],
        characterization=[
            CharacterizationUse(
                entity_id="characterization-all",
                technique="LSV",
                output="polarization curve",
                evidence_ids=[evidence.evidence_id],
            )
        ],
        results=[
            ReportedResult(
                result_id="result-all",
                metric="overpotential",
                raw_value="250 mV",
                context="10 mA cm-2",
                evidence_ids=[evidence.evidence_id],
            )
        ],
        caveats=[
            Caveat(
                caveat_id="caveat-all",
                text="corrected for resistance",
                evidence_ids=[evidence.evidence_id],
            )
        ],
        evidence=[evidence],
    )
    (package / "knowledge/protocols.jsonl").write_text(
        json.dumps(protocol.model_dump(mode="json")) + "\n"
    )
    (package / "reports/teacher_field_audit.jsonl").write_text("")

    proposals = load_model_proposals_from_package(
        package,
        model_alias="opus",
        model_family="anthropic",
    )

    assert {
        (item.entity_type, item.field_name, item.source_value)
        for item in proposals
    } == {
        ("caveats", "text", "corrected for resistance"),
        ("characterization", "output", "polarization curve"),
        ("characterization", "technique", "LSV"),
        ("instruments", "model", "VSP-300"),
        ("instruments", "name", "potentiostat"),
        ("instruments", "setting:scan rate", "10 mV s-1"),
        ("results", "context", "10 mA cm-2"),
        ("results", "metric", "overpotential"),
        ("results", "raw_value", "250 mV"),
        ("software", "name", "EC-Lab"),
        ("software", "version", "11.0"),
        ("steps", "verb", "measured"),
        ("steps", "target:0", "OER"),
        ("steps", "param:scan rate", "10 mV s-1"),
        ("steps", "notes", "corrected for resistance"),
    }
    step_proposals = [item for item in proposals if item.entity_type == "steps"]
    assert {item.entity_key for item in step_proposals} == {"measured|OER"}
    assert all(item.field_name != "action" for item in step_proposals)


def test_consensus_artifact_builder_is_non_overwriting_and_keeps_gold_blocked(
    tmp_path,
):
    import pytest

    from app.domain_adaptation.model_benchmark import TeacherModelCandidate
    from app.domain_adaptation.models import EvidenceSpan, MaterialInput, ProtocolUnit
    from app.scripts.build_teacher_consensus import build_teacher_consensus_artifacts

    def write_package(root, *, model_id: str, evidence_id: str):
        (root / "knowledge").mkdir(parents=True)
        (root / "reports").mkdir()
        (root / "source").mkdir()
        (root / "manifest.json").write_text(
            json.dumps(
                {
                    "extraction": {
                        "mode": "teacher",
                        "model": model_id,
                        "region": "us-east-1",
                        "prompt_version": "oer-protocol-teacher-v0.2",
                        "inference_config": {
                            "temperature": 0.0,
                            "max_output_tokens": 14000,
                        },
                    },
                    "counts": {
                        "paper_count": 1,
                        "protocol_count": 1,
                        "task_count": 1,
                    },
                }
            )
        )
        (root / "reports/quality_report.json").write_text("{}")
        (root / "source/selection_manifest.json").write_text(
            json.dumps({"selection": "same"})
        )
        evidence = EvidenceSpan(
            evidence_id=evidence_id,
            paper_id="DOI:10.1000_consensus",
            chunk_id="methods-1",
            quote="10 mg of NiFe catalyst was dispersed in ethanol.",
            char_start=0,
            char_end=48,
            source_sha256="0" * 64,
        )
        protocol = ProtocolUnit(
            protocol_id=f"protocol-{evidence_id}",
            paper_id=evidence.paper_id,
            protocol_name="catalyst ink preparation",
            protocol_type="electrode_preparation",
            evidence_scope="primary_report",
            source_chunk_ids=[evidence.chunk_id],
            materials=[
                MaterialInput(
                    entity_id=f"material-{evidence_id}",
                    name="NiFe catalyst",
                    amount="10 mg",
                    evidence_ids=[evidence.evidence_id],
                )
            ],
            evidence=[evidence],
        )
        (root / "knowledge/protocols.jsonl").write_text(
            json.dumps(protocol.model_dump(mode="json")) + "\n"
        )
        (root / "reports/teacher_field_audit.jsonl").write_text("")
        return root

    models = [
        TeacherModelCandidate(
            alias="kimi",
            model_id="moonshotai.kimi-k2.5",
            region="us-east-1",
        ),
        TeacherModelCandidate(
            alias="opus",
            model_id="us.anthropic.claude-opus-5",
            region="us-east-1",
        ),
    ]
    packages = {
        "kimi": write_package(
            tmp_path / "kimi",
            model_id=models[0].model_id,
            evidence_id="evidence-kimi",
        ),
        "opus": write_package(
            tmp_path / "opus",
            model_id=models[1].model_id,
            evidence_id="evidence-opus",
        ),
    }
    output = tmp_path / "consensus-output"

    report = build_teacher_consensus_artifacts(
        benchmark_id="oer-consensus-v0.1",
        models=models,
        package_dirs=packages,
        output_dir=output,
    )

    assert report["proposal_count"] == 4
    assert report["accepted_count"] == 0
    assert report["disputed_count"] == 2
    assert report["scientific_ranking"] == {
        "eligible": False,
        "reason": "shared_gold_required",
    }
    pairwise = json.loads(
        (output / "consensus/pairwise_agreement.json").read_text()
    )
    assert pairwise["pairs"][0]["exact_claim_jaccard"] == 1.0
    assert (output / "consensus/model_claims.jsonl").is_file()
    assert (output / "consensus/accepted_silver.jsonl").read_text() == ""
    assert (output / "consensus/disputed_claims.jsonl").is_file()
    perturbation_cases = [
        json.loads(line)
        for line in (output / "consensus/perturbation_cases.jsonl")
        .read_text()
        .splitlines()
    ]
    assert len(perturbation_cases) == 3
    assert {item["perturbation_type"] for item in perturbation_cases} == {
        "evidence_deletion",
        "numeric_replacement",
    }
    perturbation_report = json.loads(
        (output / "reports/perturbation_report.json").read_text()
    )
    assert perturbation_report["case_count"] == 3
    assert (output / "reports/consensus_report.json").is_file()

    from app.domain_adaptation.consensus import ModelClaimPerturbationResult

    case_types_by_decision: dict[str, set[str]] = {}
    targets_by_decision: dict[str, set[str]] = {}
    for case in perturbation_cases:
        case_types_by_decision.setdefault(case["decision_id"], set()).add(
            case["perturbation_type"]
        )
        targets_by_decision.setdefault(case["decision_id"], set()).update(
            case["target_model_aliases"]
        )
    perturbation_results = [
        ModelClaimPerturbationResult(
            model_alias=alias,
            decision_id=decision_id,
            evidence_deletion_passed=True,
            numeric_replacement_passed=(
                True
                if "numeric_replacement" in case_types_by_decision[decision_id]
                else None
            ),
        )
        for decision_id in sorted(case_types_by_decision)
        for alias in sorted(targets_by_decision[decision_id])
    ]
    promoted_output = tmp_path / "consensus-promoted-output"
    promoted_report = build_teacher_consensus_artifacts(
        benchmark_id="oer-consensus-v0.1",
        models=models,
        package_dirs=packages,
        output_dir=promoted_output,
        perturbation_results=perturbation_results,
    )
    assert promoted_report["accepted_count"] == 2
    assert promoted_report["disputed_count"] == 0
    assert (
        len(
            (
                promoted_output / "consensus/accepted_silver.jsonl"
            ).read_text().splitlines()
        )
        == 2
    )

    migrated_output = tmp_path / "consensus-migrated-output"
    migrated_report = build_teacher_consensus_artifacts(
        benchmark_id="oer-consensus-v0.1",
        models=models,
        package_dirs=packages,
        output_dir=migrated_output,
        perturbation_results=[
            *perturbation_results,
            ModelClaimPerturbationResult(
                model_alias="kimi",
                decision_id="consensus_removed_legacy_action",
                evidence_deletion_passed=True,
            ),
        ],
        ignore_stale_perturbation_results=True,
    )
    assert migrated_report["ignored_stale_perturbation_result_count"] == 1
    persisted_results = (
        migrated_output / "consensus/perturbation_results.jsonl"
    ).read_text()
    assert "consensus_removed_legacy_action" not in persisted_results

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        build_teacher_consensus_artifacts(
            benchmark_id="oer-consensus-v0.1",
            models=models,
            package_dirs=packages,
            output_dir=output,
        )


def test_legacy_action_audit_separates_contaminated_and_atomic_results(tmp_path):
    import pytest

    from app.scripts.audit_legacy_step_action import audit_legacy_step_action

    consensus = tmp_path / "legacy" / "consensus"
    consensus.mkdir(parents=True)

    def write_jsonl(name: str, rows: list[dict]):
        (consensus / name).write_text(
            "".join(json.dumps(row) + "\n" for row in rows)
        )

    cases = [
        {
            "decision_id": "action-decision",
            "entity_type": "steps",
            "field_name": "action",
        },
        {
            "decision_id": "amount-decision",
            "entity_type": "materials",
            "field_name": "amount",
        },
    ]
    write_jsonl("perturbation_cases.jsonl", cases)
    write_jsonl(
        "perturbation_results.jsonl",
        [
            {
                "decision_id": "action-decision",
                "model_alias": "kimi",
                "evidence_deletion_passed": True,
                "numeric_replacement_passed": False,
            },
            {
                "decision_id": "action-decision",
                "model_alias": "opus",
                "evidence_deletion_passed": True,
                "numeric_replacement_passed": False,
            },
            {
                "decision_id": "amount-decision",
                "model_alias": "kimi",
                "evidence_deletion_passed": True,
                "numeric_replacement_passed": True,
            },
            {
                "decision_id": "amount-decision",
                "model_alias": "opus",
                "evidence_deletion_passed": True,
                "numeric_replacement_passed": True,
            },
        ],
    )
    write_jsonl(
        "accepted_silver.jsonl",
        [
            {
                "decision_id": "amount-decision",
                "entity_type": "materials",
                "field_name": "amount",
                "reasons": ["independent_source_grounded_consensus"],
            }
        ],
    )
    write_jsonl(
        "disputed_claims.jsonl",
        [
            {
                "decision_id": "action-decision",
                "entity_type": "steps",
                "field_name": "action",
                "reasons": ["perturbation_failed"],
            }
        ],
    )
    output = tmp_path / "legacy_action_audit.json"

    report = audit_legacy_step_action(consensus.parent, output)

    assert report["counterfactual_results"]["action"]["numeric_replacement"] == {
        "passed": 0,
        "total": 2,
        "rate": 0.0,
    }
    assert report["counterfactual_results"]["non_action"][
        "numeric_replacement"
    ] == {"passed": 2, "total": 2, "rate": 1.0}
    assert report["consensus_slots"]["action"] == {
        "accepted": 0,
        "perturbation_failed": 1,
        "perturbation_not_verified": 0,
        "evaluated_slot_count": 1,
        "failure_share_of_evaluated": 1.0,
    }
    assert "contaminated" in report["claims_boundary"]
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        audit_legacy_step_action(consensus.parent, output)
