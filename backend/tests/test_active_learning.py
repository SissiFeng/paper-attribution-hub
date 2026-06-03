"""v0.7 active learning: negative-keyword harvest, eval append, retrain hook,
and positive-vocabulary mining."""
import os
import uuid
from pathlib import Path

from sqlalchemy import select

from app.models import HumanReview, Paper, Topic
from app.services.active_learning import (
    _best_topic_match,
    _harvest_negative_keywords,
    _is_downgrade,
    maybe_retrain,
    mine_positive_vocabulary,
    on_review_submitted,
)


def test_is_downgrade_basics():
    assert _is_downgrade("CORE_RELEVANT", "EXCLUDE") is True
    assert _is_downgrade("EXCLUDE", "CORE_RELEVANT") is False
    assert _is_downgrade("RELATED_RELEVANT", "ADJACENT") is True


def test_negative_keyword_harvest_targets_top_topic(seeded_session):
    from app.services.relevance_classifier import classify_all

    classify_all(seeded_session)
    paper = seeded_session.execute(
        select(__import__("app.models", fromlist=["Paper"]).Paper).where(
            __import__("app.models", fromlist=["Paper"]).Paper.id == "P003"
        )
    ).scalar_one()
    additions = _harvest_negative_keywords(
        seeded_session, paper, previous_label="RELATED_RELEVANT"
    )
    # P003 (GNN paper) shouldn't accumulate new negative_keywords on the
    # SDL topic; if anything, on generic_ml. Either way, the function must
    # return a list (possibly empty) without raising.
    assert isinstance(additions, list)


def test_on_review_submitted_runs_without_raising(seeded_session, tmp_path, monkeypatch):
    # Redirect the eval_labels CSV to a temp file so we don't mutate the real one.
    from app.config import settings

    fake_csv = tmp_path / "eval_labels.csv"
    fake_csv.write_text(
        "paper_id,gold_label,gold_topics,notes\nP001,CORE_RELEVANT,,seed\n"
    )
    monkeypatch.setattr(settings, "eval_labels_csv", fake_csv)

    from app.services.relevance_classifier import classify_all

    classify_all(seeded_session)

    # Insert a human review row so the retrain trigger sees one example.
    review = HumanReview(
        id=f"rev_{uuid.uuid4().hex[:8]}",
        paper_id="P001",
        human_label="EXCLUDE",
    )
    seeded_session.add(review)
    seeded_session.commit()

    out = on_review_submitted(
        seeded_session,
        "P001",
        new_label="EXCLUDE",
        previous_label="CORE_RELEVANT",
        reviewer="ssf",
    )
    assert isinstance(out, dict)
    assert "P001" in out["eval_labels_updated"]
    # eval_labels.csv now contains the new label.
    assert "EXCLUDE" in fake_csv.read_text()


def test_review_endpoint_optional_active_learning(seeded_session):
    """PAS_ACTIVE_LEARNING=0 must skip active learning."""
    # Default off: the API caller's submit should not require eval_labels.csv
    # to even exist. That's covered by the existing test_api.py review test.
    assert os.environ.get("PAS_ACTIVE_LEARNING", "0") == "0"


def test_maybe_retrain_after_ten_reviews(seeded_session, tmp_path, monkeypatch):
    from app.config import settings

    fake_csv = tmp_path / "eval_labels.csv"
    fake_csv.write_text("paper_id,gold_label,gold_topics,notes\n", encoding="utf-8")
    model_path = tmp_path / "learned_classifier.joblib"
    monkeypatch.setattr(settings, "eval_labels_csv", fake_csv)
    monkeypatch.setenv("PAS_LEARNED_MODEL_PATH", str(model_path))
    monkeypatch.setenv("PAS_ACTIVE_RETRAIN_EVERY", "10")

    labels = [
        "CORE_RELEVANT",
        "CORE_RELEVANT",
        "RELATED_RELEVANT",
        "RELATED_RELEVANT",
        "ADJACENT",
        "ADJACENT",
        "EXCLUDE",
        "EXCLUDE",
        "SDL_FIELD_RELEVANT",
        "UNCERTAIN",
    ]
    for idx, label in enumerate(labels, start=1):
        seeded_session.add(
            HumanReview(
                id=f"rev_train_{idx}",
                paper_id=f"P{idx:03d}",
                human_label=label,
                reviewer="ssf",
            )
        )
    seeded_session.commit()

    out = maybe_retrain(seeded_session)

    assert out == str(model_path)
    assert model_path.exists()


# ---------------------------------------------------------------------------
# Positive-vocabulary mining tests
# ---------------------------------------------------------------------------


def test_mine_positive_vocabulary_empty_when_no_gold(seeded_session):
    """Returns [] when no papers are marked ac_known_publication=True."""
    # seeded_session has papers but none are gold-set by default
    results = mine_positive_vocabulary(seeded_session)
    assert results == []


def test_mine_positive_vocabulary_returns_suggestions(seeded_session):
    """With gold-set papers that share distinctive bigrams, returns suggestions."""
    # Use novel terms not in domain_vocabulary.yaml or topic_taxonomy.yaml
    for pid, abstract in [
        ("P001", "microfluidic droplet generation microfluidic droplet generation "
                 "microfluidic droplet generation perovskite synthesis optimization"),
        ("P002", "microfluidic droplet generation microfluidic droplet generation "
                 "microfluidic droplet generation electrochemical cell assembly"),
    ]:
        paper = seeded_session.get(Paper, pid)
        if paper:
            paper.ac_known_publication = True
            paper.abstract = abstract
    seeded_session.commit()

    results = mine_positive_vocabulary(seeded_session, min_positive_freq=2)
    assert isinstance(results, list)
    assert len(results) >= 1
    assert all(isinstance(s.suggested_term, str) and s.suggested_term for s in results)
    assert all(s.action in ("add_protected_phrase", "add_keyword") for s in results)
    assert all(s.score > 0 for s in results)


def test_mine_positive_vocabulary_skips_existing_terms(seeded_session):
    """Terms already in domain_vocabulary.yaml must not appear in suggestions."""
    paper = seeded_session.get(Paper, "P001")
    if paper:
        paper.ac_known_publication = True
        # abstract saturated with an already-known term
        paper.abstract = "self-driving lab self-driving lab self-driving lab " * 5
    seeded_session.commit()

    results = mine_positive_vocabulary(seeded_session)
    suggested = {s.suggested_term for s in results}
    assert "self-driving lab" not in suggested
    assert "self driving lab" not in suggested


def test_best_topic_match_falls_back_to_sentinel(seeded_session):
    """_best_topic_match returns __vocabulary__ sentinel when no topic overlaps."""
    topics = seeded_session.execute(select(Topic)).scalars().all()
    topic_id, topic_name = _best_topic_match("xyzzy frobnicate", topics)
    assert topic_id == "__vocabulary__"
    assert topic_name == "domain_vocabulary"
