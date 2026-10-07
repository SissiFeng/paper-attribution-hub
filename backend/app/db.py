from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


_is_postgres = not settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    echo=False,
    future=True,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if not _is_postgres else {},
)

# Register pgvector types so SQLAlchemy can read vector columns back as lists.
# Wrapped in try/except: if the extension isn't enabled in this PostgreSQL
# instance, we degrade gracefully.
if _is_postgres:
    try:
        from pgvector.sqlalchemy import Vector  # noqa: F401 — side-effect: registers type

        @event.listens_for(engine, "connect")
        def _register_vector(dbapi_conn, _):
            try:
                from pgvector.psycopg2 import register_vector
                register_vector(dbapi_conn)
            except Exception:
                pass  # vector extension not installed; similarity search disabled

    except ImportError:
        pass  # pgvector package not available


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def reset_database() -> None:
    """Drop and recreate all tables. SQLite local dev only."""
    if _is_postgres:
        raise RuntimeError("reset_database() is not safe on PostgreSQL — use alembic downgrade/upgrade instead.")
    from app.models import all_models  # noqa: F401

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def init_database() -> None:
    """Create tables if they don't exist (SQLite only). On PostgreSQL, alembic manages schema."""
    from app.models import all_models  # noqa: F401

    if not _is_postgres:
        Base.metadata.create_all(bind=engine)
    # On PostgreSQL, `alembic upgrade head` must be run before starting the server.
