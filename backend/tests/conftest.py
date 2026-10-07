"""Shared pytest fixtures: in-memory DB seeded with sample data."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

FULLTEXT_FIXTURES = Path(__file__).parent / "fixtures" / "fulltexts"

# Configure the throwaway database during conftest import, before pytest imports
# test modules that import ``app.db`` and bind the SQLAlchemy engine. Setting the
# URL inside the fixture body is too late and can reset a developer database.
_TEST_DATABASE_DIR: Path | None = None
if "PAS_DATABASE_URL" not in os.environ:
    _TEST_DATABASE_DIR = Path(tempfile.mkdtemp(prefix="pas-pytest-"))
    os.environ["PAS_DATABASE_URL"] = f"sqlite:///{_TEST_DATABASE_DIR / 'test.db'}"
os.environ.setdefault("PAS_ACTIVE_LEARNING", "0")


@pytest.fixture(scope="session", autouse=True)
def isolate_database():
    """Clean up the import-time throwaway database after the test session."""
    yield
    if _TEST_DATABASE_DIR is not None:
        shutil.rmtree(_TEST_DATABASE_DIR, ignore_errors=True)


@pytest.fixture()
def session():
    from app.db import SessionLocal, reset_database

    reset_database()
    with SessionLocal() as s:
        yield s


@pytest.fixture()
def seeded_session(session):
    from app.adapters import CsvPaperSource
    from app.config import settings as _settings
    from app.services.ingestion_service import ingest_all

    source = CsvPaperSource(
        papers_csv=_settings.papers_csv,
        people_csv=_settings.people_csv,
        institutions_csv=_settings.institutions_csv,
        topics_yaml=_settings.topics_yaml,
    )
    ingest_all(session, source)
    return session


@pytest.fixture()
def fulltext_seeded_session(seeded_session):
    """Seeded DB + every sample full-text ingested + embeddings built."""
    from app.services.fulltext_service import (
        build_chunk_embeddings,
        ingest_fulltext_directory,
    )

    ingest_fulltext_directory(seeded_session, FULLTEXT_FIXTURES)
    build_chunk_embeddings(seeded_session)
    return seeded_session
