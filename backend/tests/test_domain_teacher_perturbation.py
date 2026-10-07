from __future__ import annotations


def _case(*, perturbation_type: str, expected_source_value: str | None = None):
    from app.domain_adaptation.consensus import ClaimPerturbationCase

    return ClaimPerturbationCase(
        case_id=f"case-{perturbation_type}",
        claim_key="claim-1",
        decision_id="decision-1",
        perturbation_type=perturbation_type,
        expected_behavior=(
            "omit_or_abstain"
            if perturbation_type == "evidence_deletion"
            else "extract_replacement"
        ),
        target_model_aliases=["kimi", "opus"],
        paper_id="DOI:10.1000_perturbation",
        source_chunk_id="methods-1",
        entity_type="materials",
        entity_key="NiFe catalyst",
        field_name="amount",
        original_source_value="10 mg",
        expected_source_value=expected_source_value,
        original_quote="10 mg of NiFe catalyst was dispersed in ethanol.",
        mutated_quote=(
            " of NiFe catalyst was dispersed in ethanol."
            if perturbation_type == "evidence_deletion"
            else "11 mg of NiFe catalyst was dispersed in ethanol."
        ),
    )


class _FakeBedrockClient:
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.calls: list[dict] = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "output": {
                "message": {"content": [{"text": self.response_text}]}
            },
            "usage": {"inputTokens": 100, "outputTokens": 20},
            "stopReason": "end_turn",
        }


def test_batched_counterfactual_evaluation_is_fail_closed_and_value_exact():
    import json

    from app.domain_adaptation.model_benchmark import TeacherModelCandidate
    from app.domain_adaptation.perturbation import evaluate_perturbation_cases

    cases = [
        _case(perturbation_type="evidence_deletion"),
        _case(
            perturbation_type="numeric_replacement",
            expected_source_value="11 mg",
        ),
    ]
    clients = {
        "kimi.model": _FakeBedrockClient(
            json.dumps(
                {
                    "results": [
                        {"case_id": cases[0].case_id, "values": []},
                        {"case_id": cases[1].case_id, "values": ["11 mg"]},
                    ]
                }
            )
        ),
        "opus.model": _FakeBedrockClient(
            json.dumps(
                {
                    "results": [
                        {"case_id": cases[0].case_id, "values": ["10 mg"]},
                        {"case_id": cases[1].case_id, "values": ["12 mg"]},
                    ]
                }
            )
        ),
    }
    models = [
        TeacherModelCandidate(
            alias="kimi", model_id="kimi.model", region="us-east-1"
        ),
        TeacherModelCandidate(
            alias="opus", model_id="opus.model", region="us-east-1"
        ),
    ]

    run = evaluate_perturbation_cases(
        cases=cases,
        models=models,
        client_factory=lambda model: clients[model.model_id],
    )

    assert len(run.observations) == 4
    assert [item.model_alias for item in run.results] == ["kimi", "opus"]
    assert run.results[0].evidence_deletion_passed is True
    assert run.results[0].numeric_replacement_passed is True
    assert run.results[1].evidence_deletion_passed is False
    assert run.results[1].numeric_replacement_passed is False
    assert run.report.passed_model_claim_count == 1
    assert run.report.failed_model_claim_count == 1
    assert len(run.batches) == 2
    assert all(item.response_text for item in run.batches)


def test_invalid_or_incomplete_model_output_fails_every_missing_case():
    from app.domain_adaptation.model_benchmark import TeacherModelCandidate
    from app.domain_adaptation.perturbation import evaluate_perturbation_cases

    cases = [
        _case(perturbation_type="evidence_deletion"),
        _case(
            perturbation_type="numeric_replacement",
            expected_source_value="11 mg",
        ),
    ]
    client = _FakeBedrockClient('{"results":[]}')

    run = evaluate_perturbation_cases(
        cases=cases,
        models=[
            TeacherModelCandidate(
                alias="kimi", model_id="kimi.model", region="us-east-1"
            )
        ],
        client_factory=lambda _model: client,
    )

    assert [item.outcome for item in run.observations] == [
        "missing_result",
        "missing_result",
    ]
    assert run.results[0].evidence_deletion_passed is False
    assert run.results[0].numeric_replacement_passed is False
    assert run.report.invalid_observation_count == 2


def test_fenced_json_is_salvaged_but_malformed_json_is_a_parse_failure():
    import json

    from app.domain_adaptation.model_benchmark import TeacherModelCandidate
    from app.domain_adaptation.perturbation import evaluate_perturbation_cases

    case = _case(perturbation_type="evidence_deletion")
    model = TeacherModelCandidate(
        alias="kimi", model_id="kimi.model", region="us-east-1"
    )
    fenced = _FakeBedrockClient(
        "Here is the result:\n```json\n"
        + json.dumps(
            {"results": [{"case_id": case.case_id, "values": []}]}
        )
        + "\n```"
    )
    salvaged = evaluate_perturbation_cases(
        cases=[case],
        models=[model],
        client_factory=lambda _model: fenced,
    )
    malformed = evaluate_perturbation_cases(
        cases=[case],
        models=[model],
        client_factory=lambda _model: _FakeBedrockClient("not-json"),
    )

    assert salvaged.observations[0].outcome == "passed"
    assert salvaged.batches[0].parse_status == "salvaged"
    assert malformed.observations[0].outcome == "invalid_result"
    assert malformed.batches[0].parse_status == "invalid"


def test_one_mistyped_case_id_does_not_invalidate_the_rest_of_a_batch():
    import json

    from app.domain_adaptation.model_benchmark import TeacherModelCandidate
    from app.domain_adaptation.perturbation import evaluate_perturbation_cases

    cases = [
        _case(perturbation_type="evidence_deletion"),
        _case(
            perturbation_type="numeric_replacement",
            expected_source_value="11 mg",
        ),
    ]
    client = _FakeBedrockClient(
        json.dumps(
            {
                "results": [
                    {"case_id": cases[0].case_id, "values": []},
                    {"case_id": "mistyped-case-id", "values": ["11 mg"]},
                ]
            }
        )
    )

    run = evaluate_perturbation_cases(
        cases=cases,
        models=[
            TeacherModelCandidate(
                alias="kimi", model_id="kimi.model", region="us-east-1"
            )
        ],
        client_factory=lambda _model: client,
    )

    assert [item.outcome for item in run.observations] == [
        "passed",
        "missing_result",
    ]
    assert run.batches[0].parse_status == "salvaged"
    assert "mistyped-case-id" in (run.batches[0].diagnostic or "")

    from app.domain_adaptation.perturbation import replay_perturbation_batches

    replayed = replay_perturbation_batches(
        cases=cases,
        models=[
            TeacherModelCandidate(
                alias="kimi", model_id="kimi.model", region="us-east-1"
            )
        ],
        batches=run.batches,
    )
    assert [item.outcome for item in replayed.observations] == [
        "passed",
        "missing_result",
    ]
    assert replayed.report.invocation_count == 1


def test_perturbation_artifact_runner_selects_whole_decisions_and_never_overwrites(
    tmp_path,
):
    import json

    import pytest

    from app.domain_adaptation.model_benchmark import TeacherModelCandidate
    from app.scripts.run_teacher_perturbations import (
        run_teacher_perturbation_artifacts,
    )

    first_cases = [
        _case(perturbation_type="evidence_deletion"),
        _case(
            perturbation_type="numeric_replacement",
            expected_source_value="11 mg",
        ),
    ]
    second_case = first_cases[0].model_copy(
        update={
            "case_id": "case-second-decision",
            "claim_key": "claim-2",
            "decision_id": "decision-2",
        }
    )
    client = _FakeBedrockClient(
        json.dumps(
            {
                "results": [
                    {"case_id": first_cases[0].case_id, "values": []},
                    {"case_id": first_cases[1].case_id, "values": ["11 mg"]},
                ]
            }
        )
    )
    models = [
        TeacherModelCandidate(
            alias="kimi", model_id="kimi.model", region="us-east-1"
        )
    ]
    output = tmp_path / "perturbation-run"

    report = run_teacher_perturbation_artifacts(
        cases=[*first_cases, second_case],
        models=models,
        output_dir=output,
        client_factory=lambda _model: client,
        max_decisions=1,
    )

    assert report["case_count"] == 2
    assert report["passed_model_claim_count"] == 1
    assert len((output / "observations.jsonl").read_text().splitlines()) == 2
    assert len((output / "batches.jsonl").read_text().splitlines()) == 1
    assert len((output / "model_results.jsonl").read_text().splitlines()) == 1
    assert (output / "report.json").is_file()
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        run_teacher_perturbation_artifacts(
            cases=first_cases,
            models=models,
            output_dir=output,
            client_factory=lambda _model: client,
        )
