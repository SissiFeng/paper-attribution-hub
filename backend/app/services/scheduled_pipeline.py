"""Scheduled-pipeline orchestrator.

The daily job glues seven steps:

  1. **Zotero sync** — when configured, synchronizes the authoritative Tier 1 /
     Tier 2 group collections.

  2. **Discovery** — `run_discovery` pulls candidates from OpenAlex /
     Semantic Scholar / Crossref. Auto-eligible candidates land in the
     `papers` table; the rest sit in `discovery_candidates`.

  3. **Full-text evidence** — fetches and extracts eligible full text when
     enabled.

  4. **Model evolution recovery** — claims any complete human-review batch
     whose response-time background task did not finish.

  5. **Incremental classify** — `classify_new` scores every paper that
     wasn't already classified (and every paper whose model_version is
     out of date). Human-confirmed labels are never overwritten.

  6. **Staged screening** — `refresh_queue` persists a route for every scored
     paper and queues only positive, uncertain, or full-text-needed subsets.

  7. **Audit log** — every run is persisted to the `pipeline_runs` table so
     the API / dashboard can show "last run @ 06:00, classified 12 new
     papers, 3 routed to review, 9 screened out".

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

from app.logging_utils import get_logger
from app.models import PipelineRun

logger = get_logger(__name__)


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
    do_zotero_sync: bool = True,
    do_discovery: bool | None = None,
    do_fulltext: bool | None = None,
    force_reclassify: bool = False,
    use_learned: bool | None = None,
    use_judge: bool | None = None,
    triggered_by: str = "cron",
) -> PipelineResult:
    """Run the full scheduled pipeline once. Idempotent: re-running on a
    stable corpus does nothing destructive.

    Args:
      do_zotero_sync: synchronize the configured authoritative Zotero
        collection before processing. Disable only for a corpus-locked replay.
      do_discovery: pull from external sources. Defaults to env
        `PAS_PIPELINE_DISCOVERY` (yes/no). Off in tests.
      do_fulltext: also extract full-text evidence for the new papers.
        Defaults to env `PAS_PIPELINE_FULLTEXT`.
      force_reclassify: re-run the classifier for every non-human-confirmed
        paper even when its stored model version is current.
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
        # 1. Authoritative Zotero sync --------------------------------
        from app.config import settings

        zotero_authoritative = (
            settings.zotero_configured and settings.zotero_source_only
        )
        if settings.zotero_configured and do_zotero_sync:
            step = {"name": "zotero_sync", "started_at": _isoformat_now()}
            logger.info("stage=zotero_sync status=start run_id=%s", run_id)
            stage_t0 = time.monotonic()
            try:
                from app.services.zotero_client import ZoteroClient
                from app.services.zotero_ingestion_service import (
                    configured_collection_specs,
                    sync_zotero_corpus,
                )

                with ZoteroClient(
                    api_key=settings.zotero_api_key,
                    group_id=settings.zotero_group_id,
                    base_url=settings.zotero_api_url,
                ) as client:
                    stats = sync_zotero_corpus(
                        session,
                        client,
                        configured_collection_specs(),
                        download_fulltexts=do_fulltext,
                    )
                result.auto_ingested += stats.inserted
                step.update(stats.to_dict())
                step["status"] = "ok"
                logger.info(
                    "stage=zotero_sync status=end seen=%d inserted=%d "
                    "updated=%d elapsed_s=%.1f",
                    stats.seen_items,
                    stats.inserted,
                    stats.updated,
                    time.monotonic() - stage_t0,
                )
            except Exception as e:
                step["status"] = "failed"
                step["error"] = f"{type(e).__name__}: {e}"
                result.steps.append(step)
                logger.error(
                    "stage=zotero_sync status=failed error=%r elapsed_s=%.1f",
                    step["error"],
                    time.monotonic() - stage_t0,
                )
                raise
            result.steps.append(step)
        elif settings.zotero_configured:
            result.steps.append(
                {
                    "name": "zotero_sync",
                    "status": "disabled",
                    "reason": "explicit_corpus_lock",
                }
            )
        else:
            result.steps.append(
                {"name": "zotero_sync", "status": "not_configured"}
            )

        # 2. Discovery -------------------------------------------------
        if zotero_authoritative:
            do_discovery = False
        if do_discovery:
            step = {"name": "discovery", "started_at": _isoformat_now()}
            logger.info("stage=discovery status=start run_id=%s", run_id)
            stage_t0 = time.monotonic()
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
                logger.info(
                    "stage=discovery status=end seen=%d auto=%d queued=%d elapsed_s=%.1f",
                    disc.candidates_seen, disc.auto_ingested, disc.queued,
                    time.monotonic() - stage_t0,
                )
            except Exception as e:
                step["status"] = "skipped"
                step["error"] = f"{type(e).__name__}: {e}"
                logger.warning(
                    "stage=discovery status=skipped error=%r elapsed_s=%.1f",
                    step["error"], time.monotonic() - stage_t0,
                )
            result.steps.append(step)
        else:
            discovery_step = {"name": "discovery", "status": "disabled"}
            if zotero_authoritative:
                discovery_step["reason"] = "zotero_source_only"
            result.steps.append(discovery_step)

        # 3. Full-text evidence for new papers (best-effort) -----------
        if do_fulltext and not zotero_authoritative:
            step = {"name": "fulltext_evidence", "started_at": _isoformat_now()}
            logger.info("stage=ingest status=start run_id=%s", run_id)
            stage_t0 = time.monotonic()
            try:
                stats = _fetch_and_ingest_fulltexts(session)
                step["status"] = "ok"
                step.update(stats)
                logger.info(
                    "stage=ingest status=end attempted=%d fetched=%d failed=%d elapsed_s=%.1f",
                    stats["attempted"], stats["fetched"], stats["failed"],
                    time.monotonic() - stage_t0,
                )
            except Exception as e:
                step["status"] = "skipped"
                step["error"] = f"{type(e).__name__}: {e}"
                logger.warning(
                    "stage=ingest status=skipped error=%r elapsed_s=%.1f",
                    step["error"], time.monotonic() - stage_t0,
                )
            result.steps.append(step)
        else:
            fulltext_step = {"name": "fulltext_evidence", "status": "disabled"}
            if do_fulltext and zotero_authoritative:
                fulltext_step["reason"] = "handled_by_zotero_sync"
            result.steps.append(fulltext_step)

        # 4. Recover/execute any complete model-evolution batch --------
        step = {
            "name": "model_evolution",
            "started_at": _isoformat_now(),
        }
        logger.info("stage=model_evolution status=start run_id=%s", run_id)
        stage_t0 = time.monotonic()
        try:
            if os.environ.get("PAS_ACTIVE_LEARNING", "1") != "1":
                step["status"] = "disabled"
                step["outcome"] = "disabled"
            else:
                from app.services.model_evolution import (
                    pending_review_count,
                    reconcile_training_feedback,
                    run_pending_model_evolution,
                )

                step["reconciled_feedback"] = reconcile_training_feedback(
                    session
                )
                training_runs = run_pending_model_evolution(session)
                step["status"] = "ok"
                step["pending_reviews"] = pending_review_count(session)
                step["training_run_count"] = len(training_runs)
                step["training_run_ids"] = [
                    training_run.id for training_run in training_runs
                ]
                if not training_runs:
                    step["outcome"] = "idle"
                else:
                    training_run = training_runs[-1]
                    step["outcome"] = training_run.status.lower()
                    step["training_run_id"] = training_run.id
                    step["model_version"] = training_run.model_version
            logger.info(
                "stage=model_evolution status=end outcome=%s elapsed_s=%.1f",
                step["outcome"],
                time.monotonic() - stage_t0,
            )
        except Exception as e:
            step["status"] = "skipped"
            step["error"] = f"{type(e).__name__}: {e}"
            logger.warning(
                "stage=model_evolution status=skipped error=%r elapsed_s=%.1f",
                step["error"],
                time.monotonic() - stage_t0,
            )
        result.steps.append(step)

        # 5. Incremental classify -------------------------------------
        step = {"name": "classify_new", "started_at": _isoformat_now()}
        logger.info("stage=classify status=start run_id=%s", run_id)
        stage_t0 = time.monotonic()
        try:
            from app.services.relevance_classifier import classify_new

            touched, new_count, refreshed = classify_new(
                session,
                force=force_reclassify,
                use_learned=use_learned,
                use_judge=use_judge,
            )
            result.classified_new = new_count
            result.reclassified_stale = refreshed
            step["status"] = "ok"
            step["touched"] = len(touched)
            step["new"] = new_count
            step["refreshed"] = refreshed
            logger.info(
                "stage=classify status=end touched=%d new=%d refreshed=%d elapsed_s=%.1f",
                len(touched), new_count, refreshed, time.monotonic() - stage_t0,
            )
        except Exception as e:
            step["status"] = "failed"
            step["error"] = f"{type(e).__name__}: {e}"
            logger.error(
                "stage=classify status=failed error=%r elapsed_s=%.1f",
                step["error"], time.monotonic() - stage_t0,
            )
            raise
        result.steps.append(step)

        # 6. Route the scored corpus into the human-review subset ------
        step = {"name": "staged_screening", "started_at": _isoformat_now()}
        logger.info("stage=review_queue_refresh status=start run_id=%s", run_id)
        stage_t0 = time.monotonic()
        try:
            from app.services.review_queue import refresh_queue
            from app.services.staged_screening import staged_screening_summary

            flagged = refresh_queue(session)
            screening = staged_screening_summary(session)
            result.enqueued_for_review = flagged
            step["status"] = "ok"
            step.update(screening.pipeline_fields())
            step["queued_now"] = flagged
            logger.info(
                "stage=review_queue_refresh status=end scored=%d "
                "review_subset=%d queued_now=%d elapsed_s=%.1f",
                screening.scored,
                screening.review_subset,
                flagged,
                time.monotonic() - stage_t0,
            )
        except Exception as e:
            step["status"] = "failed"
            step["error"] = f"{type(e).__name__}: {e}"
            logger.error(
                "stage=review_queue_refresh status=failed error=%r elapsed_s=%.1f",
                step["error"], time.monotonic() - stage_t0,
            )
            raise
        result.steps.append(step)

    except Exception as e:
        result.status = "failed"
        result.error_message = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"

    result.finished_at = datetime.now(UTC)
    result.duration_seconds = round(time.monotonic() - t0, 3)

    logger.info("stage=audit status=start run_id=%s", run_id)
    stage_t0 = time.monotonic()
    _persist_run(session, result, triggered_by=triggered_by)
    logger.info(
        "stage=audit status=end run_id=%s run_status=%s duration_s=%.1f elapsed_s=%.1f",
        run_id, result.status, result.duration_seconds,
        time.monotonic() - stage_t0,
    )
    return result


def _fetch_and_ingest_fulltexts(session: Session) -> dict:
    """Best-effort OA full-text fetch for the scheduled pipeline.

    Earlier versions only re-ran evidence extraction on papers already marked
    `full_text_available=True`, which left most production papers stuck on
    abstract/metadata evidence. This step now resolves OA URLs, downloads PDFs,
    ingests sections/chunks/evidence, and leaves classification refresh to the
    following `classify_new` step.
    """
    from sqlalchemy import and_, select

    from app.config import settings
    from app.models import Paper, PaperClassification
    from app.services.fulltext_fetcher import fetch_and_ingest
    from app.services.relevance_classifier import (
        LABEL_CORE,
        LABEL_RELATED,
        LABEL_SDL_FIELD,
        LABEL_UNCERTAIN,
    )

    limit = _env_int("PAS_PIPELINE_FULLTEXT_LIMIT", default=50)
    rate_limit = _env_float("PAS_PIPELINE_FULLTEXT_RATE_LIMIT", default=1.0)
    dest_dir = settings.fulltexts_dir
    dest_dir.mkdir(parents=True, exist_ok=True)

    base = (
        select(Paper, PaperClassification)
        .outerjoin(PaperClassification, PaperClassification.paper_id == Paper.id)
        .where(Paper.doi.is_not(None), Paper.full_text_available.is_(False))
    )
    tier_queries = [
        base.where(PaperClassification.label.in_([LABEL_CORE, LABEL_RELATED])),
        base.where(Paper.provenance == "ac_gold"),
        base.where(
            and_(
                PaperClassification.label == LABEL_UNCERTAIN,
                PaperClassification.review_priority >= 0.6,
            )
        ),
        base.where(
            and_(
                PaperClassification.label == LABEL_SDL_FIELD,
                Paper.ai_decision_score == 1.0,
                Paper.automation_score == 1.0,
                Paper.closed_loop_score == 1.0,
            )
        ),
        base.where(PaperClassification.label == LABEL_SDL_FIELD),
        base.where(PaperClassification.paper_id.is_(None)),
    ]

    attempted = succeeded = failed = 0
    seen_papers: set[str] = set()
    for query in tier_queries:
        if succeeded >= limit:
            break
        for paper, _cls in session.execute(query).all():
            if succeeded >= limit:
                break
            if paper.id in seen_papers:
                continue
            seen_papers.add(paper.id)
            attempted += 1
            ok, _reason = fetch_and_ingest(
                session,
                paper.id,
                paper.doi,
                dest_dir,
                rate_limit_s=rate_limit,
            )
            if ok:
                succeeded += 1
            else:
                failed += 1
            if attempted % 25 == 0:
                session.commit()
    session.commit()
    if succeeded:
        from app.services.fulltext_service import build_chunk_embeddings

        build_chunk_embeddings(session)
    return {
        "attempted": attempted,
        "fetched": succeeded,
        "failed": failed,
        "limit": limit,
    }


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


def _env_int(name: str, *, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, *, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


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
