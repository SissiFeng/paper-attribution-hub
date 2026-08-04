from __future__ import annotations

import pytest

from fastapi.testclient import TestClient

from app.main import app
from app.models import Paper
from app.services.relevance_classifier import classify_all
from app.services.review_queue import refresh_queue


def _queued_paper(seeded_session):
    classify_all(seeded_session)
    paper = seeded_session.get(Paper, "P002")
    paper.classification.label = "UNCERTAIN"
    paper.classification.needs_review = True
    paper.classification.review_priority = 0.8
    seeded_session.commit()
    return paper


def test_dual_dimension_review_does_not_become_legacy_training_label(
    seeded_session,
):
    paper = _queued_paper(seeded_session)
    client = TestClient(app)

    response = client.post(
        "/reviews/P002",
        json={
            "sdl_judgement": "NOT_SDL",
            "ac_relevance_judgement": "AC_RELEVANT",
            "ai_for_science_judgement": "AI_FOR_SCIENCE",
            "review_status": "COMPLETED",
            "evidence_level": "ABSTRACT",
            "judgement_basis": "DUAL_REVIEW",
            "reviewer": "reviewer-1",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["human_label"] is None
    assert body["sdl_judgement"] == "NOT_SDL"
    assert body["ac_relevance_judgement"] == "AC_RELEVANT"
    seeded_session.refresh(paper)
    assert paper.classification.label == "UNCERTAIN"
    assert paper.classification.human_confirmed is False
    assert paper.classification.needs_review is False
    assert paper.classification.screening_stage == "HUMAN_RESOLVED"
    assert paper.classification.screening_route == "RESOLVED"


def test_completed_dual_review_requires_sdl_and_ac_judgements(seeded_session):
    _queued_paper(seeded_session)
    client = TestClient(app)

    response = client.post(
        "/reviews/P002",
        json={
            "sdl_judgement": "CONFIRMED_SDL",
            "review_status": "COMPLETED",
            "evidence_level": "ABSTRACT",
            "judgement_basis": "DUAL_REVIEW",
        },
    )

    assert response.status_code == 422
    assert "requires both SDL and AC judgements" in response.text


def test_review_queue_exposes_review_context_and_source_contract(seeded_session):
    paper = _queued_paper(seeded_session)
    paper.corpus_sources = ["AC_MEMBER_CORPUS", "STRICT_SDL_KEYWORD"]
    seeded_session.commit()
    refresh_queue(seeded_session)
    client = TestClient(app)

    response = client.get("/reviews/queue")

    assert response.status_code == 200
    item = next(row for row in response.json() if row["paper_id"] == "P002")
    assert item["abstract"]
    assert item["year"]
    assert item["authors"]
    assert item["institutions"]
    assert item["source"]
    assert item["corpus_sources"] == [
        "AC_MEMBER_CORPUS",
        "STRICT_SDL_KEYWORD",
    ]


def test_completed_dual_review_stays_out_of_refreshed_queue(seeded_session):
    paper = _queued_paper(seeded_session)
    client = TestClient(app)
    response = client.post(
        "/reviews/P002",
        json={
            "sdl_judgement": "PROBABLE_SDL",
            "ac_relevance_judgement": "AC_RELEVANT",
            "review_status": "COMPLETED",
            "evidence_level": "FULLTEXT",
            "judgement_basis": "DUAL_REVIEW",
        },
    )
    assert response.status_code == 200, response.text

    seeded_session.refresh(paper)
    assert paper.classification.screening_route == "RESOLVED"
    refresh_queue(seeded_session)
    assert paper.classification.needs_review is False
    assert all(row["paper_id"] != "P002" for row in client.get("/reviews/queue").json())


def test_insufficient_evidence_requires_fulltext_and_stays_in_queue(
    seeded_session,
):
    paper = _queued_paper(seeded_session)
    client = TestClient(app)

    response = client.post(
        "/reviews/P002",
        json={
            "sdl_judgement": "INSUFFICIENT_EVIDENCE",
            "ac_relevance_judgement": "AC_RELEVANT",
            "evidence_level": "ABSTRACT",
            "judgement_basis": "DUAL_REVIEW",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["review_status"] == "NEEDS_FULLTEXT"
    seeded_session.refresh(paper)
    assert paper.classification.screening_route == "FULLTEXT_REVIEW"
    refresh_queue(seeded_session)
    assert paper.classification.needs_review is True
    assert any(
        row["paper_id"] == "P002" for row in client.get("/reviews/queue").json()
    )


def test_completed_status_rejects_insufficient_evidence(seeded_session):
    _queued_paper(seeded_session)
    client = TestClient(app)

    response = client.post(
        "/reviews/P002",
        json={
            "sdl_judgement": "INSUFFICIENT_EVIDENCE",
            "ac_relevance_judgement": "AC_RELEVANT",
            "review_status": "COMPLETED",
            "evidence_level": "ABSTRACT",
            "judgement_basis": "DUAL_REVIEW",
        },
    )

    assert response.status_code == 422
    assert "NEEDS_FULLTEXT" in response.text


# ---------------------------------------------------------------------------
# D22: strict-SDL reviewer rubric — SDL_ADJACENT contract
# ---------------------------------------------------------------------------


def test_review_accepts_and_returns_sdl_adjacent(seeded_session):
    _queued_paper(seeded_session)
    client = TestClient(app)

    response = client.post(
        "/reviews/P002",
        json={
            "sdl_judgement": "SDL_ADJACENT",
            "ac_relevance_judgement": "AC_RELEVANT",
            "ai_for_science_judgement": "AI_FOR_SCIENCE",
            "review_status": "COMPLETED",
            "evidence_level": "ABSTRACT",
            "judgement_basis": "STRICT_SDL",
            "reviewer": "reviewer-1",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["sdl_judgement"] == "SDL_ADJACENT"


def test_sdl_adjacent_filter_selects_human_and_model_scope(fulltext_seeded_session):
    from app.models import HumanReview, Paper
    from app.services.filter_spec import PaperFilter, filtered_paper_ids
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    paper = fulltext_seeded_session.get(Paper, "P001")
    paper.classification.sdl_relevance_label = "SDL_ADJACENT"
    fulltext_seeded_session.add(
        HumanReview(
            id="review_sdl_adjacent_model",
            paper_id="P004",
            sdl_judgement="SDL_ADJACENT",
            ac_relevance_judgement="AC_RELEVANT",
            review_status="COMPLETED",
        )
    )
    fulltext_seeded_session.commit()

    ids = set(
        filtered_paper_ids(
            fulltext_seeded_session,
            PaperFilter(sdl_judgements=["SDL_ADJACENT"]),
        )
    )
    # Model-equivalent SDL_ADJACENT + human SDL_ADJACENT both match.
    assert "P001" in ids
    assert "P004" in ids


def test_filter_sdl_judgements_rejects_unknown_label(fulltext_seeded_session):
    from pydantic import ValidationError

    from app.services.filter_spec import PaperFilter

    with pytest.raises(ValidationError):
        PaperFilter(sdl_judgements=["CONFIRMED_SDL", "NOT_A_LABEL"])
