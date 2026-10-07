"""Real PAS ORM + isolated SQLite, no production data or remote services."""
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

from app.db import Base  # noqa: E402
from app.models import all_models, Paper as PasPaper, DiscoveryCandidate  # noqa: E402,F401
from app.config import settings  # noqa: E402
from paper_monitor.models import Paper  # noqa: E402
from paper_monitor.pas import ingest_session  # noqa: E402


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'pas.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_direct_main_ingestion_is_idempotent_and_visible_to_papers_api(session, monkeypatch):
    monkeypatch.setattr(settings, "sdl_stage1_only", False)
    monkeypatch.setattr(settings, "zotero_source_only", False)
    p = Paper("Real metadata integration", doi="10.1/monitor", date="2026-10-01", authors=["A", "B"],
              tracked_authors=["A"], sources=["openalex"], abstract="Abstract")
    first = ingest_session(session, p, "main")
    session.commit()
    assert ingest_session(session, p, "main") == first
    assert session.scalar(select(func.count(PasPaper.id))) == 1
    row = session.get(PasPaper, first)
    assert len(row.authors) == 2 and row.classification is None
    assert row.provenance == "author_monitor" and row.abstract == "Abstract"
    from app.api.papers import _paper_to_schema
    result = _paper_to_schema(row)
    assert result.title == p.title and result.id == first


def test_existing_paper_and_stage1_policy_are_preserved(session, monkeypatch):
    monkeypatch.setattr(settings, "sdl_stage1_only", True)
    p = Paper("New metadata", doi="10.1/new")
    with pytest.raises(ValueError, match="corpus policy"):
        ingest_session(session, p, "main")
    key = ingest_session(session, p, "inbox")
    session.commit()
    assert ingest_session(session, p, "inbox") == key
    assert session.scalar(select(func.count(PasPaper.id))) == 0
    assert session.scalar(select(func.count(DiscoveryCandidate.id))) == 1
    from app.api.discovery import _to_out
    assert _to_out(session.get(DiscoveryCandidate, key)).source == "author_monitor"
