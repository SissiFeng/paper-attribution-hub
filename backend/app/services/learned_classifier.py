"""Learned classifier (v0.7).

A small calibrated classifier that takes the 13 hand-engineered features the
rules engine already computes and predicts {CORE, RELATED, ADJACENT,
EXCLUDE}. The rules engine still runs first; if the learned model is much
more confident on a different label, it overrides — otherwise the rules win.

Two backends, switchable via env:

    PAS_LEARNED_BACKEND=sklearn    # default, multinomial logistic + Platt
    PAS_LEARNED_BACKEND=lightgbm   # gradient boosting

Both expose the same `LearnedClassifier` interface. Training data comes from
the curated `data/training_labels.csv` file plus the `human_reviews` table.
The frozen `data/eval_labels.csv` holdout is never used as model-training
labels. Its paper IDs are read only as an exclusion set and never used as
labels or features.

The model file lives at `data/learned_classifier.joblib` (path overridable
via `PAS_LEARNED_MODEL_PATH`). Missing model = no override, system runs
exactly like the rules-only pipeline.
"""

from __future__ import annotations

import os
from io import BytesIO
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.classification_labels import (
    CLASSIFICATION_LABEL_ORDER,
    normalize_classification_label,
)
from app.config import DATA_DIR
from app.label_dataset import (
    ensure_disjoint_label_ids,
    ensure_distinct_label_paths,
    load_label_dataset,
    load_reserved_evaluation_ids,
)

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


LABELS_ORDER = list(CLASSIFICATION_LABEL_ORDER)

SKLEARN_LOGISTIC_CONFIG = {
    "solver": "lbfgs",
    "max_iter": 500,
    "C": 1.0,
}
SKLEARN_CALIBRATION_CONFIG = {
    "minimum_examples": 20,
    "minimum_class_support": 2,
    "sigmoid_minimum_class_support": 3,
    "maximum_cv_folds": 3,
}
LIGHTGBM_CONFIG = {
    "objective": "multiclass",
    "metric": "multi_logloss",
    "verbose": -1,
    "learning_rate": 0.05,
    "num_leaves": 15,
    "min_data_in_leaf": 1,
    "feature_pre_filter": False,
}
LIGHTGBM_BOOST_ROUNDS = 200


def training_configuration(backend: str, examples: list[dict] | None = None) -> dict:
    """Return the estimator and feature contract needed to replay training."""
    configuration: dict[str, Any] = {
        "backend": backend,
        "feature_order": list(FEATURE_ORDER),
        "label_order": list(LABELS_ORDER),
        "year_normalization": "positive-year mean/std; std floor 1e-6 then 1.0",
    }
    if backend == "sklearn":
        calibration: dict[str, Any] = dict(SKLEARN_CALIBRATION_CONFIG)
        if examples:
            counts: dict[str, int] = {}
            for example in examples:
                label = normalize_classification_label(example.get("label"))
                if label is not None:
                    counts[label] = counts.get(label, 0) + 1
            smallest_class = min(counts.values()) if counts else 0
            attempted_method = None
            attempted_cv = None
            if (
                len(examples) >= SKLEARN_CALIBRATION_CONFIG["minimum_examples"]
                and smallest_class
                >= SKLEARN_CALIBRATION_CONFIG["minimum_class_support"]
            ):
                attempted_method = (
                    "sigmoid"
                    if smallest_class
                    >= SKLEARN_CALIBRATION_CONFIG[
                        "sigmoid_minimum_class_support"
                    ]
                    else "isotonic"
                )
                attempted_cv = min(
                    SKLEARN_CALIBRATION_CONFIG["maximum_cv_folds"],
                    smallest_class,
                )
            calibration.update(
                observed_smallest_class=smallest_class,
                attempted_method=attempted_method,
                attempted_cv=attempted_cv,
            )
        configuration.update(
            estimator="StandardScaler+LogisticRegression",
            logistic_regression=dict(SKLEARN_LOGISTIC_CONFIG),
            calibration_policy=calibration,
        )
    elif backend == "lightgbm":
        configuration.update(
            estimator="lightgbm.Booster",
            parameters=dict(LIGHTGBM_CONFIG),
            num_boost_round=LIGHTGBM_BOOST_ROUNDS,
        )
    return configuration


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
    model_version: str | None = None

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
    y_raw = []
    for example in examples:
        label = normalize_classification_label(example["label"])
        if label is None:
            raise ValueError(f"Unsupported classification label: {example['label']}")
        y_raw.append(label)
    labels = sorted(set(y_raw), key=LABELS_ORDER.index)
    label_to_int = {label: i for i, label in enumerate(labels)}
    y = np.asarray([label_to_int[label] for label in y_raw], dtype=np.int64)

    # Year normalization.
    years = X[:, FEATURE_ORDER.index("year")]
    year_mean = float(years[years > 0].mean()) if (years > 0).any() else 2020.0
    year_std = float(years[years > 0].std()) if (years > 0).any() else 4.0
    if year_std < 1e-6:
        year_std = 1.0
    X[:, FEATURE_ORDER.index("year")] = (years - year_mean) / year_std

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
                    LogisticRegression(**SKLEARN_LOGISTIC_CONFIG),
                ),
            ]
        )
        n_examples = len(examples)
        smallest_class = min(np.bincount(y).tolist()) if len(y) else 0
        if (
            n_examples >= SKLEARN_CALIBRATION_CONFIG["minimum_examples"]
            and smallest_class
            >= SKLEARN_CALIBRATION_CONFIG["minimum_class_support"]
        ):
            # Platt scaling via CV requires multiple examples per class.
            method = (
                "sigmoid"
                if smallest_class
                >= SKLEARN_CALIBRATION_CONFIG[
                    "sigmoid_minimum_class_support"
                ]
                else "isotonic"
            )
            try:
                model = CalibratedClassifierCV(
                    base,
                    method=method,
                    cv=min(
                        SKLEARN_CALIBRATION_CONFIG["maximum_cv_folds"],
                        smallest_class,
                    ),
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
            **LIGHTGBM_CONFIG,
            "num_class": len(labels),
        }
        train_set = lgb.Dataset(X, label=y)
        booster = lgb.train(
            params,
            train_set,
            num_boost_round=LIGHTGBM_BOOST_ROUNDS,
        )
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
        "model_version": clf.model_version,
    }
    if clf.backend == "sklearn":
        payload["model"] = clf.model
    elif clf.backend == "lightgbm":
        # lightgbm Booster has its own serializer; embed the string.
        payload["model_string"] = clf.model.model_to_string()
    joblib.dump(payload, target)
    return target


def _classifier_from_payload(payload: dict) -> LearnedClassifier | None:
    backend = payload.get("backend", "sklearn")
    if backend == "sklearn":
        return LearnedClassifier(
            backend="sklearn",
            model=payload["model"],
            labels=payload["labels"],
            year_mean=payload.get("year_mean", 2020.0),
            year_std=payload.get("year_std", 4.0),
            model_version=payload.get("model_version"),
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
            model_version=payload.get("model_version"),
        )
    return None


def load_model(path: Path | None = None) -> LearnedClassifier | None:
    target = Path(path) if path is not None else _model_path()
    if not target.exists():
        return None
    import joblib

    return _classifier_from_payload(joblib.load(target))


class AuthoritativeModelError(RuntimeError):
    """The database declares a production model that cannot be verified."""


def load_authoritative_model(session) -> tuple[LearnedClassifier, str]:
    """Load and verify the database-authoritative production artifact.

    A declared production run is never allowed to fall back to the local file
    cache. Callers that need legacy behavior must do so only when no database
    production run has been declared.
    """
    import hashlib
    import joblib

    from app.models import ModelTrainingRun, ModelTrainingState

    state = session.get(ModelTrainingState, "learned_classifier")
    if state is None or not state.production_run_id:
        raise AuthoritativeModelError("no database production model is declared")
    run = session.get(ModelTrainingRun, state.production_run_id)
    if run is None:
        raise AuthoritativeModelError("declared production run does not exist")
    if run.status != "PROMOTED":
        raise AuthoritativeModelError("declared production run is not promoted")
    if not run.model_artifact or not run.candidate_model_sha256:
        raise AuthoritativeModelError("declared production artifact is incomplete")
    artifact_hash = hashlib.sha256(run.model_artifact).hexdigest()
    if artifact_hash != run.candidate_model_sha256:
        raise AuthoritativeModelError("declared production artifact hash mismatch")
    model = _classifier_from_payload(joblib.load(BytesIO(run.model_artifact)))
    if model is None:
        raise AuthoritativeModelError("declared production artifact is unsupported")
    if run.model_version and model.model_version != run.model_version:
        raise AuthoritativeModelError("declared production model version mismatch")
    return model, artifact_hash


def load_default_model(session=None) -> LearnedClassifier | None:
    """Convenience used by relevance_classifier.py."""
    try:
        if session is not None:
            from app.models import ModelTrainingState

            state = session.get(ModelTrainingState, "learned_classifier")
            if state is not None and state.production_run_id:
                model, _ = load_authoritative_model(session)
                return model
        return load_model()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Building the training set from curated labels + HumanReview
# ---------------------------------------------------------------------------


def build_training_set(
    session, training_labels_csv: Path | None = None
) -> list[dict]:
    """Materialize feature rows for every paper with a training label.

    Sources (later overrides earlier):
      1. curated training_labels.csv
      2. production feedback in the human_reviews table
    """
    from sqlalchemy import select

    from app.models import HumanReview

    from app.config import settings as _settings

    if training_labels_csv is None:
        training_labels_csv = _settings.training_labels_csv

    ensure_distinct_label_paths(
        training=Path(training_labels_csv),
        validation=_settings.validation_labels_csv,
        frozen_holdout=_settings.eval_labels_csv,
    )
    labels_by_paper = load_label_dataset(
        Path(training_labels_csv),
        role="training",
        allow_missing=True,
    )
    reserved_paper_ids = load_reserved_evaluation_ids(
        validation_path=_settings.validation_labels_csv,
        holdout_path=_settings.eval_labels_csv,
    )
    ensure_disjoint_label_ids(
        training=labels_by_paper,
        reserved_evaluation=reserved_paper_ids,
    )

    # Override with reviewer labels.
    for hr in session.execute(select(HumanReview)).scalars():
        if (
            hr.paper_id in reserved_paper_ids
            or hr.review_status not in {None, "COMPLETED"}
        ):
            continue
        label = normalize_classification_label(hr.human_label)
        if label:
            labels_by_paper[hr.paper_id] = label

    return build_examples_for_labels(session, labels_by_paper)


def build_validation_set(
    session,
    validation_labels_csv: Path | None = None,
) -> list[dict]:
    """Materialize the dedicated validation set without using it for training."""
    from app.config import settings as _settings

    validation_path = (
        Path(validation_labels_csv)
        if validation_labels_csv is not None
        else _settings.validation_labels_csv
    )
    ensure_distinct_label_paths(
        training=_settings.training_labels_csv,
        validation=validation_path,
        frozen_holdout=_settings.eval_labels_csv,
    )
    validation_labels = load_label_dataset(
        validation_path,
        role="validation",
        allow_missing=True,
    )
    training_labels = load_label_dataset(
        _settings.training_labels_csv,
        role="training",
        allow_missing=True,
    )
    holdout_labels = load_label_dataset(
        _settings.eval_labels_csv,
        role="frozen_holdout",
        allow_missing=True,
    )
    ensure_disjoint_label_ids(
        training=training_labels,
        validation=validation_labels,
        frozen_holdout=holdout_labels,
    )
    return build_examples_for_labels(session, validation_labels)


def build_examples_for_labels(
    session,
    labels_by_paper: dict[str, str],
) -> list[dict]:
    """Compute rule features for an explicit, already-validated label map."""
    from sqlalchemy import select

    from app.models import Author, Institution, Paper, PaperEvidence, Topic
    from app.services.author_matcher import AuthorMatcher
    from app.services.graph_service import compute_graph_signals
    from app.services.institution_matcher import InstitutionMatcher
    from app.services.relevance_classifier import (
        _classify_paper,
        _features_for_learned,
    )
    from app.services.topic_classifier import TopicClassifier

    if not labels_by_paper:
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
        if paper.id not in labels_by_paper:
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
        feats["label"] = labels_by_paper[paper.id]
        feats["paper_id"] = paper.id
        feats["base_label"] = result.label
        feats["base_confidence"] = result.confidence
        examples.append(feats)
    return examples
