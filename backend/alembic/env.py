from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make sure `app` is importable when running `alembic` from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.db import Base  # noqa: E402
from app.models import all_models  # noqa: E402, F401 — registers all ORM models

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inject the live database URL so the ini file doesn't need it hardcoded.
# For Supabase Transaction Pooler (port 6543 / PgBouncer), append
# ?options=-c%20prepared_statements%3Doff if not already present to avoid
# "prepared statement does not exist" errors during DDL migrations.
_db_url = settings.database_url
if ":6543/" in _db_url and "prepared_statements" not in _db_url:
    _sep = "&" if "?" in _db_url else "?"
    _db_url = f"{_db_url}{_sep}options=-c%20prepared_statements%3Doff"
config.set_main_option("sqlalchemy.url", _db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
