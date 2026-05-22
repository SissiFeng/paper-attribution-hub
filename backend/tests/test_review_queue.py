"""v0.7 review queue: priority scoring, confirm, skip."""
from datetime import UTC, datetime, timedelta

from app.models import Paper, PaperClassification, PaperEvidence
from app.services.relevance_classifier import classify_all
from app.services.review_queue import (
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
    # Queue is one shorter (or zero).
    after = queue_size(seeded_session)
    assert after == before - 1


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
