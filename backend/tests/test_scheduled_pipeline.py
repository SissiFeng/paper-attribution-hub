"""v0.7 scheduled pipeline: runs end-to-end, idempotent, audit-logged."""
from sqlalchemy import select

from app.models import Paper, PipelineRun
from app.services.scheduled_pipeline import (
    latest_run,
    recent_runs,
    run_daily_pipeline,
)


def test_pipeline_runs_and_persists_audit_row(seeded_session):
    result = run_daily_pipeline(seeded_session, do_discovery=False)
    assert result.status == "success"
    # Audit row exists.
    rows = list(seeded_session.execute(select(PipelineRun)).scalars())
    assert len(rows) == 1
    assert rows[0].id == result.run_id


def test_pipeline_is_idempotent(seeded_session):
    run_daily_pipeline(seeded_session, do_discovery=False)
    # Second run on stable corpus shouldn't classify anything new.
    result2 = run_daily_pipeline(seeded_session, do_discovery=False)
    assert result2.status == "success"
    assert result2.classified_new == 0
    assert result2.reclassified_stale == 0


def test_pipeline_classifies_newly_added_paper(seeded_session):
    run_daily_pipeline(seeded_session, do_discovery=False)
    seeded_session.add(
        Paper(
            id="P_DAILY",
            title="Closed-loop discovery via robotic synthesis",
            abstract="A self-driving lab orchestrates the synthesis loop.",
            year=2025,
            doi="10.test/daily",
            source="csv",
            keywords=["self-driving lab"],
        )
    )
    seeded_session.commit()

    result = run_daily_pipeline(seeded_session, do_discovery=False)
    assert result.classified_new == 1
    new_paper = seeded_session.get(Paper, "P_DAILY")
    assert new_paper.classification is not None
    assert new_paper.classification.label in {
        "CORE_RELEVANT",
        "RELATED_RELEVANT",
        "ADJACENT",
    }


def test_recent_runs_and_latest_run(seeded_session):
    for _ in range(3):
        run_daily_pipeline(seeded_session, do_discovery=False)
    rows = recent_runs(seeded_session, limit=10)
    assert len(rows) == 3
    latest = latest_run(seeded_session)
    assert latest is not None
    assert latest.id == rows[0].id


def test_pipeline_records_failure_in_audit(seeded_session, monkeypatch):
    """Force a step to raise — audit row should still land with status=failed."""
    def _boom(*a, **kw):
        raise RuntimeError("synthetic failure")

    # classify_new is imported lazily inside the pipeline; patch the symbol
    # at its definition site.
    monkeypatch.setattr(
        "app.services.relevance_classifier.classify_new", _boom
    )
    result = run_daily_pipeline(seeded_session, do_discovery=False)
    assert result.status == "failed"
    assert result.error_message
    # And the audit row recorded the failure.
    row = latest_run(seeded_session)
    assert row.status == "failed"


def test_pipeline_fulltext_step_fetches_and_rebuilds_embeddings(seeded_session, monkeypatch):
    calls: list[str] = []
    embeddings = {"rebuilt": False}

    def fake_fetch(session, paper_id, doi, dest_dir, *, rate_limit_s=1.0, prefer_grobid=None):
        paper = session.get(Paper, paper_id)
        paper.full_text_available = True
        calls.append(paper_id)
        return True, "fake fulltext"

    def fake_embeddings(session):
        embeddings["rebuilt"] = True
        return 1

    monkeypatch.setattr("app.services.fulltext_fetcher.fetch_and_ingest", fake_fetch)
    monkeypatch.setattr("app.services.fulltext_service.build_chunk_embeddings", fake_embeddings)

    result = run_daily_pipeline(
        seeded_session,
        do_discovery=False,
        do_fulltext=True,
    )

    assert result.status == "success"
    assert calls
    assert embeddings["rebuilt"] is True
    fulltext_step = next(step for step in result.steps if step["name"] == "fulltext_evidence")
    assert fulltext_step["fetched"] == len(calls)
