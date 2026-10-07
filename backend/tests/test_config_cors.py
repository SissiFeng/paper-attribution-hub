"""PAS_CORS_ORIGINS must accept both JSON and comma-separated env values.

A plain comma-separated value in an ECS task definition is a natural thing to
set, and it used to crash the app at import (pydantic tried to JSON-decode it).
Booting the API must not depend on the operator remembering JSON syntax.
"""

from __future__ import annotations

from app.config import Settings


def test_cors_origins_accepts_json_array(monkeypatch):
    monkeypatch.setenv(
        "PAS_CORS_ORIGINS",
        '["https://papers.example.org", "https://d111111abcdef8.cloudfront.net"]',
    )
    assert Settings().cors_origins == [
        "https://papers.example.org",
        "https://d111111abcdef8.cloudfront.net",
    ]


def test_cors_origins_accepts_comma_separated(monkeypatch):
    monkeypatch.setenv(
        "PAS_CORS_ORIGINS",
        "https://papers.example.org, "
        "https://d111111abcdef8.cloudfront.net ,https://c.example.org",
    )
    assert Settings().cors_origins == [
        "https://papers.example.org",
        "https://d111111abcdef8.cloudfront.net",
        "https://c.example.org",
    ]


def test_cors_origins_accepts_single_value(monkeypatch):
    monkeypatch.setenv("PAS_CORS_ORIGINS", "https://papers.example.org")
    assert Settings().cors_origins == ["https://papers.example.org"]


def test_cors_origins_defaults_when_unset(monkeypatch):
    monkeypatch.delenv("PAS_CORS_ORIGINS", raising=False)
    # Production origins must be explicitly configured, never inherited from
    # an old hosted preview. Ignore local .env files when testing defaults.
    assert Settings(_env_file=None).cors_origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
