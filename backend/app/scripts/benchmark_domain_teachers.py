"""Preflight and compare evidence-bound domain teacher models."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from app.domain_adaptation.model_benchmark import (
    compare_teacher_packages,
    load_benchmark_spec,
    preflight_bedrock_models,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SPEC = (
    PROJECT_ROOT / "data/domain_adapters/oer_teacher_benchmark.json"
)


def parse_package_dirs(values: list[str]) -> dict[str, Path]:
    packages: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("Each package must use ALIAS=PATH")
        alias, raw_path = value.split("=", 1)
        if not alias or not raw_path:
            raise ValueError("Each package must use ALIAS=PATH")
        if alias in packages:
            raise ValueError(f"Duplicate package alias: {alias}")
        packages[alias] = Path(raw_path)
    return packages


def _write_json(path: Path, value: dict) -> None:
    content = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preflight or compare domain-adaptation teacher models."
    )
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser(
        "preflight", help="Check Bedrock access and minimal JSON output."
    )
    preflight.add_argument("--output", type=Path, required=True)
    preflight.add_argument(
        "--aws-profile", default=os.getenv("AWS_PROFILE", "pas-sdl0-dev")
    )
    preflight.add_argument("--read-timeout", type=int, default=60)

    compare = subparsers.add_parser(
        "compare", help="Compare completed model-specific packages."
    )
    compare.add_argument(
        "--package",
        action="append",
        default=[],
        metavar="ALIAS=PATH",
        help="Completed package; repeat once per model.",
    )
    compare.add_argument("--shared-gold-scores", type=Path, default=None)
    compare.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    spec = load_benchmark_spec(args.spec)
    if args.command == "preflight":
        import boto3  # type: ignore[import-untyped]
        from botocore.config import Config  # type: ignore[import-untyped]

        session = boto3.Session(profile_name=args.aws_profile)

        def client_factory(region: str):
            return session.client(
                "bedrock-runtime",
                region_name=region,
                config=Config(
                    connect_timeout=10,
                    read_timeout=args.read_timeout,
                    retries={"total_max_attempts": 2, "mode": "standard"},
                ),
            )

        report = preflight_bedrock_models(
            benchmark_id=spec.benchmark_id,
            models=spec.models,
            client_factory=client_factory,
        )
    else:
        shared_gold_scores = (
            json.loads(args.shared_gold_scores.read_text(encoding="utf-8"))
            if args.shared_gold_scores is not None
            else None
        )
        report = compare_teacher_packages(
            benchmark_id=spec.benchmark_id,
            models=spec.models,
            package_dirs=parse_package_dirs(args.package),
            shared_gold_scores=shared_gold_scores,
        )
    _write_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
