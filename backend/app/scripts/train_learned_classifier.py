"""CLI: train the v0.7 learned classifier and save the artifact.

    python -m app.scripts.train_learned_classifier
    # or:
    PAS_LEARNED_BACKEND=lightgbm python -m app.scripts.train_learned_classifier

Reads features from `training_labels.csv` and the `human_reviews` table;
writes the trained model to `data/learned_classifier.joblib`.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from app.config import settings
from app.db import SessionLocal
from app.services.learned_classifier import (
    build_training_set,
    save_model,
    train_from_examples,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default=None, help="sklearn | lightgbm")
    parser.add_argument("--output", default=None, help="Output path for the model")
    parser.add_argument(
        "--stage1-through-round",
        type=int,
        choices=(1, 2, 3),
        default=None,
        help="Include only Stage 1 training batches through this round.",
    )
    args = parser.parse_args()
    if settings.sdl_stage1_only and args.stage1_through_round is None:
        raise SystemExit(
            "Stage 1 training requires --stage1-through-round 1, 2, or 3"
        )
    output = args.output
    if settings.sdl_stage1_only and output is None:
        output = str(
            Path("outputs/sdl-stage1")
            / f"round-{args.stage1_through_round}-candidate.joblib"
        )

    with SessionLocal() as session:
        examples = build_training_set(
            session,
            stage1_through_round=args.stage1_through_round,
        )
        if not examples:
            raise SystemExit(
                "No training examples found (need curated labels in "
                "training_labels.csv or human_reviews rows)."
            )
        clf = train_from_examples(examples, backend=args.backend)
        out = save_model(clf, output)
        print(f"Trained {clf.backend} on {len(examples)} examples → {out}")


if __name__ == "__main__":
    main()
