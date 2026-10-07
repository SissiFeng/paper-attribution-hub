"""Bounded in-process scheduler; project locks make multiple replicas safe."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from sqlalchemy import select
from app.db import SessionLocal
from app.models.exploration import ResearchWatch
from app.services.research_exploration import scan_project

log = logging.getLogger(__name__)


def refresh_watches():
    with SessionLocal() as db:
        projects = list(db.scalars(select(ResearchWatch.project_id).where(ResearchWatch.enabled.is_(True))))
    for project_id in projects:
        try:
            with SessionLocal() as db:
                scan_project(db, project_id)
                db.commit()
        except Exception as exc:
            # Never log private project titles, terms, SQL parameters or notes.
            log.error('Project discovery check failed (%s); last successful check remains visible.', type(exc).__name__)


async def run(stop):
    while not stop.is_set():
        try:
            await asyncio.to_thread(refresh_watches)
        except Exception as exc:
            log.error('Project discovery unavailable (%s).', type(exc).__name__)
        try:
            await asyncio.wait_for(stop.wait(), timeout=900)
        except TimeoutError:
            pass


def install_worker(app):
    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        async with previous(app):
            if os.environ.get('PAS_EXPLORATION_WORKER') != '1':
                yield
                return
            stop = asyncio.Event(); task = asyncio.create_task(run(stop))
            try:
                yield
            finally:
                stop.set()
                await task

    app.router.lifespan_context = lifespan
