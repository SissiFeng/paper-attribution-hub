"""v0.7 learned classifier: train, save/load, predict; sklearn backend."""
import importlib
import os
import pytest


def _try_import(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except ImportError:
        return False


from app.services.learned_classifier import (
    FEATURE_ORDER,
    LABELS_ORDER,
    build_training_set,
    load_model,
    save_model,
    train_from_examples,
)


def _synthetic_examples():
    """Synthesize a tiny but separable training set."""
    examples = []
    # Strong CORE pattern: AC author + topic + funding.
    for _ in range(6):
        examples.append(
            {
                "author_score": 1.0,
                "institution_score": 1.0,
                "topic_score": 0.8,
                "fulltext_evidence_score": 0.7,
                "topic_density": 2,
                "has_funding_evidence": 1.0,
                "year": 2024,
                "label": "CORE_RELEVANT",
            }
        )
    # RELATED: AC author, weak topic.
    for _ in range(6):
        examples.append(
            {
                "author_score": 0.95,
                "institution_score": 0.5,
                "topic_score": 0.3,
                "fulltext_evidence_score": 0.0,
                "topic_density": 0,
                "year": 2023,
                "label": "RELATED_RELEVANT",
            }
        )
    # EXCLUDE: no signals.
    for _ in range(6):
        examples.append(
            {
                "author_score": 0.0,
                "institution_score": 0.0,
                "topic_score": 0.05,
                "year": 2022,
                "label": "EXCLUDE",
            }
        )
    return examples


def test_sklearn_train_predict_roundtrip(tmp_path):
    examples = _synthetic_examples()
    clf = train_from_examples(examples, backend="sklearn")
    assert clf.backend == "sklearn"

    out = save_model(clf, tmp_path / "model.joblib")
    loaded = load_model(out)
    assert loaded is not None

    # Should classify a strongly-CORE feature vector as CORE.
    pred, conf = loaded.predict(
        {
            "author_score": 1.0,
            "institution_score": 1.0,
            "topic_score": 0.9,
            "fulltext_evidence_score": 0.7,
            "topic_density": 2,
            "has_funding_evidence": 1.0,
            "year": 2024,
        }
    )
    assert pred == "CORE_RELEVANT"
    assert conf > 0.5


def test_feature_order_stable():
    # Defensive: changing order would silently corrupt saved models.
    assert FEATURE_ORDER[0] == "author_score"
    assert "provenance_prior" in FEATURE_ORDER


def test_unknown_features_default_to_zero(tmp_path):
    clf = train_from_examples(_synthetic_examples(), backend="sklearn")
    save_model(clf, tmp_path / "m.joblib")
    loaded = load_model(tmp_path / "m.joblib")
    # Passing only one feature shouldn't crash.
    pred, conf = loaded.predict({"author_score": 1.0})
    assert pred in LABELS_ORDER


def test_build_training_set_from_db(seeded_session):
    """build_training_set should produce a row per labeled paper."""
    from app.services.relevance_classifier import classify_all

    classify_all(seeded_session)
    examples = build_training_set(seeded_session)
    # eval_labels.csv ships with 11 labels, all of which should match
    # seeded papers.
    assert len(examples) >= 8
    for ex in examples:
        assert "label" in ex
        for name in FEATURE_ORDER:
            assert name in ex


@pytest.mark.skipif(
    not _try_import("lightgbm"), reason="lightgbm not installed"
)
def test_lightgbm_backend_optional(tmp_path):
    examples = _synthetic_examples()
    clf = train_from_examples(examples, backend="lightgbm")
    assert clf.backend == "lightgbm"
    save_model(clf, tmp_path / "lgb.joblib")
    loaded = load_model(tmp_path / "lgb.joblib")
    pred, conf = loaded.predict(
        {
            "author_score": 1.0,
            "topic_score": 0.9,
            "fulltext_evidence_score": 0.7,
            "topic_density": 2,
            "has_funding_evidence": 1.0,
            "year": 2024,
        }
    )
    assert pred in LABELS_ORDER
