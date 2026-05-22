"""Scheduled-pipeline orchestrator.

The daily job glues four steps:

  1. **Discovery** — `run_discovery` pulls candidates from OpenAlex /
     Semantic Scholar / Crossref. Auto-eligible candidates land in the
     `papers` table; the rest sit in `discovery_candidates`.

  2. **Incremental classify** — `classify_new` scores every paper that
     wasn't already classified (and every paper whose model_version is
     out of date). Human-confirmed labels are never overwritten.

  3. **Re-prioritize the review queue** — `refresh_queue` recomputes
     priority for everything and sets `needs_review` on the high-priority
     subset.

  4. **Audit log** — every run is persisted to the `pipeline_runs` table so
     the API / dashboard can show "last run @ 06:00, classified 12 new
     papers, 3 flagged for review".

Skips heavy steps when their inputs are missing (no discovery clients
configured, no full text available, etc.), which keeps the cron job
reliable in offline environments.
"""
from __future__ import annotations

import os
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import PipelineRun


@dataclass
class PipelineResult:
    run_id: str
    started_at: datetime
    finished_at: datetime
    duration_seconds: float

    discovered_candidates: int = 0
    auto_ingested: int = 0
    queued_for_review: int = 0
    classified_new: int = 0
    reclassified_stale: int = 0
    enqueued_for_review: int = 0

    status: str = "success"
    error_message: str | None = None
    steps: list[dict] = field(default_factory=list)


def run_daily_pipeline(
    session: Session,
    *,
    do_discovery: bool | None = None,
    do_fulltext: bool | None = None,
    use_learned: bool | None = None,
    use_judge: bool | None = None,
    triggered_by: str = "cron",
) -> PipelineResult:
    """Run the full scheduled pipeline once. Idempotent: re-running on a
    stable corpus does nothing destructive.

    Args:
      do_discovery: pull from external sources. Defaults to env
        `PAS_PIPELINE_DISCOVERY` (yes/no). Off in tests.
      do_fulltext: also extract full-text evidence for the new papers.
        Defaults to env `PAS_PIPELINE_FULLTEXT`.
      use_learned / use_judge: forwarded to classify_new.
      triggered_by: free-form string; goes into the audit log.
    """
    started_at = datetime.now(UTC)
    t0 = time.monotonic()
    run_id = f"run_{uuid.uuid4().hex[:12]}"

    if do_discovery is None:
        do_discovery = _env_bool("PAS_PIPELINE_DISCOVERY", default=False)
    if do_fulltext is None:
        do_fulltext = _env_bool("PAS_PIPELINE_FULLTEXT", default=False)

    result = PipelineResult(
        run_id=run_id,
        started_at=started_at,
        finished_at=started_at,
        duration_seconds=0.0,
    )

    try:
        # 1. Discovery -------------------------------------------------
        if do_discovery:
            step = {"name": "discovery", "started_at": _isoformat_now()}
            try:
                from app.services.discovery_service import run_discovery

                disc = run_discovery(session)
                result.discovered_candidates = disc.candidates_seen
                result.auto_ingested = disc.auto_ingested
                result.queued_for_review = disc.queued
                step["status"] = "ok"
                step["seen"] = disc.candidates_seen
                step["auto"] = disc.auto_ingested
                step["queued"] = disc.queued
            except Exception as e:
                step["status"] = "skipped"
                step["error"] = f"{type(e).__name__}: {e}"
            result.steps.append(step)
        else:
            result.steps.append({"name": "discovery", "status": "disabled"})

        # 2. Full-text evidence for new papers (best-effort) -----------
        if do_fulltext:
            step = {"name": "fulltext_evidence", "started_at": _isoformat_now()}
            try:
                from sqlalchemy import select

                from app.models import Paper
                from app.services.evidence_extractor import persist_evidence

                papers_with_text = session.execute(
                    select(Paper).where(Paper.full_text_available.is_(True))
                ).scalars()
                count = 0
                for p in papers_with_text:
                    persist_evidence(session, p.id)
                    count += 1
                session.commit()
                step["status"] = "ok"
                step["papers_with_fulltext"] = count
            except Exception as e:
                step["status"] = "skipped"
                step["error"] = f"{type(e).__name__}: {e}"
            result.steps.append(step)
        else:
            result.steps.append({"name": "fulltext_evidence", "status": "disabled"})

        # 3. Incremental classify -------------------------------------
        step = {"name": "classify_new", "started_at": _isoformat_now()}
        try:
            from app.services.relevance_classifier import classify_new

            touched, new_count, refreshed = classify_new(
                session,
                use_learned=use_learned,
                use_judge=use_judge,
            )
            result.classified_new = new_count
            result.reclassified_stale = refreshed
            step["status"] = "ok"
            step["touched"] = len(touched)
            step["new"] = new_count
            step["refreshed"] = refreshed
        except Exception as e:
            step["status"] = "failed"
            step["error"] = f"{type(e).__name__}: {e}"
            raise
        result.steps.append(step)

        # 4. Re-prioritize the review queue ---------------------------
        step = {"name": "refresh_queue", "started_at": _isoformat_now()}
        try:
            from app.services.review_queue import refresh_queue

            flagged = refresh_queue(session)
            result.enqueued_for_review = flagged
            step["status"] = "ok"
            step["flagged"] = flagged
        except Exception as e:
            step["status"] = "failed"
            step["error"] = f"{type(e).__name__}: {e}"
            raise
        result.steps.append(step)

    except Exception as e:
        result.status = "failed"
        result.error_message = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"

    result.finished_at = datetime.now(UTC)
    result.duration_seconds = round(time.monotonic() - t0, 3)

    _persist_run(session, result, triggered_by=triggered_by)
    return result


def _persist_run(
    session: Session, result: PipelineResult, *, triggered_by: str
) -> None:
    run = PipelineRun(
        id=result.run_id,
        started_at=result.started_at,
        finished_at=result.finished_at,
        duration_seconds=result.duration_seconds,
        discovered_candidates=result.discovered_candidates,
        auto_ingested=result.auto_ingested,
        queued_for_review=result.queued_for_review,
        classified_new=result.classified_new,
        reclassified_stale=result.reclassified_stale,
        enqueued_for_review=result.enqueued_for_review,
        status=result.status,
        error_message=result.error_message,
        steps=result.steps,
        triggered_by=triggered_by,
    )
    session.add(run)
    session.commit()


def _isoformat_now() -> str:
    return datetime.now(UTC).isoformat()


def _env_bool(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y"}


# ---------------------------------------------------------------------------
# Read-side helpers
# ---------------------------------------------------------------------------


def latest_run(session: Session) -> PipelineRun | None:
    from sqlalchemy import desc, select

    return session.execute(
        select(PipelineRun).order_by(desc(PipelineRun.started_at)).limit(1)
    ).scalar_one_or_none()


def recent_runs(session: Session, *, limit: int = 20) -> list[PipelineRun]:
    from sqlalchemy import desc, select

    return list(
        session.execute(
            select(PipelineRun)
            .order_by(desc(PipelineRun.started_at))
            .limit(limit)
        ).scalars()
    )
