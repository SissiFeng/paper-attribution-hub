"""Smoke-test the REST surface against the seeded sample data."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(seeded_session):
    from app.main import app
    from app.services.relevance_classifier import classify_all

    classify_all(seeded_session)
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_list_papers(client):
    r = client.get("/papers")
    assert r.status_code == 200
    body = r.json()
    assert len(body) >= 10
    p = next(p for p in body if p["id"] == "P001")
    assert p["classification"]["label"] == "CORE_RELEVANT"
    assert any(
        m["name"] == "Alan Aspuru-Guzik" for m in p["classification"]["matched_people"]
    )


def test_filter_papers_by_label(client):
    r = client.get("/papers", params={"label": "CORE_RELEVANT"})
    assert r.status_code == 200
    body = r.json()
    assert all(p["classification"]["label"] == "CORE_RELEVANT" for p in body)


def test_export_csv(client):
    r = client.get("/papers/export.csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "paper_id" in r.text
    assert "P001" in r.text


def test_submit_review(client):
    r = client.post(
        "/reviews/P001",
        json={"human_label": "INCLUDE", "reviewer": "ssf", "notes": "looks good"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["human_label"] == "INCLUDE"


def test_coauthor_network(client):
    r = client.get("/network/coauthors")
    assert r.status_code == 200
    body = r.json()
    assert body["nodes"]
    assert body["edges"]
