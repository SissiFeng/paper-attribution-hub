"""Build non-overwriting source-grounded silver consensus artifacts."""

from __future__ import annotations

import argparse
import json
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from itertools import combinations
from pathlib import Path

from pydantic import BaseModel

from app.domain_adaptation.consensus import (
    ClaimPerturbationCase,
    ConsensusDecision,
    ModelClaimPerturbationResult,
    ModelFieldProposal,
    apply_perturbation_results,
    build_source_grounded_consensus,
    generate_perturbation_cases,
    load_model_proposals_from_package,
    proposal_claim_key,
)
from app.domain_adaptation.model_benchmark import (
    TeacherModelCandidate,
    compare_teacher_packages,
    load_benchmark_spec,
)
from app.scripts.benchmark_domain_teachers import (
    DEFAULT_SPEC,
    parse_package_dirs,
)


def _model_family(model_id: str) -> str:
    lowered = model_id.casefold()
    families = {
        "anthropic": "anthropic",
        "openai": "openai",
        "moonshot": "moonshot",
        "kimi": "moonshot",
        "deepseek": "deepseek",
        "qwen": "qwen",
        "zai": "zai",
        "glm": "zai",
        "amazon": "amazon",
    }
    return next(
        (family for marker, family in families.items() if marker in lowered),
        model_id.split(".", 1)[0].casefold(),
    )


def _json_bytes(value: dict) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _jsonl_bytes(rows: Sequence[BaseModel]) -> bytes:
    return "".join(
        json.dumps(
            row.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
        for row in rows
    ).encode("utf-8")


def _write_new(path: Path, content: bytes) -> None:
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


def _pairwise_agreement(
    proposals_by_model: Mapping[str, list[ModelFieldProposal]],
) -> dict:
    pairs: list[dict] = []
    for left_alias, right_alias in combinations(sorted(proposals_by_model), 2):
        left = {
            proposal_claim_key(item)
            for item in proposals_by_model[left_alias]
            if item.evidence_valid
        }
        right = {
            proposal_claim_key(item)
            for item in proposals_by_model[right_alias]
            if item.evidence_valid
        }
        union = left | right
        intersection = left & right
        pairs.append(
            {
                "left_model_alias": left_alias,
                "right_model_alias": right_alias,
                "left_valid_claim_count": len(left),
                "right_valid_claim_count": len(right),
                "shared_exact_claim_count": len(intersection),
                "exact_claim_jaccard": (
                    round(len(intersection) / len(union), 6) if union else None
                ),
            }
        )
    return {
        "schema_version": "domain-teacher-pairwise-agreement-v0.1",
        "claims_boundary": (
            "Exact-claim agreement measures source-grounded overlap, not "
            "scientific accuracy."
        ),
        "pairs": pairs,
    }


def build_teacher_consensus_artifacts(
    *,
    benchmark_id: str,
    models: list[TeacherModelCandidate],
    package_dirs: Mapping[str, str | Path],
    output_dir: str | Path,
    perturbation_results: list[ModelClaimPerturbationResult] | None = None,
    ignore_stale_perturbation_results: bool = False,
) -> dict:
    """Compare packages, build silver decisions, and preserve the gold boundary."""
    comparison = compare_teacher_packages(
        benchmark_id=benchmark_id,
        models=models,
        package_dirs=package_dirs,
    )
    model_by_alias = {item.alias: item for item in models}
    proposals_by_model: dict[str, list[ModelFieldProposal]] = {}
    for alias, package_dir in sorted(package_dirs.items()):
        if alias not in model_by_alias:
            raise ValueError(f"Unknown benchmark alias: {alias}")
        model = model_by_alias[alias]
        proposals_by_model[alias] = load_model_proposals_from_package(
            package_dir,
            model_alias=alias,
            model_family=_model_family(model.model_id),
        )
    proposals = [
        proposal
        for alias in sorted(proposals_by_model)
        for proposal in proposals_by_model[alias]
    ]
    initial_consensus = build_source_grounded_consensus(proposals)
    perturbation_cases = generate_perturbation_cases(
        proposals=proposals,
        decisions=initial_consensus.disputed,
    )
    valid_result_pairs = {
        (model_alias, case.decision_id)
        for case in perturbation_cases
        for model_alias in case.target_model_aliases
    }
    supplied_results = perturbation_results or []
    stale_results = [
        item
        for item in supplied_results
        if (item.model_alias, item.decision_id) not in valid_result_pairs
    ]
    if stale_results and not ignore_stale_perturbation_results:
        raise ValueError(
            "Perturbation results contain stale or non-target model decisions"
        )
    effective_results = [
        item
        for item in supplied_results
        if (item.model_alias, item.decision_id) in valid_result_pairs
    ]
    verified_proposals = (
        apply_perturbation_results(
            proposals,
            decisions=initial_consensus.disputed,
            results=effective_results,
        )
        if perturbation_results is not None
        else proposals
    )
    consensus = build_source_grounded_consensus(verified_proposals)
    decisions = [
        *consensus.accepted,
        *consensus.disputed,
        *consensus.abstained,
    ]
    pairwise = _pairwise_agreement(proposals_by_model)
    perturbation_counts = Counter(
        item.perturbation_status
        for item in verified_proposals
        if item.evidence_valid
    )
    perturbation_case_counts = Counter(
        item.perturbation_type for item in perturbation_cases
    )
    perturbation_report = {
        "schema_version": "domain-teacher-perturbation-report-v0.1",
        "status_counts": dict(sorted(perturbation_counts.items())),
        "case_count": len(perturbation_cases),
        "case_counts_by_type": dict(sorted(perturbation_case_counts.items())),
        "training_eligible_claim_count": sum(
            item.training_eligible for item in consensus.accepted
        ),
        "supplied_result_count": len(supplied_results),
        "applied_result_count": len(effective_results),
        "ignored_stale_result_count": len(stale_results),
        "claims_boundary": (
            "Not-tested perturbations cannot enter training-eligible Tier A."
        ),
    }
    report = {
        "schema_version": "domain-teacher-consensus-artifact-report-v0.1",
        "benchmark_id": benchmark_id,
        **consensus.report.model_dump(mode="json", exclude={"schema_version"}),
        "model_aliases": sorted(proposals_by_model),
        "comparability": comparison["comparability"],
        "scientific_ranking": comparison["scientific_ranking"],
        "training_eligible_count": sum(
            item.training_eligible for item in consensus.accepted
        ),
        "ignored_stale_perturbation_result_count": len(stale_results),
        "claims_boundary": (
            "Source-grounded consensus produces auditable silver knowledge. "
            "It does not establish scientific precision or recall without an "
            "independent external truth source."
        ),
    }
    output = Path(output_dir)
    outputs = {
        output / "consensus/model_claims.jsonl": _jsonl_bytes(
            verified_proposals
        ),
        output / "consensus/claim_clusters.jsonl": _jsonl_bytes(decisions),
        output / "consensus/accepted_silver.jsonl": _jsonl_bytes(
            consensus.accepted
        ),
        output / "consensus/disputed_claims.jsonl": _jsonl_bytes(
            consensus.disputed
        ),
        output / "consensus/abstained_claims.jsonl": _jsonl_bytes(
            consensus.abstained
        ),
        output / "consensus/perturbation_cases.jsonl": _jsonl_bytes(
            perturbation_cases
        ),
        output / "consensus/perturbation_results.jsonl": _jsonl_bytes(
            effective_results
        ),
        output / "consensus/pairwise_agreement.json": _json_bytes(pairwise),
        output / "reports/consensus_report.json": _json_bytes(report),
        output / "reports/perturbation_report.json": _json_bytes(
            perturbation_report
        ),
        output / "consensus/schemas/model_claims.schema.json": _json_bytes(
            ModelFieldProposal.model_json_schema()
        ),
        output / "consensus/schemas/decisions.schema.json": _json_bytes(
            ConsensusDecision.model_json_schema()
        ),
        output
        / "consensus/schemas/perturbation_cases.schema.json": _json_bytes(
            ClaimPerturbationCase.model_json_schema()
        ),
        output
        / "consensus/schemas/perturbation_results.schema.json": _json_bytes(
            ModelClaimPerturbationResult.model_json_schema()
        ),
    }
    existing = [str(path) for path in outputs if path.exists()]
    if existing:
        raise FileExistsError(
            "Refusing to overwrite existing consensus files: "
            + ", ".join(existing)
        )
    for path, content in outputs.items():
        _write_new(path, content)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build source-grounded multi-teacher silver consensus."
    )
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument(
        "--package",
        action="append",
        default=[],
        metavar="ALIAS=PATH",
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--perturbation-results",
        type=Path,
        default=None,
        help="Optional JSONL results from claim-level counterfactual checks.",
    )
    parser.add_argument(
        "--ignore-stale-perturbation-results",
        action="store_true",
        help=(
            "Drop results whose decisions or target models disappeared after a "
            "schema migration, and report the dropped count."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    spec = load_benchmark_spec(args.spec)
    report = build_teacher_consensus_artifacts(
        benchmark_id=spec.benchmark_id,
        models=spec.models,
        package_dirs=parse_package_dirs(args.package),
        output_dir=args.output,
        perturbation_results=(
            [
                ModelClaimPerturbationResult.model_validate_json(line)
                for line in args.perturbation_results.read_text(
                    encoding="utf-8"
                ).splitlines()
                if line.strip()
            ]
            if args.perturbation_results is not None
            else None
        ),
        ignore_stale_perturbation_results=(
            args.ignore_stale_perturbation_results
        ),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
