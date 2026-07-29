from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError


def test_preview_health_identifies_read_only_mode():
    from app.preview_readonly import app

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json()["mode"] == "read-only-preview"


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_preview_rejects_mutating_methods(method):
    from app.preview_readonly import app

    response = TestClient(app).request(method, "/health")

    assert response.status_code == 405
    assert response.json()["detail"] == "Read-only preview: method not allowed"


def test_preview_requires_server_side_token(monkeypatch):
    from app.preview_readonly import app

    monkeypatch.setenv("PAS_PREVIEW_API_TOKEN", "test-preview-token")
    response = TestClient(app).get("/papers")

    assert response.status_code == 401
    assert response.json()["detail"] == "Preview authentication required"


def test_preview_rejects_non_ascii_token_without_server_error(monkeypatch):
    from app.preview_readonly import app

    monkeypatch.setenv("PAS_PREVIEW_API_TOKEN", "test-preview-token")
    response = TestClient(app).get(
        "/papers",
        headers={b"X-Preview-Token": "é".encode("latin-1")},
    )

    assert response.status_code == 401


def test_preview_fails_closed_without_token(monkeypatch):
    from app.preview_readonly import app

    monkeypatch.delenv("PAS_PREVIEW_API_TOKEN", raising=False)
    response = TestClient(app).get("/papers")

    assert response.status_code == 503
    assert response.json()["detail"] == "Preview authentication is not configured"


def test_preview_exposes_real_paper_and_aet_reads(session, monkeypatch):
    from app.config import settings
    from app.models import Paper
    from app.preview_readonly import app

    session.add(Paper(id="PREVIEW1", title="Preview database paper"))
    session.commit()
    monkeypatch.setattr(settings, "attribution_evidence_tree_enabled", True)
    monkeypatch.setenv("PAS_PREVIEW_API_TOKEN", "test-preview-token")
    client = TestClient(app)
    headers = {"X-Preview-Token": "test-preview-token"}

    paper_response = client.get("/papers/PREVIEW1", headers=headers)
    tree_response = client.get(
        "/papers/PREVIEW1/attribution-evidence-tree", headers=headers
    )

    assert paper_response.status_code == 200
    assert paper_response.json()["title"] == "Preview database paper"
    assert tree_response.status_code == 200
    assert tree_response.json()["paper_id"] == "PREVIEW1"


def test_preview_database_session_rejects_writes(session):
    from app.models import Paper
    from app.preview_readonly import get_read_only_session

    dependency = get_read_only_session()
    read_only_session = next(dependency)
    read_only_session.add(Paper(id="BLOCKED", title="Must not be written"))

    with pytest.raises(OperationalError):
        read_only_session.commit()

    dependency.close()
    assert session.get(Paper, "BLOCKED") is None
