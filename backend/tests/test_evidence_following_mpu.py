from __future__ import annotations

import json

import pytest
from pydantic import ValidationError


def _paper(domain: str, suffix: str):
    from app.domain_adaptation.evidence_following_mpu import MpuPaper

    return MpuPaper(
        paper_id=f"{domain}-{suffix}",
        domain=domain,
        title=f"Primary paper {suffix}",
        doi=f"10.1000/{domain}.{suffix}",
        report_type="primary_experiment",
        source_markdown_sha256=("a" if domain == "oer" else "b") * 64,
    )


def _task(domain: str, suffix: str):
    from app.domain_adaptation.evidence_following_mpu import MpuTask

    paper = _paper(domain, suffix)
    return MpuTask(
        task_id=f"task-{domain}-{suffix}",
        paper_id=paper.paper_id,
        domain=domain,
        field_type="amount",
        question="What amount was used?",
        paper_identity=f"{paper.title}; DOI {paper.doi}",
        blind_context="A primary experimental protocol",
        original_value="10 mg",
        replacement_value="11 mg",
        counterfactual_evidence="11 mg of catalyst was used.",
        fact_injection="Prior domain memory: this protocol used 10 mg.",
        source_evidence_sha256="c" * 64,
    )


def _policy():
    from app.domain_adaptation.evidence_following_mpu import MpuPolicy

    return MpuPolicy(
        min_primary_papers_per_domain=1,
        min_tasks_per_domain=1,
        min_model_count=2,
        bootstrap_replicates=200,
        correlation_equivalence_bound=0.3,
    )


def _spec():
    from app.domain_adaptation.evidence_following_mpu import (
        MpuModel,
        MpuStudyInput,
    )

    papers = [_paper("oer", "1"), _paper("organic-synthesis", "1")]
    tasks = [_task("oer", "1"), _task("organic-synthesis", "1")]
    return MpuStudyInput(
        study_id="evidence-following-mpu-v0.1",
        domains=["oer", "organic-synthesis"],
        policy=_policy(),
        models=[
            MpuModel(alias="model-a", family="family-a", model_id="a.1"),
            MpuModel(alias="model-b", family="family-b", model_id="b.1"),
        ],
        papers=papers,
        tasks=tasks,
    )


def _observation(prompt, values: list[str]):
    import hashlib

    from app.domain_adaptation.evidence_following_mpu import MpuObservation

    response_text = json.dumps({"values": values}, separators=(",", ":"))
    return MpuObservation(
        study_id="evidence-following-mpu-v0.1",
        prompt_id=prompt.prompt_id,
        prompt_sha256=prompt.prompt_sha256,
        task_id=prompt.task_id,
        model_alias=prompt.model_alias,
        model_id=prompt.model_id,
        condition=prompt.condition,
        run_id="test-run-1",
        provider_request_id="provider-request-1",
        response_text=response_text,
        response_sha256=hashlib.sha256(response_text.encode()).hexdigest(),
        values=values,
    )


def _complete_observations(spec):
    from app.domain_adaptation.evidence_following_mpu import build_mpu_design

    prompt_index = {
        (item.task_id, item.model_alias, item.condition): item
        for item in build_mpu_design(spec).prompts
    }
    rows = []
    for task in spec.tasks:
        for model in spec.models:
            follows = model.alias == "model-a"
            rows.extend(
                [
                    _observation(
                        prompt_index[
                            (task.task_id, model.alias, "closed_book_blind")
                        ],
                        [],
                    ),
                    _observation(
                        prompt_index[
                            (task.task_id, model.alias, "closed_book_identified")
                        ],
                        ["10 mg"] if follows else [],
                    ),
                    _observation(
                        prompt_index[
                            (task.task_id, model.alias, "fact_injected_probe")
                        ],
                        ["10 mg"],
                    ),
                    _observation(
                        prompt_index[(task.task_id, model.alias, "counterfactual")],
                        ["11 mg"] if follows else ["10 mg"],
                    ),
                    _observation(
                        prompt_index[
                            (
                                task.task_id,
                                model.alias,
                                "counterfactual_fact_injected",
                            )
                        ],
                        ["10 mg"],
                    ),
                ]
            )
    return rows


def test_mpu_contract_requires_two_domains_primary_papers_and_unique_coordinates():
    from app.domain_adaptation.evidence_following_mpu import MpuPolicy, MpuStudyInput

    with pytest.raises(ValidationError, match="literal_error"):
        MpuStudyInput.model_validate(
            {**_spec().model_dump(mode="json"), "schema_version": "future-v9"}
        )
    with pytest.raises(ValidationError, match="less than or equal to 10000"):
        MpuPolicy(bootstrap_replicates=10001)

    payload = _spec().model_dump(mode="json")
    payload["models"][1]["model_id"] = payload["models"][0]["model_id"]
    with pytest.raises(ValidationError, match="duplicate model IDs"):
        MpuStudyInput.model_validate(payload)

    payload = _spec().model_dump(mode="json")
    payload["policy"]["bootstrap_replicates"] = 10000
    seed_task = payload["tasks"][0]
    payload["tasks"] = [
        {**seed_task, "task_id": f"work-budget-{index}"} for index in range(501)
    ]
    with pytest.raises(ValidationError, match="score-visit work budget"):
        MpuStudyInput.model_validate(payload)

    payload = _spec().model_dump(mode="json")
    payload["domains"] = ["oer"]
    with pytest.raises(ValidationError, match="exactly two domains"):
        MpuStudyInput.model_validate(payload)

    payload = _spec().model_dump(mode="json")
    payload["papers"][1]["doi"] = payload["papers"][0]["doi"]
    with pytest.raises(ValidationError, match="duplicate DOIs"):
        MpuStudyInput.model_validate(payload)

    payload = _spec().model_dump(mode="json")
    payload["papers"][0]["report_type"] = "review"
    with pytest.raises(ValidationError, match="primary experimental"):
        MpuStudyInput.model_validate(payload)


def test_design_readiness_fails_closed_and_builds_all_five_prompt_conditions():
    from app.domain_adaptation.evidence_following_mpu import build_mpu_design

    spec = _spec()
    spec.policy.min_primary_papers_per_domain = 100
    design = build_mpu_design(spec)

    assert design.ready is False
    assert design.failed_gates == [
        "primary_papers:oer",
        "primary_papers:organic-synthesis",
    ]
    assert len(design.prompts) == 20
    assert {item.condition for item in design.prompts} == {
        "closed_book_blind",
        "closed_book_identified",
        "fact_injected_probe",
        "counterfactual",
        "counterfactual_fact_injected",
    }
    closed_book = next(
        item for item in design.prompts if item.condition == "closed_book_identified"
    )
    assert "existing model knowledge" in closed_book.system_instruction
    assert "Use only the current source evidence" not in closed_book.system_instruction
    injected = next(
        item
        for item in design.prompts
        if item.condition == "counterfactual_fact_injected"
    )
    assert "Prior domain memory" in (injected.user_payload.prior_fact or "")
    assert "11 mg" in (injected.user_payload.current_source_evidence or "")
    assert injected.prompt_sha256


def test_empty_second_domain_is_a_valid_fail_closed_current_cohort():
    from app.domain_adaptation.evidence_following_mpu import MpuStudyInput, build_mpu_design

    payload = _spec().model_dump(mode="json")
    payload["papers"] = [payload["papers"][0]]
    payload["tasks"] = []
    current = MpuStudyInput.model_validate(payload)

    design = build_mpu_design(current)

    assert design.ready is False
    assert design.primary_paper_counts == {"oer": 1, "organic-synthesis": 0}
    assert design.task_counts == {"oer": 0, "organic-synthesis": 0}
    assert design.prompts == []


def test_numeric_counterfactual_cases_compile_into_mpu_tasks():
    from app.domain_adaptation.consensus import ClaimPerturbationCase
    from app.scripts.prepare_evidence_following_mpu import compile_mpu_tasks

    paper = _paper("oer", "1")
    numeric = ClaimPerturbationCase(
        case_id="case-numeric",
        claim_key="claim-1",
        decision_id="decision-1",
        perturbation_type="numeric_replacement",
        expected_behavior="extract_replacement",
        target_model_aliases=["model-a", "model-b"],
        paper_id=paper.paper_id,
        source_chunk_id="methods-1",
        entity_type="materials",
        entity_key="NiFe catalyst",
        field_name="amount",
        original_source_value="10 mg",
        expected_source_value="11 mg",
        original_quote="10 mg of NiFe catalyst was used.",
        mutated_quote="11 mg of NiFe catalyst was used.",
    )
    deletion = numeric.model_copy(
        update={
            "case_id": "case-deletion",
            "perturbation_type": "evidence_deletion",
            "expected_behavior": "omit_or_abstain",
            "expected_source_value": None,
            "mutated_quote": "NiFe catalyst was used.",
        }
    )

    tasks = compile_mpu_tasks(papers=[paper], cases=[numeric, deletion])

    assert len(tasks) == 1
    assert tasks[0].task_id == "mpu:case-numeric"
    assert tasks[0].paper_identity.endswith(f"DOI {paper.doi}")
    assert tasks[0].replacement_value == "11 mg"
    assert tasks[0].source_evidence_sha256

    conflicting = numeric.model_copy(
        update={
            "case_id": "case-conflicting-occurrence",
            "original_source_value": "20 mg",
            "expected_source_value": "21 mg",
            "original_quote": "20 mg of NiFe catalyst was used elsewhere.",
            "mutated_quote": "21 mg of NiFe catalyst was used elsewhere.",
        }
    )
    assert compile_mpu_tasks(papers=[paper], cases=[numeric, conflicting]) == []


def test_prepare_mpu_input_compiles_existing_cases_without_overwrite(tmp_path):
    from app.domain_adaptation.consensus import ClaimPerturbationCase
    from app.scripts.prepare_evidence_following_mpu import prepare_evidence_following_mpu

    spec = _spec()
    spec.tasks = []
    input_path = tmp_path / "base.json"
    input_path.write_text(json.dumps(spec.model_dump(mode="json")))
    case = ClaimPerturbationCase(
        case_id="case-numeric",
        claim_key="claim-1",
        decision_id="decision-1",
        perturbation_type="numeric_replacement",
        expected_behavior="extract_replacement",
        target_model_aliases=["model-a", "model-b"],
        paper_id=spec.papers[0].paper_id,
        source_chunk_id="methods-1",
        entity_type="materials",
        entity_key="catalyst",
        field_name="amount",
        original_source_value="10 mg",
        expected_source_value="11 mg",
        original_quote="10 mg of catalyst was used.",
        mutated_quote="11 mg of catalyst was used.",
    )
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text(json.dumps(case.model_dump(mode="json")) + "\n")
    output_path = tmp_path / "compiled.json"

    result = prepare_evidence_following_mpu(
        input_path=input_path,
        case_paths=[cases_path],
        output_path=output_path,
    )

    assert result["compiled_task_count"] == 1
    assert json.loads(output_path.read_text())["tasks"][0]["task_id"] == (
        "mpu:case-numeric"
    )
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        prepare_evidence_following_mpu(
            input_path=input_path,
            case_paths=[cases_path],
            output_path=output_path,
        )


def test_scoring_separates_exposure_evidence_following_and_fact_injection():
    from app.domain_adaptation.evidence_following_mpu import score_mpu_observations

    spec = _spec()
    scores = score_mpu_observations(spec, _complete_observations(spec))
    indexed = {(item.task_id, item.model_alias): item for item in scores}

    model_a = indexed[("task-oer-1", "model-a")]
    assert model_a.closed_book_knowledge is True
    assert model_a.blind_domain_prior is False
    assert model_a.exposure_score == 1
    assert model_a.evidence_followed is True
    assert model_a.fact_injected_knowledge is True
    assert model_a.fact_injected_evidence_followed is False

    model_b = indexed[("task-oer-1", "model-b")]
    assert model_b.closed_book_knowledge is False
    assert model_b.exposure_score == 0
    assert model_b.evidence_followed is False

    stale = _complete_observations(spec)
    stale[0] = stale[0].model_copy(update={"prompt_sha256": "f" * 64})
    with pytest.raises(ValueError, match="prompt hash"):
        score_mpu_observations(spec, stale)

    from app.domain_adaptation.evidence_following_mpu import MpuObservation

    tampered = _complete_observations(spec)[0].model_dump(mode="json")
    tampered["response_sha256"] = "f" * 64
    with pytest.raises(ValidationError, match="response hash"):
        MpuObservation.model_validate(tampered)


def test_analysis_is_paired_clustered_and_never_claims_unidentified_results():
    from app.domain_adaptation.evidence_following_mpu import analyze_mpu

    spec = _spec()
    report = analyze_mpu(spec, _complete_observations(spec))

    assert report.analysis_ready is True
    assert report.missing_observation_count == 0
    assert len(report.model_domain_summaries) == 4
    assert report.fact_injection.knowledge_delta == pytest.approx(0.5)
    assert report.fact_injection.evidence_following_delta == pytest.approx(-0.5)
    assert report.fact_injection.paired_item_count == 4
    assert report.cross_domain.model_count == 2
    assert report.cross_domain.rank_correlation is None
    assert report.cross_domain.mean_absolute_rate_gap_interval == [0.0, 0.0]
    assert report.cross_domain.trait_supported is False
    assert report.knowledge_dissociation.supported is False
    assert "does not establish" in report.claims_boundary

    incomplete = _complete_observations(spec)[:-1]
    failed = analyze_mpu(spec, incomplete)
    assert failed.analysis_ready is False
    assert failed.missing_observation_count == 1
    assert failed.cross_domain.trait_supported is False
    assert failed.fact_injection.pareto_tradeoff_supported is False


def test_artifact_builder_is_content_addressed_and_non_overwriting(tmp_path):
    from app.scripts.build_evidence_following_mpu import build_evidence_following_mpu

    spec = _spec()
    input_path = tmp_path / "study.json"
    observations_path = tmp_path / "observations.jsonl"
    input_path.write_text(json.dumps(spec.model_dump(mode="json")))
    observations_path.write_text(
        "".join(
            json.dumps(item.model_dump(mode="json")) + "\n"
            for item in _complete_observations(spec)
        )
    )
    output = tmp_path / "artifact"

    result = build_evidence_following_mpu(
        input_path=input_path,
        observations_path=observations_path,
        output_dir=output,
    )

    assert result["design_ready"] is True
    assert result["analysis_ready"] is True
    assert (output / "design/prompts.jsonl").is_file()
    assert (output / "analysis/item_scores.jsonl").is_file()
    assert (output / "reports/mpu_report.json").is_file()
    assert (output / "inputs/study.json").is_file()
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["study_sha256"]
    assert manifest["observations_sha256"]
    assert "future_scope_exclusion" in manifest
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        build_evidence_following_mpu(
            input_path=input_path,
            observations_path=observations_path,
            output_dir=output,
        )


def test_mpu_readers_reject_non_regular_inputs():
    from pathlib import Path

    device = Path("/dev/zero")
    if not device.exists():
        pytest.skip("No non-regular zero device on this platform")

    from app.scripts.build_evidence_following_mpu import _read_bounded as build_read
    from app.scripts.prepare_evidence_following_mpu import _read_bounded as prepare_read

    with pytest.raises(ValueError, match="regular file"):
        build_read(device, 100)
    with pytest.raises(ValueError, match="regular file"):
        prepare_read(device)
