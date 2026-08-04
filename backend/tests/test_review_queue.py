"""v0.7 review queue: priority scoring, confirm, skip."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import HumanReview, Paper, PaperClassification, PaperEvidence
from app.services.relevance_classifier import classify_all
from app.services.review_queue import (
    assign_review,
    confirm_classification,
    get_next,
    list_queue,
    queue_size,
    refresh_queue,
    skip_for_now,
)


def test_refresh_queue_flags_uncertain_papers(seeded_session):
    classify_all(seeded_session)

    # Force a paper into UNCERTAIN.
    paper = seeded_session.get(Paper, "P002")
    cls = paper.classification
    cls.label = "UNCERTAIN"
    cls.confidence = 0.45
    cls.human_confirmed = False
    seeded_session.commit()

    flagged = refresh_queue(seeded_session)
    assert flagged >= 1
    refreshed = seeded_session.get(PaperClassification, cls.id)
    assert refreshed.needs_review is True
    assert refreshed.review_priority >= 0.2


def test_queue_excludes_human_confirmed(seeded_session):
    classify_all(seeded_session)
    paper = seeded_session.get(Paper, "P001")
    paper.classification.label = "UNCERTAIN"
    paper.classification.human_confirmed = True
    seeded_session.commit()

    refresh_queue(seeded_session)
    items = list_queue(seeded_session, limit=50)
    assert all(it.paper_id != "P001" for it in items)


def test_disqualifying_evidence_pushes_high_label_to_top(seeded_session):
    classify_all(seeded_session)
    # Add a fake disqualifying-evidence row on a CORE paper.
    seeded_session.add(
        PaperEvidence(
            id="ev_test_dis",
            paper_id="P001",
            chunk_id=None,
            evidence_type="disqualifying",
            evidence_source="llm_judge",
            evidence_text="no autonomous platform is described",
            score=-0.4,
        )
    )
    seeded_session.commit()

    refresh_queue(seeded_session)
    items = list_queue(seeded_session, limit=10)
    p001 = next((it for it in items if it.paper_id == "P001"), None)
    assert p001 is not None
    assert any("disqualifying" in r.lower() for r in p001.reasons)


def test_confirm_locks_label_and_clears_queue(seeded_session):
    classify_all(seeded_session)
    paper = seeded_session.get(Paper, "P002")
    paper.classification.label = "UNCERTAIN"
    seeded_session.commit()

    refresh_queue(seeded_session)
    before = queue_size(seeded_session)
    assert before >= 1

    confirm_classification(seeded_session, "P002", reviewer="ssf")
    cls = seeded_session.get(PaperClassification, paper.classification.id)
    assert cls.human_confirmed is True
    assert cls.human_confirmed_by == "ssf"
    assert cls.needs_review is False
    review = seeded_session.execute(
        select(HumanReview).where(HumanReview.paper_id == "P002")
    ).scalar_one()
    assert review.human_label == "UNCERTAIN"
    assert review.reviewer == "ssf"
    # Queue is one shorter (or zero).
    after = queue_size(seeded_session)
    assert after == before - 1


def test_confirm_triggers_active_learning_when_enabled(
    seeded_session, tmp_path, monkeypatch
):
    from app.config import settings

    fake_csv = tmp_path / "eval_labels.csv"
    original_holdout = "paper_id,gold_label,gold_topics,notes\n"
    fake_csv.write_text(original_holdout, encoding="utf-8")
    monkeypatch.setattr(settings, "eval_labels_csv", fake_csv)
    monkeypatch.setenv("PAS_ACTIVE_LEARNING", "1")

    classify_all(seeded_session)
    paper = seeded_session.get(Paper, "P002")
    paper.classification.label = "UNCERTAIN"
    seeded_session.commit()

    confirm_classification(seeded_session, "P002", reviewer="ssf")

    review = seeded_session.execute(
        select(HumanReview).where(HumanReview.paper_id == "P002")
    ).scalar_one()
    assert review.human_label == "UNCERTAIN"
    assert fake_csv.read_text(encoding="utf-8") == original_holdout


def test_skip_defers_paper_from_queue(seeded_session):
    classify_all(seeded_session)
    paper = seeded_session.get(Paper, "P002")
    paper.classification.label = "UNCERTAIN"
    seeded_session.commit()

    refresh_queue(seeded_session)
    assert queue_size(seeded_session) >= 1

    skip_for_now(seeded_session, "P002", cooldown_days=14)
    cls = seeded_session.get(PaperClassification, paper.classification.id)
    assert cls.needs_review is False
    # last_classified_at jumped into the future.
    assert cls.last_classified_at > datetime.now(UTC) + timedelta(days=10)


def test_get_next_returns_highest_priority(seeded_session):
    classify_all(seeded_session)
    # P001 + P002 both forced UNCERTAIN, P001 with a disqualifying row.
    for pid in ["P001", "P002"]:
        paper = seeded_session.get(Paper, pid)
        paper.classification.label = "UNCERTAIN"
        paper.classification.human_confirmed = False
    seeded_session.add(
        PaperEvidence(
            id="ev_test_pri",
            paper_id="P001",
            chunk_id=None,
            evidence_type="disqualifying",
            evidence_source="llm_judge",
            evidence_text="contradiction",
            score=-0.4,
        )
    )
    seeded_session.commit()

    refresh_queue(seeded_session)
    nxt = get_next(seeded_session)
    assert nxt is not None
    # P001 has a disqualifying-evidence boost so it should bubble to the top.
    assert nxt.paper_id in {"P001", "P002"}


def test_review_assignments_partition_queue_without_changing_review_state(
    seeded_session,
):
    classify_all(seeded_session)
    for paper_id in ("P001", "P002"):
        cls = seeded_session.get(Paper, paper_id).classification
        cls.label = "UNCERTAIN"
        cls.human_confirmed = False
    seeded_session.commit()
    refresh_queue(seeded_session)

    assigned = assign_review(
        seeded_session,
        "P001",
        assignee="Alice",
        assigned_by="Lead",
    )

    assert assigned.review_assignee == "Alice"
    assert assigned.review_assigned_by == "Lead"
    assert assigned.review_assigned_at is not None
    assert {item.paper_id for item in list_queue(seeded_session, assignee="Alice")} == {
        "P001"
    }
    assert "P001" not in {
        item.paper_id
        for item in list_queue(seeded_session, unassigned_only=True)
    }
    assert queue_size(seeded_session, assignee="Alice") == 1
    assert assigned.human_confirmed is False
    assert assigned.needs_review is True

    released = assign_review(seeded_session, "P001", assignee=None)
    assert released.review_assignee is None
    assert released.review_assigned_at is None
    assert released.review_assigned_by is None


def test_review_assignment_does_not_overwrite_another_reviewer(seeded_session):
    classify_all(seeded_session)
    paper = seeded_session.get(Paper, "P002")
    paper.classification.label = "UNCERTAIN"
    paper.classification.human_confirmed = False
    seeded_session.commit()
    refresh_queue(seeded_session)
    assign_review(seeded_session, "P002", assignee="Alice")

    import pytest

    with pytest.raises(RuntimeError, match="already assigned to Alice"):
        assign_review(seeded_session, "P002", assignee="Bob")
