from __future__ import annotations


def _task(task_id: str = "task-1") -> dict:
    return {
        "schema_version": "domain-adapter-task-v0.3",
        "task_id": task_id,
        "task_type": "materials_extraction",
        "paper_id": "DOI:10.1000_oer",
        "protocol_id": "protocol-1",
        "instruction": "Extract the explicitly reported materials.",
        "source_context": [
            {
                "evidence_id": "evidence-1",
                "paper_id": "DOI:10.1000_oer",
                "chunk_id": "methods-1",
                "quote": "The electrolyte was 1 M KOH.",
                "char_start": 0,
                "char_end": 29,
                "document_char_start": 100,
                "document_char_end": 129,
                "source_sha256": "0" * 64,
            }
        ],
        "response_schema": [
            {
                "name": "<string>",
                "amount": "<string|null>",
                "role": "<string|null>",
            }
        ],
        "response": [{"name": "KOH", "amount": "1 M", "role": "electrolyte"}],
        "evidence_ids": ["evidence-1"],
        "generation_policy": "extractive_only",
    }


def test_task_prompt_contains_source_but_not_target_response():
    from app.domain_adaptation.distillation import build_task_prompt

    prompt = build_task_prompt(_task())

    assert "The electrolyte was 1 M KOH." in prompt
    assert "Extract the explicitly reported materials." in prompt
    assert '"amount": "1 M"' not in prompt
    assert '"amount":"<string|null>"' in prompt
    assert '"name":"<string>"' in prompt
    assert "Return only valid JSON" in prompt


def test_prediction_score_detects_invalid_and_unsupported_output():
    from app.domain_adaptation.distillation import score_task_prediction

    exact = score_task_prediction(
        _task(),
        '```json\n[{"name":"KOH","amount":"1 M","role":"electrolyte"}]\n```',
    )
    hallucinated = score_task_prediction(
        _task(),
        '[{"name":"NaOH","amount":"1 M","role":"electrolyte"}]',
    )
    invalid = score_task_prediction(_task(), "not JSON")

    assert exact.json_valid is True
    assert exact.exact_match is True
    assert exact.field_f1 == 1.0
    assert exact.grounded_leaf_rate == 1.0
    assert hallucinated.json_valid is True
    assert hallucinated.exact_match is False
    assert 0.0 < hallucinated.field_f1 < 1.0
    assert 0.0 < hallucinated.grounded_leaf_rate < 1.0
    assert invalid.json_valid is False
    assert invalid.field_f1 == 0.0
    assert invalid.grounded_leaf_rate == 0.0


def test_hard_task_selection_is_deterministic_and_error_driven():
    from app.domain_adaptation.distillation import PredictionScore
    from app.domain_adaptation.distillation import select_on_policy_hard_tasks

    tasks = [_task("task-exact"), _task("task-invalid"), _task("task-partial")]
    scores = {
        "task-exact": PredictionScore(
            json_valid=True,
            exact_match=True,
            field_precision=1.0,
            field_recall=1.0,
            field_f1=1.0,
            grounded_leaf_rate=1.0,
        ),
        "task-invalid": PredictionScore(
            json_valid=False,
            exact_match=False,
            field_precision=0.0,
            field_recall=0.0,
            field_f1=0.0,
            grounded_leaf_rate=0.0,
        ),
        "task-partial": PredictionScore(
            json_valid=True,
            exact_match=False,
            field_precision=0.5,
            field_recall=0.5,
            field_f1=0.5,
            grounded_leaf_rate=1.0,
        ),
    }

    selected = select_on_policy_hard_tasks(tasks, scores, max_tasks=2)

    assert [task["task_id"] for task in selected] == [
        "task-invalid",
        "task-partial",
    ]


def test_stratified_tasks_are_balanced_and_paper_splits_are_disjoint():
    import pytest

    from app.domain_adaptation.distillation import require_paper_disjoint
    from app.domain_adaptation.distillation import stratified_tasks

    tasks = []
    for task_type in ("materials", "steps", "results"):
        for index in range(3):
            task = _task(f"{task_type}-{index}")
            task["task_type"] = task_type
            task["paper_id"] = f"paper-{task_type}-{index}"
            tasks.append(task)

    selected = stratified_tasks(tasks, max_tasks=4)

    assert [task["task_id"] for task in selected] == [
        "materials-0",
        "results-0",
        "steps-0",
        "materials-1",
    ]
    require_paper_disjoint(selected, [_task("eval")])
    with pytest.raises(ValueError, match="paper-disjoint"):
        require_paper_disjoint(selected, [selected[0]])


def test_seed_and_rollout_tasks_are_task_disjoint():
    from app.domain_adaptation.distillation import split_seed_and_rollout_tasks

    tasks = []
    for task_type in ("materials", "steps", "results"):
        for index in range(3):
            task = _task(f"{task_type}-{index}")
            task["task_type"] = task_type
            tasks.append(task)

    seed, rollout = split_seed_and_rollout_tasks(
        tasks,
        max_seed_tasks=3,
        max_rollout_tasks=3,
    )

    assert [task["task_id"] for task in seed] == [
        "materials-0",
        "results-0",
        "steps-0",
    ]
    assert [task["task_id"] for task in rollout] == [
        "materials-1",
        "results-1",
        "steps-1",
    ]
    assert {task["task_id"] for task in seed}.isdisjoint(
        {task["task_id"] for task in rollout}
    )


def test_adaptation_sets_have_equal_compute_and_shared_seed_replay():
    from app.domain_adaptation.distillation import build_adaptation_task_sets

    seed = [_task(f"seed-{index}") for index in range(3)]
    rollout = [_task(f"rollout-{index}") for index in range(3)]
    hard = [rollout[2]]

    matched, on_policy, replay = build_adaptation_task_sets(
        seed_tasks=seed,
        rollout_tasks=rollout,
        hard_tasks=hard,
        max_replay_tasks=1,
    )

    assert len(matched) == len(on_policy) == 2
    assert [task["task_id"] for task in replay] == ["seed-0"]
    assert matched[-1]["task_id"] == on_policy[-1]["task_id"] == "seed-0"
    assert on_policy[0]["task_id"] == "rollout-2"
    assert matched[0]["task_id"] == "rollout-0"
