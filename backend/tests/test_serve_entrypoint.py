"""The container entrypoint must always reach uvicorn.

Demo safety: a schema-bootstrap or seeding hiccup must be logged but must not
stop the API from starting, so /health and the /debug endpoints stay reachable
for diagnosis.
"""

from __future__ import annotations

import subprocess

import app.scripts.serve as serve


class _FakeCompleted:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode


def test_run_step_returns_code_and_does_not_raise_on_failure(monkeypatch, capsys):
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: _FakeCompleted(returncode=1)
    )

    code = serve._run_step("seed", ["app.scripts.ingest_scopus_batch"])

    assert code == 1
    assert "WARNING" in capsys.readouterr().err


def test_main_execs_uvicorn_even_when_seed_fails(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd, *a, **k):
        calls.append(" ".join(cmd))
        # db_bootstrap ok, seeding fails.
        failed = "ingest_scopus_batch" in " ".join(cmd)
        return _FakeCompleted(returncode=1 if failed else 0)

    execs: list[tuple] = []
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(serve.os, "execv", lambda path, argv: execs.append((path, argv)))
    monkeypatch.setenv("PORT", "9999")

    serve.main()

    # Both prep steps ran...
    assert any("db_bootstrap" in c for c in calls)
    assert any("ingest_scopus_batch" in c for c in calls)
    # ...and uvicorn was still started despite the seed failure.
    assert len(execs) == 1
    _, argv = execs[0]
    assert "uvicorn" in argv
    assert "app.main:app" in argv
    assert "9999" in argv


def test_main_execs_uvicorn_when_bootstrap_fails(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompleted(returncode=1))
    execs: list[tuple] = []
    monkeypatch.setattr(serve.os, "execv", lambda path, argv: execs.append((path, argv)))
    monkeypatch.delenv("PORT", raising=False)

    serve.main()

    assert len(execs) == 1  # still serves even if bootstrap failed
    _, argv = execs[0]
    assert "8000" in argv  # default port
