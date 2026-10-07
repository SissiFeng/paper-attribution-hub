"""Compile existing exact numeric counterfactual cases into an MPU study input."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path

from app.domain_adaptation.consensus import ClaimPerturbationCase
from app.domain_adaptation.evidence_following_mpu import (
    MpuInputSource,
    MpuPaper,
    MpuStudyInput,
    MpuTask,
)


MAX_INPUT_BYTES = 50_000_000
MAX_CASE_COUNT = 10_000


def _read_bounded(path: Path) -> bytes:
    with path.open("rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError(f"MPU input must be a regular file: {path}")
        content = handle.read(MAX_INPUT_BYTES + 1)
    if len(content) > MAX_INPUT_BYTES:
        raise ValueError(f"MPU input exceeds {MAX_INPUT_BYTES} bytes: {path}")
    return content


def compile_mpu_tasks(
    *,
    papers: list[MpuPaper],
    cases: list[ClaimPerturbationCase],
) -> list[MpuTask]:
    """Compile exact numeric replacement cases at the ingestion boundary."""
    paper_by_id = {item.paper_id: item for item in papers}
    if len(paper_by_id) != len(papers):
        raise ValueError("MPU task compiler received duplicate paper IDs")
    grouped: dict[
        tuple[str, str, str, str],
        list[ClaimPerturbationCase],
    ] = {}
    for case in cases:
        if case.perturbation_type != "numeric_replacement":
            continue
        key = (
            case.paper_id,
            case.entity_type,
            case.entity_key.casefold().strip(),
            case.field_name,
        )
        grouped.setdefault(key, []).append(case)
    eligible_cases: list[ClaimPerturbationCase] = []
    for group in grouped.values():
        original_values = {
            " ".join(item.original_source_value.casefold().split()) for item in group
        }
        if len(original_values) != 1:
            continue
        eligible_cases.append(min(group, key=lambda item: item.case_id))
    tasks: list[MpuTask] = []
    for case in sorted(eligible_cases, key=lambda item: item.case_id):
        if case.expected_source_value is None:
            raise ValueError("Numeric replacement case is missing its expected value")
        paper = paper_by_id.get(case.paper_id)
        if paper is None:
            raise ValueError(
                f"Numeric replacement case references unknown paper: {case.paper_id}"
            )
        tasks.append(
            MpuTask(
                task_id=f"mpu:{case.case_id}",
                paper_id=paper.paper_id,
                domain=paper.domain,
                field_type=case.field_name,
                question=(
                    f"What is the {case.field_name} for {case.entity_type} "
                    f"'{case.entity_key}'?"
                ),
                paper_identity=f"{paper.title}; DOI {paper.doi}",
                blind_context=(
                    f"A primary {paper.domain} experimental protocol containing "
                    f"{case.entity_type} '{case.entity_key}'."
                ),
                original_value=case.original_source_value,
                replacement_value=case.expected_source_value,
                counterfactual_evidence=case.mutated_quote,
                fact_injection=(
                    f"Prior domain memory for {paper.title}: the {case.field_name} "
                    f"for {case.entity_key} is {case.original_source_value}."
                ),
                source_evidence_sha256=hashlib.sha256(
                    case.original_quote.encode("utf-8")
                ).hexdigest(),
            )
        )
    task_ids = [item.task_id for item in tasks]
    if len(task_ids) != len(set(task_ids)):
        raise ValueError("Compiled MPU tasks contain duplicate IDs")
    return tasks


def _write_new(path: Path, content: bytes) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing MPU input: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary_path = Path(temporary.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def prepare_evidence_following_mpu(
    *,
    input_path: str | Path,
    case_paths: list[str | Path],
    output_path: str | Path,
) -> dict[str, object]:
    source = Path(input_path)
    source_bytes = _read_bounded(source)
    spec = MpuStudyInput.model_validate_json(source_bytes)
    cases: list[ClaimPerturbationCase] = []
    input_sources = [
        *spec.input_sources,
        MpuInputSource(
            role="base_study",
            sha256=hashlib.sha256(source_bytes).hexdigest(),
            path_hint=source.name,
        ),
    ]
    for raw_path in case_paths:
        path = Path(raw_path)
        content = _read_bounded(path)
        input_sources.append(
            MpuInputSource(
                role="counterfactual_cases",
                sha256=hashlib.sha256(content).hexdigest(),
                path_hint=path.name,
            )
        )
        cases.extend(
            ClaimPerturbationCase.model_validate_json(line)
            for line in content.decode("utf-8").splitlines()
            if line.strip()
        )
        if len(cases) > MAX_CASE_COUNT:
            raise ValueError(f"MPU preparation accepts at most {MAX_CASE_COUNT} cases")
    compiled = compile_mpu_tasks(papers=spec.papers, cases=cases)
    numeric_case_count = sum(
        item.perturbation_type == "numeric_replacement" for item in cases
    )
    by_id = {item.task_id: item for item in spec.tasks}
    for task in compiled:
        existing = by_id.get(task.task_id)
        if existing is not None and existing != task:
            raise ValueError(f"Conflicting MPU task ID: {task.task_id}")
        by_id[task.task_id] = task
    prepared = MpuStudyInput.model_validate(
        {
            **spec.model_dump(mode="json"),
            "tasks": [by_id[key].model_dump(mode="json") for key in sorted(by_id)],
            "input_sources": [item.model_dump(mode="json") for item in input_sources],
        }
    )
    destination = Path(output_path)
    content = (
        json.dumps(
            prepared.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    _write_new(destination, content)
    return {
        "output_path": str(destination),
        "source_task_count": len(spec.tasks),
        "compiled_task_count": len(compiled),
        "excluded_nonidentifiable_numeric_case_count": (
            numeric_case_count - len(compiled)
        ),
        "total_task_count": len(prepared.tasks),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compile numeric replacement cases into an MPU study input."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--cases", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = prepare_evidence_following_mpu(
        input_path=args.input,
        case_paths=args.cases,
        output_path=args.output,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
