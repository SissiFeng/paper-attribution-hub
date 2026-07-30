"""The container entrypoint must start uvicorn without prep work."""

from __future__ import annotations

import app.scripts.serve as serve


def test_main_execs_uvicorn_immediately(monkeypatch):
    execs: list[tuple] = []
    monkeypatch.setattr(serve.os, "execv", lambda path, argv: execs.append((path, argv)))
    monkeypatch.setenv("PORT", "9999")

    serve.main()

    assert len(execs) == 1
    _, argv = execs[0]
    assert "uvicorn" in argv
    assert "app.main:app" in argv
    assert "9999" in argv


def test_main_uses_default_port(monkeypatch):
    execs: list[tuple] = []
    monkeypatch.setattr(serve.os, "execv", lambda path, argv: execs.append((path, argv)))
    monkeypatch.delenv("PORT", raising=False)

    serve.main()

    assert len(execs) == 1
    _, argv = execs[0]
    assert "8000" in argv
