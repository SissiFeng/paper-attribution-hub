"""Learned classifier (v0.7).

A small calibrated classifier that takes the 13 hand-engineered features the
rules engine already computes and predicts {CORE, RELATED, ADJACENT,
EXCLUDE}. The rules engine still runs first; if the learned model is much
more confident on a different label, it overrides — otherwise the rules win.

Two backends, switchable via env:

    PAS_LEARNED_BACKEND=sklearn    # default, multinomial logistic + Platt
    PAS_LEARNED_BACKEND=lightgbm   # gradient boosting

Both expose the same `LearnedClassifier` interface. The training data comes
from `data/eval_labels.csv` + the `human_reviews` table; new reviewer
decisions feed back via the active learning loop.

The model file lives at `data/learned_classifier.joblib` (path overridable
via `PAS_LEARNED_MODEL_PATH`). Missing model = no override, system runs
exactly like the rules-only pipeline.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.config import DATA_DIR

FEATURE_ORDER = [
    "author_score",
    "institution_score",
    "topic_score",
    "fulltext_evidence_score",
    "network_score",
    "citation_score",
    "topic_density",
    "negated_topic_hits",
    "disqualifying_count",
    "n_ac_authors",
    "n_partner_inst",
    "has_funding_evidence",
    "year",
    "provenance_prior",
]


LABELS_ORDER = [
    "CORE_RELEVANT",
    "RELATED_RELEVANT",
    "ADJACENT",
    "UNCERTAIN",
    "EXCLUDE",
]


def _model_path() -> Path:
    return Path(
        os.environ.get(
            "PAS_LEARNED_MODEL_PATH",
            str(DATA_DIR / "learned_classifier.joblib"),
        )
    )


def _backend() -> str:
    return os.environ.get("PAS_LEARNED_BACKEND", "sklearn").lower()


# ---------------------------------------------------------------------------
# Backend interface
# ---------------------------------------------------------------------------


@dataclass
class LearnedClassifier:
    """Wraps either a sklearn pipeline or a lightgbm Booster + label map."""

    backend: str
    model: Any
    labels: list[str]
    # Year mean/std stored for numerical stability when "year" is a raw int.
    year_mean: float = 2020.0
    year_std: float = 4.0

    # ------------------------------------------------------------------ #
    # Prediction                                                         #
    # ------------------------------------------------------------------ #

    def predict(self, features: dict[str, float]) -> tuple[str, float]:
        x = self._featurize(features)
        if self.backend == "sklearn":
            proba = self.model.predict_proba([x])[0]
        elif self.backend == "lightgbm":
            # lightgbm Booster.predict on multiclass returns class probs.
            proba = self.model.predict([x])[0]
        else:
            raise ValueError(f"Unknown backend {self.backend}")
        idx = int(np.argmax(proba))
        return self.labels[idx], float(proba[idx])

    def predict_proba(self, features: dict[str, float]) -> dict[str, float]:
        x = self._featurize(features)
        if self.backend == "sklearn":
            proba = self.model.predict_proba([x])[0]
        elif self.backend == "lightgbm":
            proba = self.model.predict([x])[0]
        else:
            raise ValueError(f"Unknown backend {self.backend}")
        return {label: float(p) for label, p in zip(self.labels, proba)}

    def _featurize(self, features: dict[str, float]) -> np.ndarray:
        vec = []
        for name in FEATURE_ORDER:
            val = float(features.get(name, 0.0))
            if name == "year":
                val = (val - self.year_mean) / max(self.year_std, 1e-6)
            vec.append(val)
        return np.asarray(vec, dtype=np.float32)


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


def train_from_examples(
    examples: list[dict],
    *,
    backend: str | None = None,
) -> LearnedClassifier:
    """`examples` is a list of {features..., label} dicts.

    Returns a trained LearnedClassifier ready to save.
    """
    backend = (backend or _backend()).lower()
    X = np.asarray(
        [[ex.get(name, 0.0) for name in FEATURE_ORDER] for ex in examples],
        dtype=np.float32,
    )
    y_raw = [ex["label"] for ex in examples]
    labels = sorted(set(y_raw), key=LABELS_ORDER.index)
    label_to_int = {label: i for i, label in enumerate(labels)}
    y = np.asarray([label_to_int[l] for l in y_raw], dtype=np.int64)

    # Year normalization.
    years = X[:, FEATURE_ORDER.index("year")]
    year_mean = float(years[years > 0].mean()) if (years > 0).any() else 2020.0
    year_std = float(years[years > 0].std()) if (years > 0).any() else 4.0
    if year_std < 1e-6:
        year_std = 1.0
    X[:, FEATURE_ORDER.index("year")] = (
        years - year_mean
    ) / year_std

    if backend == "sklearn":
        from sklearn.linear_model import LogisticRegression
        from sklearn.calibration import CalibratedClassifierCV
        from sklearn.preprocessing import StandardScaler
        from sklearn.pipeline import Pipeline

        base = Pipeline(
            steps=[
                ("scaler", StandardScaler(with_mean=True)),
                (
                    "lr",
                    LogisticRegression(
                        solver="lbfgs",
                        max_iter=500,
                        C=1.0,
                    ),
                ),
            ]
        )
        n_examples = len(examples)
        smallest_class = min(np.bincount(y).tolist()) if len(y) else 0
        if n_examples >= 20 and smallest_class >= 2:
            # Platt scaling via CV requires multiple examples per class.
            method = "sigmoid" if smallest_class >= 3 else "isotonic"
            try:
                model = CalibratedClassifierCV(
                    base, method=method, cv=min(3, smallest_class)
                )
                model.fit(X, y)
            except Exception:
                model = base.fit(X, y)
        else:
            model = base.fit(X, y)
        return LearnedClassifier(
            backend="sklearn",
            model=model,
            labels=labels,
            year_mean=year_mean,
            year_std=year_std,
        )

    if backend == "lightgbm":
        try:
            import lightgbm as lgb  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "lightgbm is not installed. "
                "`pip install lightgbm` or switch PAS_LEARNED_BACKEND to sklearn."
            ) from e

        params = {
            "objective": "multiclass",
            "num_class": len(labels),
            "metric": "multi_logloss",
            "verbose": -1,
            "learning_rate": 0.05,
            "num_leaves": 15,
            "min_data_in_leaf": 1,
            "feature_pre_filter": False,
        }
        train_set = lgb.Dataset(X, label=y)
        booster = lgb.train(params, train_set, num_boost_round=200)
        return LearnedClassifier(
            backend="lightgbm",
            model=booster,
            labels=labels,
            year_mean=year_mean,
            year_std=year_std,
        )

    raise ValueError(f"Unknown backend {backend}")


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def save_model(clf: LearnedClassifier, path: Path | None = None) -> Path:
    target = Path(path) if path is not None else _model_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    import joblib

    payload = {
        "backend": clf.backend,
        "labels": clf.labels,
        "year_mean": clf.year_mean,
        "year_std": clf.year_std,
        "feature_order": FEATURE_ORDER,
    }
    if clf.backend == "sklearn":
        payload["model"] = clf.model
    elif clf.backend == "lightgbm":
        # lightgbm Booster has its own serializer; embed the string.
        payload["model_string"] = clf.model.model_to_string()
    joblib.dump(payload, target)
    return target


def load_model(path: Path | None = None) -> LearnedClassifier | None:
    target = Path(path) if path is not None else _model_path()
    if not target.exists():
        return None
    import joblib

    payload = joblib.load(target)
    backend = payload.get("backend", "sklearn")
    if backend == "sklearn":
        return LearnedClassifier(
            backend="sklearn",
            model=payload["model"],
            labels=payload["labels"],
            year_mean=payload.get("year_mean", 2020.0),
            year_std=payload.get("year_std", 4.0),
        )
    if backend == "lightgbm":
        import lightgbm as lgb  # type: ignore

        booster = lgb.Booster(model_str=payload["model_string"])
        return LearnedClassifier(
            backend="lightgbm",
            model=booster,
            labels=payload["labels"],
            year_mean=payload.get("year_mean", 2020.0),
            year_std=payload.get("year_std", 4.0),
        )
    return None


def load_default_model() -> LearnedClassifier | None:
    """Convenience used by relevance_classifier.py."""
    try:
        return load_model()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Building the training set from eval_labels + HumanReview
# ---------------------------------------------------------------------------


def build_training_set(session, eval_labels_csv: Path | None = None) -> list[dict]:
    """Materialize feature rows for every paper that has a gold or human label.

    Sources (later overrides earlier):
      1. eval_labels.csv
      2. human_reviews table
    """
    from app.models import HumanReview, Paper
    from sqlalchemy import select
    from app.services.relevance_classifier import (
        _features_for_learned,
        _classify_paper,
    )
    from app.services.author_matcher import AuthorMatcher
    from app.services.institution_matcher import InstitutionMatcher
    from app.services.topic_classifier import TopicClassifier
    from app.services.graph_service import compute_graph_signals
    from app.models import Author, Institution, Topic, PaperEvidence

    if eval_labels_csv is None:
        from app.config import settings as _settings

        eval_labels_csv = _settings.eval_labels_csv

    gold: dict[str, str] = {}
    try:
        import pandas as pd

        if Path(eval_labels_csv).exists():
            df = pd.read_csv(eval_labels_csv)
            for _, row in df.iterrows():
                pid = str(row["paper_id"]).strip()
                lbl = str(row["gold_label"]).strip()
                if lbl in LABELS_ORDER:
                    gold[pid] = lbl
    except Exception:
        pass

    # Override with reviewer labels.
    for hr in session.execute(select(HumanReview)).scalars():
        if hr.human_label in LABELS_ORDER:
            gold[hr.paper_id] = hr.human_label

    if not gold:
        return []

    authors = list(session.execute(select(Author)).scalars())
    institutions = list(session.execute(select(Institution)).scalars())
    topics = list(session.execute(select(Topic)).scalars())
    author_matcher = AuthorMatcher(authors)
    institution_matcher = InstitutionMatcher(institutions)
    topic_classifier = TopicClassifier(topics)
    evidence_index: dict[str, list] = {}
    for ev in session.execute(select(PaperEvidence)).scalars():
        evidence_index.setdefault(ev.paper_id, []).append(ev)
    graph_signals = compute_graph_signals(session)

    examples: list[dict] = []
    for paper in session.execute(select(Paper)).scalars():
        if paper.id not in gold:
            continue
        result = _classify_paper(
            paper,
            author_matcher,
            institution_matcher,
            topic_classifier,
            evidence_index=evidence_index,
            graph_signals=graph_signals.get(paper.id),
        )
        feats = _features_for_learned(paper, result)
        feats["label"] = gold[paper.id]
        examples.append(feats)
    return examples
