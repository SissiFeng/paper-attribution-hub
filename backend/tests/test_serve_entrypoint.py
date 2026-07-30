"""The container entrypoint must always reach uvicorn.

Demo safety: a schema-bootstrap or seeding hiccup must be logged but must not
stop the API from starting, so /health and the /debug endpoints stay reachable
for diagnosis.
"""

from __future__ import annotations

import subprocess

import app.scripts.serve as serve
import uvicorn


class _FakeCompleted:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode


class _ImmediateThread:
    def __init__(self, *, target, args, **_kwargs) -> None:
        self.target = target
        self.args = args

    def start(self) -> None:
        self.target(*self.args)


def test_run_step_returns_code_and_does_not_raise_on_failure(monkeypatch, capsys):
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: _FakeCompleted(returncode=1)
    )

    code = serve._run_step("seed", ["app.scripts.ingest_scopus_batch"])

    assert code == 1
    assert "WARNING" in capsys.readouterr().err


def test_main_starts_uvicorn_even_when_seed_fails(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd, *a, **k):
        calls.append(" ".join(cmd))
        # db_bootstrap ok, seeding fails.
        failed = "ingest_scopus_batch" in " ".join(cmd)
        return _FakeCompleted(returncode=1 if failed else 0)

    uvicorn_calls: list[tuple] = []
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(serve, "Thread", _ImmediateThread)
    monkeypatch.setattr(
        uvicorn,
        "run",
        lambda app, **kwargs: uvicorn_calls.append((app, kwargs)),
    )
    monkeypatch.setenv("PORT", "9999")

    serve.main()

    # Both prep steps ran...
    assert any("db_bootstrap" in c for c in calls)
    assert any("ingest_scopus_batch" in c for c in calls)
    assert any("seed_sdl_labs" in c for c in calls)
    assert any("run_entity_extraction" in c for c in calls)
    # ...and uvicorn was still started despite the seed failure.
    assert uvicorn_calls == [
        (
            "app.main:app",
            {"host": "0.0.0.0", "port": 9999},
        )
    ]


def test_main_starts_uvicorn_when_bootstrap_fails(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompleted(returncode=1))
    monkeypatch.setattr(serve, "Thread", _ImmediateThread)
    uvicorn_calls: list[tuple] = []
    monkeypatch.setattr(
        uvicorn,
        "run",
        lambda app, **kwargs: uvicorn_calls.append((app, kwargs)),
    )
    monkeypatch.delenv("PORT", raising=False)

    serve.main()

    assert uvicorn_calls[0][1]["port"] == 8000
