"""Compare base, static SFT, and student-error-conditioned distillation.

This is a small, reproducible experiment for the OER Task Suite. It uses a
paper-disjoint evaluation set and an equal-compute static-SFT control. The
on-policy variant mines hard examples from the current student's own rollouts;
it is sequence-level hard-example distillation, not token-level reverse-KL GKD.
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from app.domain_adaptation.distillation import (
    PredictionScore,
    build_adaptation_task_sets,
    build_task_prompt,
    canonical_response,
    require_paper_disjoint,
    score_task_prediction,
    select_on_policy_hard_tasks,
    split_seed_and_rollout_tasks,
    stratified_tasks,
    system_instruction,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PACKAGE = (
    PROJECT_ROOT
    / "outputs/domain-adapters/oer-electrocatalysis/0.1.0-pilot/heuristic-baseline"
)
DEFAULT_OUTPUT = DEFAULT_PACKAGE / "post-training/smollm2-360m-pilot"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a paper-disjoint OER distillation comparison."
    )
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--model-id", default="HuggingFaceTB/SmolLM2-360M-Instruct"
    )
    parser.add_argument("--device", choices=("auto", "mps", "cpu"), default="auto")
    parser.add_argument("--max-train-tasks", type=int, default=12)
    parser.add_argument("--max-rollout-tasks", type=int, default=12)
    parser.add_argument("--max-eval-tasks", type=int, default=9)
    parser.add_argument("--max-hard-tasks", type=int, default=12)
    parser.add_argument("--max-replay-tasks", type=int, default=3)
    parser.add_argument("--max-sequence-length", type=int, default=1536)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--sft-epochs", type=int, default=2)
    parser.add_argument("--correction-epochs", type=int, default=1)
    parser.add_argument("--learning-rate", type=float, default=5e-5)
    parser.add_argument("--correction-learning-rate", type=float, default=2e-5)
    parser.add_argument("--seed", type=int, default=23)
    return parser.parse_args()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _messages(task: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system_instruction()},
        {"role": "user", "content": build_task_prompt(task)},
    ]


def _token_ids(tokenizer, messages, *, add_generation_prompt: bool) -> list[int]:
    ids = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=add_generation_prompt,
        return_dict=False,
    )
    if not isinstance(ids, list):
        raise TypeError("Tokenizer chat template did not return token IDs")
    return ids


def _training_example(tokenizer, task: dict[str, Any]) -> tuple[list[int], list[int]]:
    prompt_messages = _messages(task)
    full_messages = prompt_messages + [
        {"role": "assistant", "content": canonical_response(task["response"])}
    ]
    prompt_ids = _token_ids(
        tokenizer, prompt_messages, add_generation_prompt=True
    )
    full_ids = _token_ids(tokenizer, full_messages, add_generation_prompt=False)
    if full_ids[: len(prompt_ids)] != prompt_ids:
        raise ValueError("Chat template target does not extend the prompt prefix")
    labels = [-100] * len(prompt_ids) + full_ids[len(prompt_ids) :]
    return full_ids, labels


def _eligible_tasks(
    tokenizer,
    tasks: list[dict[str, Any]],
    *,
    max_sequence_length: int,
    max_new_tokens: int,
) -> list[dict[str, Any]]:
    eligible: list[dict[str, Any]] = []
    for task in tasks:
        full_ids, labels = _training_example(tokenizer, task)
        response_length = sum(label != -100 for label in labels)
        if (
            len(full_ids) <= max_sequence_length
            and response_length <= max_new_tokens
        ):
            eligible.append(task)
    return eligible


def _device(torch, requested: str) -> str:
    if requested == "mps":
        if not torch.backends.mps.is_available():
            raise RuntimeError("MPS was requested but is unavailable")
        return "mps"
    if requested == "auto" and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _train(
    *,
    torch,
    model,
    tokenizer,
    tasks: list[dict[str, Any]],
    device: str,
    epochs: int,
    learning_rate: float,
    seed: int,
) -> dict[str, Any]:
    if not tasks or epochs <= 0:
        return {"steps": 0, "mean_loss": None, "losses": []}
    model.train()
    model.config.use_cache = False
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    losses: list[float] = []
    generator = torch.Generator(device="cpu").manual_seed(seed)
    for _epoch in range(epochs):
        order = torch.randperm(len(tasks), generator=generator).tolist()
        for index in order:
            input_ids, labels = _training_example(tokenizer, tasks[index])
            input_tensor = torch.tensor([input_ids], dtype=torch.long, device=device)
            label_tensor = torch.tensor([labels], dtype=torch.long, device=device)
            attention_mask = torch.ones_like(input_tensor)
            optimizer.zero_grad(set_to_none=True)
            output = model(
                input_ids=input_tensor,
                attention_mask=attention_mask,
                labels=label_tensor,
            )
            output.loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            losses.append(float(output.loss.detach().cpu()))
    model.config.use_cache = True
    return {
        "steps": len(losses),
        "mean_loss": sum(losses) / len(losses),
        "losses": losses,
    }


def _predict(
    *,
    torch,
    model,
    tokenizer,
    tasks: list[dict[str, Any]],
    device: str,
    max_new_tokens: int,
) -> tuple[dict[str, str], dict[str, PredictionScore]]:
    model.eval()
    predictions: dict[str, str] = {}
    scores: dict[str, PredictionScore] = {}
    for task in tasks:
        prompt_ids = _token_ids(
            tokenizer, _messages(task), add_generation_prompt=True
        )
        input_tensor = torch.tensor([prompt_ids], dtype=torch.long, device=device)
        attention_mask = torch.ones_like(input_tensor)
        with torch.inference_mode():
            generated = model.generate(
                input_ids=input_tensor,
                attention_mask=attention_mask,
                do_sample=False,
                max_new_tokens=max_new_tokens,
                eos_token_id=tokenizer.eos_token_id,
                pad_token_id=tokenizer.pad_token_id,
            )
        completion = tokenizer.decode(
            generated[0, len(prompt_ids) :], skip_special_tokens=True
        ).strip()
        task_id = str(task["task_id"])
        predictions[task_id] = completion
        scores[task_id] = score_task_prediction(task, completion)
    return predictions, scores


def _aggregate(scores: dict[str, PredictionScore]) -> dict[str, Any]:
    values = list(scores.values())
    if not values:
        return {"task_count": 0}
    return {
        "task_count": len(values),
        "json_valid_rate": sum(item.json_valid for item in values) / len(values),
        "exact_match_rate": sum(item.exact_match for item in values) / len(values),
        "field_precision": sum(item.field_precision for item in values) / len(values),
        "field_recall": sum(item.field_recall for item in values) / len(values),
        "field_f1": sum(item.field_f1 for item in values) / len(values),
        "grounded_leaf_rate": sum(item.grounded_leaf_rate for item in values)
        / len(values),
    }


def _write_predictions(
    path: Path,
    tasks: list[dict[str, Any]],
    predictions: dict[str, str],
    scores: dict[str, PredictionScore],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for task in tasks:
        task_id = str(task["task_id"])
        rows.append(
            {
                "task_id": task_id,
                "task_type": task["task_type"],
                "paper_id": task["paper_id"],
                "prediction": predictions[task_id],
                "expected": task["response"],
                "score": asdict(scores[task_id]),
            }
        )
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        )
    )


def main() -> int:
    args = parse_args()
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = _device(torch, args.device)
    tokenizer = AutoTokenizer.from_pretrained(args.model_id, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.model_id, local_files_only=True
    )
    model = cast(Any, model).to(torch.device(device))

    raw_train = _read_jsonl(args.package / "tasks/sft/train.jsonl")
    raw_eval = _read_jsonl(args.package / "tasks/evaluation/eval.jsonl")
    require_paper_disjoint(raw_train, raw_eval)
    eligible_train = _eligible_tasks(
        tokenizer,
        raw_train,
        max_sequence_length=args.max_sequence_length,
        max_new_tokens=args.max_new_tokens,
    )
    eligible_eval = _eligible_tasks(
        tokenizer,
        raw_eval,
        max_sequence_length=args.max_sequence_length,
        max_new_tokens=args.max_new_tokens,
    )
    train_tasks, rollout_tasks = split_seed_and_rollout_tasks(
        eligible_train,
        max_seed_tasks=args.max_train_tasks,
        max_rollout_tasks=args.max_rollout_tasks,
    )
    eval_tasks = stratified_tasks(eligible_eval, max_tasks=args.max_eval_tasks)
    if not train_tasks or not rollout_tasks or not eval_tasks:
        raise ValueError("No eligible paper-disjoint train/evaluation tasks")

    all_predictions: dict[str, dict[str, str]] = {}
    all_scores: dict[str, dict[str, PredictionScore]] = {}

    base_predictions, base_scores = _predict(
        torch=torch,
        model=model,
        tokenizer=tokenizer,
        tasks=eval_tasks,
        device=device,
        max_new_tokens=args.max_new_tokens,
    )
    all_predictions["base"] = base_predictions
    all_scores["base"] = base_scores

    static_training = _train(
        torch=torch,
        model=model,
        tokenizer=tokenizer,
        tasks=train_tasks,
        device=device,
        epochs=args.sft_epochs,
        learning_rate=args.learning_rate,
        seed=args.seed,
    )
    static_predictions, static_scores = _predict(
        torch=torch,
        model=model,
        tokenizer=tokenizer,
        tasks=eval_tasks,
        device=device,
        max_new_tokens=args.max_new_tokens,
    )
    all_predictions["static_sft"] = static_predictions
    all_scores["static_sft"] = static_scores

    _rollout_predictions, rollout_scores = _predict(
        torch=torch,
        model=model,
        tokenizer=tokenizer,
        tasks=rollout_tasks,
        device=device,
        max_new_tokens=args.max_new_tokens,
    )
    hard_tasks = select_on_policy_hard_tasks(
        rollout_tasks, rollout_scores, max_tasks=args.max_hard_tasks
    )
    if not hard_tasks:
        hard_tasks = rollout_tasks[:1]

    static_state = {
        key: value.detach().cpu().clone()
        for key, value in model.state_dict().items()
    }
    matched_tasks, on_policy_tasks, replay_tasks = build_adaptation_task_sets(
        seed_tasks=train_tasks,
        rollout_tasks=rollout_tasks,
        hard_tasks=hard_tasks,
        max_replay_tasks=args.max_replay_tasks,
    )
    matched_training = _train(
        torch=torch,
        model=model,
        tokenizer=tokenizer,
        tasks=matched_tasks,
        device=device,
        epochs=args.correction_epochs,
        learning_rate=args.correction_learning_rate,
        seed=args.seed + 1,
    )
    matched_predictions, matched_scores = _predict(
        torch=torch,
        model=model,
        tokenizer=tokenizer,
        tasks=eval_tasks,
        device=device,
        max_new_tokens=args.max_new_tokens,
    )
    all_predictions["matched_static_sft"] = matched_predictions
    all_scores["matched_static_sft"] = matched_scores

    model.load_state_dict(static_state)
    del static_state
    on_policy_training = _train(
        torch=torch,
        model=model,
        tokenizer=tokenizer,
        tasks=on_policy_tasks,
        device=device,
        epochs=args.correction_epochs,
        learning_rate=args.correction_learning_rate,
        seed=args.seed + 1,
    )
    on_policy_predictions, on_policy_scores = _predict(
        torch=torch,
        model=model,
        tokenizer=tokenizer,
        tasks=eval_tasks,
        device=device,
        max_new_tokens=args.max_new_tokens,
    )
    all_predictions["on_policy_hard_sft"] = on_policy_predictions
    all_scores["on_policy_hard_sft"] = on_policy_scores

    args.output.mkdir(parents=True, exist_ok=True)
    for variant in all_predictions:
        _write_predictions(
            args.output / "predictions" / f"{variant}.jsonl",
            eval_tasks,
            all_predictions[variant],
            all_scores[variant],
        )

    manifest = json.loads((args.package / "manifest.json").read_text())
    metrics = {variant: _aggregate(scores) for variant, scores in all_scores.items()}
    matched = metrics["matched_static_sft"]
    on_policy = metrics["on_policy_hard_sft"]
    promoted = (
        on_policy["field_f1"] > matched["field_f1"]
        and on_policy["grounded_leaf_rate"] >= matched["grounded_leaf_rate"]
        and on_policy["json_valid_rate"] >= matched["json_valid_rate"]
    )
    report = {
        "schema_version": "domain-distillation-experiment-v0.1",
        "claims_boundary": (
            "This compares student agreement with package targets. It is not "
            "an independent human assessment of scientific completeness."
        ),
        "package": str(args.package),
        "package_extraction": manifest.get("extraction"),
        "model_id": args.model_id,
        "device": device,
        "seed": args.seed,
        "config": {
            "max_sequence_length": args.max_sequence_length,
            "max_new_tokens": args.max_new_tokens,
            "learning_rate": args.learning_rate,
            "correction_learning_rate": args.correction_learning_rate,
            "sft_epochs": args.sft_epochs,
            "correction_epochs": args.correction_epochs,
        },
        "selection": {
            "raw_train_task_count": len(raw_train),
            "raw_evaluation_task_count": len(raw_eval),
            "eligible_train_task_count": len(eligible_train),
            "eligible_evaluation_task_count": len(eligible_eval),
            "train_task_ids": [task["task_id"] for task in train_tasks],
            "rollout_task_ids": [task["task_id"] for task in rollout_tasks],
            "evaluation_task_ids": [task["task_id"] for task in eval_tasks],
            "hard_task_ids": [task["task_id"] for task in hard_tasks],
            "matched_control_task_ids": [task["task_id"] for task in matched_tasks],
            "on_policy_adaptation_task_ids": [
                task["task_id"] for task in on_policy_tasks
            ],
            "replay_task_ids": [task["task_id"] for task in replay_tasks],
        },
        "training": {
            "static_sft": static_training,
            "matched_static_sft": matched_training,
            "on_policy_hard_sft": on_policy_training,
        },
        "metrics": metrics,
        "promotion": {
            "promoted": promoted,
            "comparison": "on_policy_hard_sft_vs_matched_static_sft",
            "rule": (
                "field_f1 must improve without reducing JSON validity or "
                "grounded leaf rate"
            ),
        },
        "method_label": (
            "student-error-conditioned sequence distillation with seed replay; "
            "not reverse-KL GKD"
        ),
    }
    (args.output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
