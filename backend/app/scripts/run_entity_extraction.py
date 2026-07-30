"""Extract typed entities (method/material/instrument/software) for papers.

Usage:
    python -m app.scripts.run_entity_extraction [--paper-ids P001 P002] [--json]

Flags:
    --paper-ids  Only process these paper ids (default: all papers).
    --limit      Process at most N papers (ordered by paper id).
    --offset     Skip the first N papers (ordered by paper id).
    --if-stale-version
                 Process only papers with stale source/version fingerprints.
    --batch-size Commit this many stale papers at a time (default: 100).
    --json       Print the summary as JSON instead of text.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from time import perf_counter

from sqlalchemy import text

from app.db import SessionLocal, init_database
from app.models import PipelineRun
from app.services.entity_extractor import (
    CATALYST_EXTRACTOR_VERSION,
    run_entity_extraction,
    stale_paper_ids,
)
from app.services.ontology_service import load_ontology

DEFAULT_BATCH_SIZE = 100
_PROCESS_EXTRACTION_LOCK = Lock()
try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None


def extraction_run_id() -> str:
    ontology_version = load_ontology()["ontology_version"]
    return f"entity-extraction:{ontology_version}:{CATALYST_EXTRACTOR_VERSION}"


def _step(
    *,
    status: str,
    total_stale: int,
    processed: int,
    entities: int,
) -> dict:
    return {
        "name": "entity_extraction",
        "status": status,
        "total_stale": total_stale,
        "papers_processed": processed,
        "entities": entities,
        "extractor_version": CATALYST_EXTRACTOR_VERSION,
        "ontology_version": load_ontology()["ontology_version"],
    }


def _run_stale_batches(batch_size: int) -> dict:
    """Commit stale papers in resumable batches.

    Freshness is based on the exact title, abstract, and chunks scanned by the
    extractor plus the ontology/extractor versions. Each committed batch writes
    those per-paper fingerprints, so a later run resumes after interruption.
    """
    run_id = extraction_run_id()
    with SessionLocal() as session:
        paper_ids = stale_paper_ids(session)
        total_stale = len(paper_ids)
        existing = session.get(PipelineRun, run_id)
        if not paper_ids:
            run = existing or PipelineRun(id=run_id)
            now = datetime.now(UTC)
            run.started_at = existing.started_at if existing is not None else now
            run.finished_at = now
            run.duration_seconds = (
                existing.duration_seconds if existing is not None else 0.0
            )
            run.status = "success"
            run.error_message = None
            run.steps = [
                _step(
                    status="success",
                    total_stale=0,
                    processed=0,
                    entities=0,
                )
            ]
            run.triggered_by = "deploy_backfill"
            session.add(run)
            session.commit()
            return {
                "papers_processed": 0,
                "entities": 0,
                "by_type": {},
                "skipped": True,
                "run_id": run_id,
            }

        started_at = datetime.now(UTC)
        run = existing or PipelineRun(id=run_id)
        run.started_at = started_at
        run.finished_at = None
        run.duration_seconds = 0.0
        run.status = "running"
        run.error_message = None
        run.steps = [
            _step(
                status="running",
                total_stale=total_stale,
                processed=0,
                entities=0,
            )
        ]
        run.triggered_by = "deploy_backfill"
        session.add(run)
        session.commit()

    started = perf_counter()
    aggregate = {
        "papers_processed": 0,
        "entities": 0,
        "by_type": {},
    }
    try:
        for start in range(0, total_stale, batch_size):
            batch_ids = paper_ids[start : start + batch_size]
            with SessionLocal() as session:
                summary = run_entity_extraction(session, paper_ids=batch_ids)
                aggregate["papers_processed"] += summary["papers_processed"]
                aggregate["entities"] += summary["entities"]
                for entity_type, count in summary["by_type"].items():
                    aggregate["by_type"][entity_type] = (
                        aggregate["by_type"].get(entity_type, 0) + count
                    )
                run = session.get(PipelineRun, run_id)
                if run is None:
                    raise RuntimeError(f"Missing extraction marker {run_id}")
                run.duration_seconds = perf_counter() - started
                run.steps = [
                    _step(
                        status="running",
                        total_stale=total_stale,
                        processed=aggregate["papers_processed"],
                        entities=aggregate["entities"],
                    )
                ]
                session.commit()
    except Exception as exc:
        with SessionLocal() as session:
            run = session.get(PipelineRun, run_id) or PipelineRun(id=run_id)
            run.finished_at = datetime.now(UTC)
            run.duration_seconds = perf_counter() - started
            run.status = "failed"
            run.error_message = str(exc)
            run.steps = [
                _step(
                    status="failed",
                    total_stale=total_stale,
                    processed=aggregate["papers_processed"],
                    entities=aggregate["entities"],
                )
            ]
            run.triggered_by = "deploy_backfill"
            session.add(run)
            session.commit()
        raise

    with SessionLocal() as session:
        run = session.get(PipelineRun, run_id)
        if run is None:
            raise RuntimeError(f"Missing extraction marker {run_id}")
        run.finished_at = datetime.now(UTC)
        run.duration_seconds = perf_counter() - started
        run.status = "success"
        run.error_message = None
        run.steps = [
            _step(
                status="success",
                total_stale=total_stale,
                processed=aggregate["papers_processed"],
                entities=aggregate["entities"],
            )
        ]
        session.commit()

    return {
        **aggregate,
        "skipped": False,
        "run_id": run_id,
    }


def _lease_key() -> int:
    # One stable lock across rolling versions: old and new replicas must never
    # rewrite the compatibility projection concurrently.
    digest = hashlib.sha256(
        b"paper-attribution:entity-extraction-backfill"
    ).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def _sqlite_lock_path(lease_session) -> Path:
    database = lease_session.get_bind().url.database
    if database and database != ":memory:":
        path = Path(database)
        return path.with_name(f"{path.name}.entity-extraction.lock")
    digest = hashlib.sha256(str(database).encode("utf-8")).hexdigest()[:16]
    return Path("/tmp") / f"pas-entity-extraction-{digest}.lock"


def run_stale_batches(batch_size: int = DEFAULT_BATCH_SIZE) -> dict:
    """Run the resumable backfill under a cross-replica lease."""
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    run_id = extraction_run_id()
    with SessionLocal() as lease_session:
        is_postgres = lease_session.get_bind().dialect.name == "postgresql"
        lock_file = None
        using_process_lock = False
        if is_postgres:
            acquired = bool(
                lease_session.scalar(
                    text("SELECT pg_try_advisory_lock(:key)"),
                    {"key": _lease_key()},
                )
            )
        elif fcntl is not None:
            lock_file = _sqlite_lock_path(lease_session).open("a+")
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except BlockingIOError:
                lock_file.close()
                lock_file = None
                acquired = False
        else:  # pragma: no cover - Windows fallback
            using_process_lock = True
            acquired = _PROCESS_EXTRACTION_LOCK.acquire(blocking=False)
        if not acquired:
            return {
                "papers_processed": 0,
                "entities": 0,
                "by_type": {},
                "skipped": True,
                "reason": "lease_unavailable",
                "run_id": run_id,
            }
        try:
            return _run_stale_batches(batch_size)
        finally:
            if is_postgres:
                lease_session.execute(
                    text("SELECT pg_advisory_unlock(:key)"),
                    {"key": _lease_key()},
                )
            elif lock_file is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                lock_file.close()
            elif using_process_lock:  # pragma: no cover - Windows fallback
                _PROCESS_EXTRACTION_LOCK.release()


def run_if_stale() -> dict:
    """Backward-compatible name for the resumable deploy backfill."""
    return run_stale_batches()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run typed entity extraction.")
    parser.add_argument(
        "--paper-ids", nargs="*", default=None, help="Only process these paper ids."
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Process at most N papers."
    )
    parser.add_argument(
        "--offset", type=int, default=None, help="Skip the first N papers."
    )
    parser.add_argument(
        "--if-stale-version",
        action="store_true",
        help="Process only papers with stale source/version fingerprints.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Commit this many stale papers at a time (default: 100).",
    )
    parser.add_argument("--json", action="store_true", help="Print summary as JSON.")
    args = parser.parse_args()
    if args.if_stale_version and (
        args.paper_ids is not None or args.limit is not None or args.offset is not None
    ):
        parser.error("--if-stale-version cannot be combined with partial-run flags")

    init_database()
    if args.if_stale_version:
        summary = run_stale_batches(batch_size=args.batch_size)
    else:
        with SessionLocal() as session:
            summary = run_entity_extraction(
                session,
                paper_ids=args.paper_ids,
                limit=args.limit,
                offset=args.offset,
            )
            session.commit()

    if args.json:
        print(json.dumps(summary))
    else:
        if summary.get("skipped"):
            message = (
                "already running"
                if summary.get("reason") == "lease_unavailable"
                else "current"
            )
            print(f"Entity extraction is {message} ({summary['run_id']}).")
        else:
            print(
                f"Extracted {summary['entities']} entities from "
                f"{summary['papers_processed']} papers."
            )
        for entity_type, count in sorted(summary["by_type"].items()):
            print(f"  {entity_type}: {count}")
    if args.paper_ids and summary["papers_processed"] == 0:
        print("No matching papers found.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
