"""CLI: train the v0.7 learned classifier and save the artifact.

    python -m app.scripts.train_learned_classifier
    # or:
    PAS_LEARNED_BACKEND=lightgbm python -m app.scripts.train_learned_classifier

Reads features from `eval_labels.csv` and `human_reviews` table; writes the
trained model to `data/learned_classifier.joblib`.
"""
from __future__ import annotations

import argparse

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
    args = parser.parse_args()

    with SessionLocal() as session:
        examples = build_training_set(session)
        if not examples:
            raise SystemExit(
                "No training examples found (need gold labels in "
                "eval_labels.csv or human_reviews rows)."
            )
        clf = train_from_examples(examples, backend=args.backend)
        out = save_model(clf, args.output)
        print(f"Trained {clf.backend} on {len(examples)} examples → {out}")


if __name__ == "__main__":
    main()
