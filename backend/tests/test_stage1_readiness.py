from tests.admin_client import AdminTestClient as TestClient
from sqlalchemy import select

from app.config import settings
from app.main import app
from app.models import Paper
from app.services.relevance_classifier import classify_all
from app.services.review_queue import refresh_queue


def test_stage1_unvalidated_views_are_quarantined(
    seeded_session,
    monkeypatch,
):
    classify_all(seeded_session)
    paper = seeded_session.get(Paper, "P002")
    paper.classification.label = "UNCERTAIN"
    paper.classification.needs_review = True
    seeded_session.commit()
    refresh_queue(seeded_session)

    monkeypatch.setattr(settings, "sdl_stage1_only", True)
    monkeypatch.setattr(
        settings,
        "sdl_stage1_derived_views_enabled",
        False,
    )
    client = TestClient(app)

    readiness = client.get("/stage1/readiness")
    assert readiness.status_code == 200
    assert readiness.json()["derived_views_enabled"] is False
    assert readiness.json()["descriptive_analytics_enabled"] is False
    assert readiness.json()["phase"] == "acquiring_fulltexts"

    assert client.get("/reviews/queue").json() == []
    assert client.get("/reviews/queue/next").json() is None
    assert client.get("/reviews/queue/size").json() == {"count": 0}
    assert client.get("/analytics/people-grid").json() == {
        "elements": [],
        "categories": [],
        "max_papers": 0,
        "total_people": 0,
    }
    assert client.get("/analytics/network-growth").json() == {
        "yearly": [],
        "cumulative": [],
    }
    assert client.get("/analytics/topic-stream").json() == {
        "data": [],
        "topics": [],
    }
    assert client.get("/analytics/inst-topic-heatmap").json() == {
        "institutions": [],
        "topics": [],
        "cells": [],
        "year": None,
    }
    assert client.get("/analytics/hub-score").json() == {
        "institution": "uoft",
        "data": [],
    }
    papers = client.get("/papers?limit=500").json()
    assert papers
    assert all(row["classification"] is None for row in papers)
    assert all(row["review"] is None for row in papers)
    assert client.get("/papers/stats").json()["classifications"] == {}
    assert client.get("/papers/stats").json()["topics"] == 0
    assert client.post("/reviews/P002/confirm", json={}).status_code == 409
    assert client.post(
        "/reviews/P002",
        json={
            "sdl_judgement": "CONFIRMED_SDL",
            "review_status": "COMPLETED",
            "evidence_level": "FULLTEXT",
            "judgement_basis": "STRICT_SDL",
        },
    ).status_code == 409


def test_stage1_views_require_explicit_promotion(
    seeded_session,
    monkeypatch,
):
    classify_all(seeded_session)
    paper = seeded_session.get(Paper, "P002")
    paper.classification.label = "UNCERTAIN"
    paper.classification.needs_review = True
    for corpus_paper in seeded_session.execute(select(Paper)).scalars():
        corpus_paper.full_text_available = True
    seeded_session.commit()
    refresh_queue(seeded_session)

    monkeypatch.setattr(settings, "sdl_stage1_only", True)
    monkeypatch.setattr(
        settings,
        "sdl_stage1_derived_views_enabled",
        True,
    )
    client = TestClient(app)

    readiness = client.get("/stage1/readiness").json()
    assert readiness["phase"] == "classification_pilot"
    assert "Human labels" in readiness["reason"]
    assert readiness["split_manifest_id"] is None
    assert readiness["split_role_counts"] == {}
    assert client.get("/reviews/queue/size").json()["count"] > 0
    assert client.get("/analytics/people-grid").json() == {
        "elements": [],
        "categories": [],
        "max_papers": 0,
        "total_people": 0,
    }


def test_stage1_incomplete_fulltext_corpus_cannot_be_promoted(
    seeded_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "sdl_stage1_only", True)
    monkeypatch.setattr(
        settings,
        "sdl_stage1_derived_views_enabled",
        True,
    )

    readiness = TestClient(app).get("/stage1/readiness").json()

    assert readiness["metadata_papers"] > readiness["fulltexts_imported"]
    assert readiness["phase"] == "acquiring_fulltexts"
    assert readiness["derived_views_enabled"] is False
