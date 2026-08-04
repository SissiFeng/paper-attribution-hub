"""v0.7 review-queue + pipeline REST endpoints."""
from fastapi.testclient import TestClient

from app.main import app
from app.models import Paper
from app.services.relevance_classifier import classify_all
from app.services.review_queue import refresh_queue


def _client():
    return TestClient(app)


def test_get_queue_returns_flagged_papers(seeded_session):
    classify_all(seeded_session)
    paper = seeded_session.get(Paper, "P002")
    paper.classification.label = "UNCERTAIN"
    seeded_session.commit()
    refresh_queue(seeded_session)

    client = _client()
    r = client.get("/reviews/queue")
    assert r.status_code == 200
    items = r.json()
    assert any(it["paper_id"] == "P002" for it in items)
    p002 = next(it for it in items if it["paper_id"] == "P002")
    assert p002["rag_status"]["status"] == "missing_fulltext"
    assert p002["screening_stage"] == "HUMAN_REVIEW"
    assert p002["screening_route"] in {
        "POSITIVE_REVIEW",
        "UNCERTAIN_REVIEW",
        "FULLTEXT_REVIEW",
    }
    assert p002["screening_reason"]


def test_get_queue_next(seeded_session):
    classify_all(seeded_session)
    paper = seeded_session.get(Paper, "P002")
    paper.classification.label = "UNCERTAIN"
    seeded_session.commit()
    refresh_queue(seeded_session)

    client = _client()
    r = client.get("/reviews/queue/next")
    assert r.status_code == 200
    body = r.json()
    assert body is not None
    assert "paper_id" in body


def test_confirm_endpoint_locks_label(seeded_session):
    classify_all(seeded_session)
    paper = seeded_session.get(Paper, "P002")
    paper.classification.label = "UNCERTAIN"
    seeded_session.commit()
    refresh_queue(seeded_session)

    client = _client()
    r = client.post(
        "/reviews/P002/confirm", json={"reviewer": "ssf"}
    )
    assert r.status_code == 200
    assert r.json()["screening_stage"] == "HUMAN_RESOLVED"
    assert r.json()["screening_route"] == "RESOLVED"
    # And the queue no longer contains P002.
    r2 = client.get("/reviews/queue")
    assert all(it["paper_id"] != "P002" for it in r2.json())


def test_confirm_unknown_paper_returns_404(seeded_session):
    client = _client()
    r = client.post("/reviews/does_not_exist/confirm", json={})
    assert r.status_code == 404


def test_skip_endpoint(seeded_session):
    classify_all(seeded_session)
    paper = seeded_session.get(Paper, "P002")
    paper.classification.label = "UNCERTAIN"
    seeded_session.commit()
    refresh_queue(seeded_session)

    client = _client()
    r = client.post("/reviews/P002/skip", json={"cooldown_days": 30})
    assert r.status_code == 200
    r2 = client.get("/reviews/queue/size")
    assert r2.json()["count"] >= 0


def test_assignment_endpoint_and_queue_filters(seeded_session):
    classify_all(seeded_session)
    paper = seeded_session.get(Paper, "P002")
    paper.classification.label = "UNCERTAIN"
    paper.classification.human_confirmed = False
    seeded_session.commit()
    refresh_queue(seeded_session)
    client = _client()

    assigned = client.put(
        "/reviews/P002/assignment",
        json={"assignee": "Alice", "assigned_by": "Lead"},
    )
    assert assigned.status_code == 200
    assert assigned.json()["review_assignee"] == "Alice"
    assert assigned.json()["review_assigned_by"] == "Lead"

    mine = client.get("/reviews/queue", params={"assignee": "Alice"})
    assert mine.status_code == 200
    assert {item["paper_id"] for item in mine.json()} == {"P002"}
    assert client.get(
        "/reviews/queue/size", params={"assignee": "Alice"}
    ).json() == {"count": 1}
    unassigned = client.get(
        "/reviews/queue", params={"unassigned_only": True}
    )
    assert all(item["paper_id"] != "P002" for item in unassigned.json())

    conflict = client.put(
        "/reviews/P002/assignment", json={"assignee": "Bob"}
    )
    assert conflict.status_code == 409

    released = client.put(
        "/reviews/P002/assignment", json={"assignee": None}
    )
    assert released.status_code == 200
    assert released.json()["review_assignee"] is None


def test_pipeline_run_endpoint(seeded_session):
    client = _client()
    r = client.post(
        "/pipeline/run",
        json={"do_discovery": False, "triggered_by": "api-test"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["triggered_by"] == "api-test"


def test_pipeline_runs_latest(seeded_session):
    client = _client()
    client.post("/pipeline/run", json={"do_discovery": False})
    r = client.get("/pipeline/runs/latest")
    assert r.status_code == 200
    assert r.json() is not None


def test_pipeline_runs_list(seeded_session):
    client = _client()
    for _ in range(2):
        client.post("/pipeline/run", json={"do_discovery": False})
    r = client.get("/pipeline/runs?limit=5")
    assert r.status_code == 200
    assert len(r.json()) >= 2
