"""Freeze and optionally publish the SDL Stage 1 review-batch manifest."""
from __future__ import annotations

import argparse
import json

from app.config import settings
from app.db import SessionLocal, init_database
from app.services.sdl_stage1_service import (
    DEFAULT_FROZEN_TEST_COUNT,
    DEFAULT_SPLIT_SEED,
    DEFAULT_TRAIN_ROUND_COUNTS,
    DEFAULT_VALIDATION_COUNT,
    prepare_stage1_batches,
)


def _round_counts(value: str) -> tuple[int, ...]:
    try:
        counts = tuple(int(part.strip()) for part in value.split(",") if part.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("round counts must be comma-separated integers") from exc
    if not counts or any(count <= 0 for count in counts):
        raise argparse.ArgumentTypeError("round counts must all be positive")
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Freeze deterministic train/validation/test batches for Tier 1 SDL review."
    )
    parser.add_argument("--validation-count", type=int, default=DEFAULT_VALIDATION_COUNT)
    parser.add_argument("--frozen-test-count", type=int, default=DEFAULT_FROZEN_TEST_COUNT)
    parser.add_argument(
        "--train-round-counts",
        type=_round_counts,
        default=DEFAULT_TRAIN_ROUND_COUNTS,
        help="Comma-separated counts, default: 60,60,60",
    )
    parser.add_argument("--seed", default=DEFAULT_SPLIT_SEED)
    parser.add_argument(
        "--expected-total",
        type=int,
        default=398,
        help="Fail if the PDF-backed, deduplicated Tier 1 corpus count changed.",
    )
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not settings.sdl_stage1_only:
        raise ValueError("PAS_SDL_STAGE1_ONLY=true is required")
    init_database()
    with SessionLocal() as session:
        manifest = prepare_stage1_batches(
            session,
            validation_count=args.validation_count,
            frozen_test_count=args.frozen_test_count,
            train_round_counts=args.train_round_counts,
            seed=args.seed,
            expected_total=args.expected_total,
            persist=True,
        )
        published_key = None
        if args.publish:
            from app.services.s3_storage import put_file

            published_key = put_file(
                f"manifests/sdl-stage1/{manifest['manifest_id']}",
                "split-manifest.json",
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                ).encode("utf-8"),
                "application/json",
                require_s3=True,
            )
            if published_key is None:
                raise RuntimeError("failed to publish SDL Stage 1 manifest to S3")
        session.commit()

    output = {
        key: manifest[key]
        for key in (
            "manifest_id",
            "corpus_sha256",
            "unique_papers",
            "role_counts",
            "train_round_counts",
            "frozen_test_policy",
        )
    }
    output["published_key"] = published_key
    if args.json:
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(
            "SDL Stage 1 batches frozen:",
            f"manifest={manifest['manifest_id']}",
            f"counts={manifest['role_counts']}",
            f"rounds={manifest['train_round_counts']}",
            f"published={published_key or 'no'}",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
