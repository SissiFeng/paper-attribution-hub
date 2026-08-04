"""Fresh-database bootstrap: create_all + stamp head, no from-scratch replay.

`alembic upgrade head` cannot run on an empty DB because the 0001 baseline uses
`Base.metadata.create_all()` on the live metadata (the full current schema), so
later `op.create_table` migrations collide.  A fresh deploy must therefore be
stamped, not replayed.  These tests drive the bootstrap in a subprocess against
throwaway SQLite databases so the app's global engine binding is not disturbed.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _alembic_head() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(
        Config(str(BACKEND / "alembic.ini"))
    ).get_current_head()


def _run_bootstrap(db_path: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PAS_DATABASE_URL"] = f"sqlite:///{db_path}"
    env["PYTHONPATH"] = str(BACKEND)
    return subprocess.run(
        [sys.executable, "-m", "app.scripts.db_bootstrap"],
        cwd=str(BACKEND),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _inspect(db_path: Path) -> tuple[set[str], str | None]:
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        version = None
        if "alembic_version" in tables:
            row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
            version = row[0] if row else None
        return tables, version
    finally:
        conn.close()


def test_bootstrap_fresh_db_creates_schema_and_stamps_head(tmp_path):
    db_path = tmp_path / "fresh.db"

    result = _run_bootstrap(db_path)

    assert result.returncode == 0, result.stderr
    tables, version = _inspect(db_path)
    # Full current schema is present without any replay collision.
    assert "papers" in tables
    assert "model_training_runs" in tables  # added by a post-0001 migration
    assert "alembic_version" in tables
    # Stamped at head so future `alembic upgrade head` is incremental, not replay.
    assert version == _alembic_head()


def test_bootstrap_adopts_pre_alembic_schema(tmp_path):
    """A DB with the schema but no alembic_version is stamped, not rebuilt."""
    db_path = tmp_path / "pre_alembic.db"
    env = dict(os.environ)
    env["PAS_DATABASE_URL"] = f"sqlite:///{db_path}"
    env["PYTHONPATH"] = str(BACKEND)
    # Build the schema via create_all but leave it untracked by alembic.
    subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.db import Base, engine; import app.models; "
            "Base.metadata.create_all(bind=engine)",
        ],
        cwd=str(BACKEND),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    _, version_before = _inspect(db_path)
    assert version_before is None

    result = _run_bootstrap(db_path)

    assert result.returncode == 0, result.stderr
    _, version_after = _inspect(db_path)
    assert version_after == _alembic_head()


def test_bootstrap_is_idempotent(tmp_path):
    db_path = tmp_path / "rerun.db"

    first = _run_bootstrap(db_path)
    assert first.returncode == 0, first.stderr
    _, first_version = _inspect(db_path)

    second = _run_bootstrap(db_path)
    assert second.returncode == 0, second.stderr
    tables, second_version = _inspect(db_path)

    head = _alembic_head()
    assert first_version == second_version == head
    assert "papers" in tables
