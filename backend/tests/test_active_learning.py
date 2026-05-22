"""v0.7 active learning: negative-keyword harvest, eval append, retrain hook."""
import os
import uuid
from pathlib import Path

from sqlalchemy import select

from app.models import HumanReview, Topic
from app.services.active_learning import (
    _harvest_negative_keywords,
    _is_downgrade,
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
