"""Idempotent database bootstrap for startup.

The 0001 baseline migration builds the whole current schema via
``Base.metadata.create_all()`` on the live ORM metadata, so a bare
``alembic upgrade head`` on an empty database collides at the first later
``op.create_table`` migration.  A fresh database must therefore be *stamped*,
not *replayed*.

Decision table (keyed off the alembic version stored in the DB):

* No alembic version, no app tables  -> fresh DB: ``create_all`` + stamp head.
* No alembic version, app tables exist -> pre-alembic DB: stamp head only.
* Alembic version present             -> normal incremental ``upgrade head``.

This replaces the bare ``alembic upgrade head`` in the container entrypoint.

Usage:
    python -m app.scripts.db_bootstrap
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect, text

from app.db import Base, engine
from app.models import all_models  # noqa: F401 — registers all ORM tables

_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

# A table that has existed since the 0001 baseline; its presence marks a
# database that already holds the application schema.
_SENTINEL_TABLE = "papers"


def _current_revision() -> str | None:
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        return context.get_current_revision()


def _prepare_fresh_database() -> None:
    """Enable PostgreSQL extensions required by the current ORM metadata."""
    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


def bootstrap_database() -> str:
    """Bring the database to head without ever replaying from 0001.

    Returns one of ``"created"``, ``"stamped"``, or ``"upgraded"`` describing
    the action taken.
    """
    config = Config(str(_ALEMBIC_INI))
    revision = _current_revision()

    if revision is not None:
        command.upgrade(config, "head")
        return "upgraded"

    if inspect(engine).has_table(_SENTINEL_TABLE):
        # Schema exists but predates alembic tracking: adopt it as head.
        command.stamp(config, "head")
        return "stamped"

    # Truly empty database: build the current schema and mark it as head.
    _prepare_fresh_database()
    Base.metadata.create_all(bind=engine)
    command.stamp(config, "head")
    return "created"


def main() -> None:
    action = bootstrap_database()
    print(f"Database bootstrap: {action}")


if __name__ == "__main__":
    main()
