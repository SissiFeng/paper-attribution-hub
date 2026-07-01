"""API-key auth on mutating endpoints (PAS_API_KEY / X-API-Key header)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(session):
    from app.main import app

    return TestClient(app)


def test_mutating_endpoint_requires_key_when_set(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "api_key", "test-key")

    r = client.post("/reviews/P001", json={"human_label": "EXCLUDE"})
    assert r.status_code == 401

    r = client.post(
        "/reviews/P001",
        json={"human_label": "EXCLUDE"},
        headers={"X-API-Key": "wrong-key"},
    )
    assert r.status_code == 401

    r = client.post(
        "/reviews/P001",
        json={"human_label": "EXCLUDE"},
        headers={"X-API-Key": "test-key"},
    )
    assert r.status_code != 401  # 404: empty DB, but auth passed


def test_mutating_endpoint_open_when_key_empty(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "api_key", "")

    r = client.post("/reviews/P001", json={"human_label": "EXCLUDE"})
    assert r.status_code != 401
