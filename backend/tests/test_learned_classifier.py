"""v0.7 learned classifier: train, save/load, predict; sklearn backend."""

import importlib

import pytest

from app.services.learned_classifier import (
    FEATURE_ORDER,
    LABELS_ORDER,
    build_training_set,
    load_model,
    save_model,
    train_from_examples,
)


def _try_import(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except ImportError:
        return False


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
    assert "SDL_FIELD_RELEVANT" in LABELS_ORDER


def test_review_include_alias_normalizes_to_related():
    examples = _synthetic_examples()
    examples[6]["label"] = "INCLUDE"

    classifier = train_from_examples(examples, backend="sklearn")

    assert "INCLUDE" not in classifier.labels
    assert "RELATED_RELEVANT" in classifier.labels


def test_unknown_features_default_to_zero(tmp_path):
    clf = train_from_examples(_synthetic_examples(), backend="sklearn")
    save_model(clf, tmp_path / "m.joblib")
    loaded = load_model(tmp_path / "m.joblib")
    # Passing only one feature shouldn't crash.
    pred, conf = loaded.predict({"author_score": 1.0})
    assert pred in LABELS_ORDER


def test_build_training_set_uses_curated_training_labels(
    seeded_session, tmp_path, monkeypatch
):
    """The frozen eval holdout is not the learned model's training source."""
    from app.config import settings
    from app.services.relevance_classifier import classify_all

    classify_all(seeded_session)
    training_labels = tmp_path / "training_labels.csv"
    training_labels.write_text(
        "paper_id,gold_label,gold_topics,notes\n"
        "P001,CORE_RELEVANT,,curated training row\n"
        "P002,RELATED_RELEVANT,,curated training row\n",
        encoding="utf-8",
    )
    holdout = tmp_path / "eval_labels.csv"
    holdout.write_text(
        "paper_id,gold_label,gold_topics,notes\n", encoding="utf-8"
    )
    monkeypatch.setattr(settings, "eval_labels_csv", holdout)

    examples = build_training_set(
        seeded_session, training_labels_csv=training_labels
    )

    assert len(examples) == 2
    for ex in examples:
        assert "label" in ex
        for name in FEATURE_ORDER:
            assert name in ex


def test_build_training_set_does_not_fall_back_to_eval_holdout(
    seeded_session, tmp_path, monkeypatch
):
    from app.config import settings

    training_labels = tmp_path / "training_labels.csv"
    training_labels.write_text(
        "paper_id,gold_label,gold_topics,notes\n", encoding="utf-8"
    )
    holdout = tmp_path / "eval_labels.csv"
    holdout.write_text(
        "paper_id,gold_label,gold_topics,notes\n"
        "P001,CORE_RELEVANT,,frozen holdout\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "training_labels_csv", training_labels)
    monkeypatch.setattr(settings, "eval_labels_csv", holdout)

    assert build_training_set(seeded_session) == []


def test_build_training_set_rejects_curated_holdout_overlap(
    seeded_session, tmp_path, monkeypatch
):
    from app.config import settings

    training_labels = tmp_path / "training_labels.csv"
    training_labels.write_text(
        "paper_id,gold_label,gold_topics,notes\n"
        "P001,CORE_RELEVANT,,training\n",
        encoding="utf-8",
    )
    holdout = tmp_path / "eval_labels.csv"
    holdout.write_text(
        "paper_id,gold_label,gold_topics,notes\n"
        "P001,CORE_RELEVANT,,holdout\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "eval_labels_csv", holdout)

    with pytest.raises(ValueError, match="overlap"):
        build_training_set(
            seeded_session, training_labels_csv=training_labels
        )


def test_build_training_set_excludes_holdout_human_reviews(
    seeded_session, tmp_path, monkeypatch
):
    from app.config import settings
    from app.models import HumanReview

    training_labels = tmp_path / "training_labels.csv"
    training_labels.write_text(
        "paper_id,gold_label,gold_topics,notes\n", encoding="utf-8"
    )
    holdout = tmp_path / "eval_labels.csv"
    holdout.write_text(
        "paper_id,gold_label,gold_topics,notes\n"
        "P001,CORE_RELEVANT,,holdout\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "training_labels_csv", training_labels)
    monkeypatch.setattr(settings, "eval_labels_csv", holdout)
    seeded_session.add(
        HumanReview(
            id="review_holdout",
            paper_id="P001",
            human_label="EXCLUDE",
        )
    )
    seeded_session.commit()

    assert build_training_set(seeded_session) == []


@pytest.mark.skipif(not _try_import("lightgbm"), reason="lightgbm not installed")
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
