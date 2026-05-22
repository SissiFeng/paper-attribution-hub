"""Shared pytest fixtures: in-memory DB seeded with sample data."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def isolate_database(tmp_path_factory: pytest.TempPathFactory):
    """Force tests to use a throwaway sqlite file before app modules import settings."""
    # If env var is already set (sandbox / CI), respect it. Otherwise pick a
    # tmp dir managed by pytest.
    if "PAS_DATABASE_URL" not in os.environ:
        db_path = tmp_path_factory.mktemp("pas") / "test.db"
        os.environ["PAS_DATABASE_URL"] = f"sqlite:///{db_path}"
    yield


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
    from app.config import settings as _settings
    from app.services.fulltext_service import (
        build_chunk_embeddings,
        ingest_fulltext_directory,
    )

    ingest_fulltext_directory(seeded_session, _settings.fulltexts_dir)
    build_chunk_embeddings(seeded_session)
    return seeded_session
