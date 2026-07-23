"""PAS_CORS_ORIGINS must accept both JSON and comma-separated env values.

A plain comma-separated value in the Render dashboard is a natural thing to
set, and it used to crash the app at import (pydantic tried to JSON-decode it).
Booting the API must not depend on the operator remembering JSON syntax.
"""

from __future__ import annotations

from app.config import Settings


def test_cors_origins_accepts_json_array(monkeypatch):
    monkeypatch.setenv("PAS_CORS_ORIGINS", '["https://a.vercel.app", "https://b.com"]')
    assert Settings().cors_origins == ["https://a.vercel.app", "https://b.com"]


def test_cors_origins_accepts_comma_separated(monkeypatch):
    monkeypatch.setenv(
        "PAS_CORS_ORIGINS", "https://a.vercel.app, https://b.com ,https://c.io"
    )
    assert Settings().cors_origins == [
        "https://a.vercel.app",
        "https://b.com",
        "https://c.io",
    ]


def test_cors_origins_accepts_single_value(monkeypatch):
    monkeypatch.setenv("PAS_CORS_ORIGINS", "https://only.vercel.app")
    assert Settings().cors_origins == ["https://only.vercel.app"]


def test_cors_origins_defaults_when_unset(monkeypatch):
    monkeypatch.delenv("PAS_CORS_ORIGINS", raising=False)
    origins = Settings().cors_origins
    assert isinstance(origins, list)
    assert "http://localhost:5173" in origins
