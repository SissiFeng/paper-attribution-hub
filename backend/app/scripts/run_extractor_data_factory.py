"""Run the budgeted structured-extractor data optimization factory.

Examples:
    python -m app.scripts.run_extractor_data_factory PROFILE --validate-only
    python -m app.scripts.run_extractor_data_factory PROFILE --out RUN_DIR --json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.config import REPO_ROOT
from app.services.extractor_data_factory import (
    FactoryError,
    load_factory_profile,
    run_extractor_data_factory,
    validate_factory_profile,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path, help="Benchmark-specific YAML profile.")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="New run directory. Defaults under backend/reports/autoresearch.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate frozen inputs and train/test boundaries without running commands.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume an interrupted run from --out after frozen-input checks.",
    )
    parser.add_argument(
        "--pass-env",
        action="append",
        default=[],
        metavar="NAME",
        help=(
            "Explicitly pass one environment variable to reviewed adapters. "
            "Repeat for multiple names; values are redacted from logs."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    args = parser.parse_args()

    try:
        profile = load_factory_profile(args.profile)
        if args.validate_only:
            report = validate_factory_profile(profile)
        else:
            if args.resume and args.out is None:
                raise FactoryError("--resume requires an explicit --out run directory.")
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            run_dir = args.out or (
                REPO_ROOT
                / "backend"
                / "reports"
                / "autoresearch"
                / "structured_extractor"
                / f"{profile.profile_id}--{timestamp}"
            )
            report = run_extractor_data_factory(
                profile,
                run_dir,
                resume=args.resume,
                pass_environment=tuple(args.pass_env),
            )
    except (FactoryError, OSError, ValueError) as exc:
        print(f"Structured extractor factory failed: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif args.validate_only:
        status = "VALID" if report["valid"] else "INVALID"
        boundary = report["boundary"]
        print(
            f"{status}: {report['profile_id']} "
            f"(train={boundary['train_records']}, "
            f"test={boundary['benchmark_records']}, "
            f"violations={len(boundary['violations'])})"
        )
        print(f"Evaluation profile: {report['evaluation_profile_sha256']}")
    else:
        selected = report["selected"]
        status = "SELECTED" if selected else "NO ELIGIBLE CHECKPOINT"
        print(
            f"{status}: attempts={len(report['attempts'])} "
            f"termination={report['termination_reason']}"
        )
        if selected:
            print(
                f"{selected['attempt_id']} -> {selected['checkpoint']} "
                f"{selected['primary_metric_name']}={selected['primary_metric']}"
            )
    return 0 if report.get("valid", report.get("selected") is not None) else 2


if __name__ == "__main__":
    raise SystemExit(main())
