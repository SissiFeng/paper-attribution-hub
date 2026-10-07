"""PAS ingestion inside the backend worker image, using its existing DB models.

Inbox mode preserves the authoritative Zotero corpus. Main mode is allowed only
when PAS itself permits a non-Zotero corpus. No classification is fabricated.
"""
from __future__ import annotations

import dataclasses
import hashlib
import os

from .models import Paper


def configured() -> bool:
    return os.environ.get("PAS_MONITOR_INGEST") == "1"


def ingest(p: Paper) -> str:
    from app.db import SessionLocal

    with SessionLocal() as session:
        receipt = ingest_session(session, p, os.environ.get("PAS_MONITOR_MODE", "inbox"))
        session.commit()
        return receipt


def ingest_session(session, p: Paper, mode: str = "inbox") -> str:
    from sqlalchemy import or_, select
    from app.config import settings
    from app.models import DiscoveryCandidate, Paper as PasPaper

    if mode not in {"inbox", "main"}:
        raise ValueError("PAS_MONITOR_MODE must be inbox or main")
    if mode == "main" and (settings.sdl_stage1_only or settings.zotero_source_only):
        raise ValueError("PAS corpus policy requires inbox mode")
    identity = p.doi or p.openalex_id or p.arxiv_id
    if not identity:
        identity = "title:" + (p.title_key or "") + "|" + "|".join(sorted(p.authors))
    key = "monitor_" + hashlib.sha256(identity.encode()).hexdigest()[:32]
    clauses = [PasPaper.id == key]
    if p.doi_aliases:
        clauses.append(PasPaper.doi.in_(p.doi_aliases))
    existing = session.scalar(select(PasPaper).where(or_(*clauses)))
    if existing:
        if existing.provenance == "author_monitor":
            existing.raw_metadata = {
                **(existing.raw_metadata or {}), "author_monitor": dataclasses.asdict(p)
            }
            session.flush()
        return existing.id

    payload = dataclasses.asdict(p)
    if mode == "inbox":
        clauses = [DiscoveryCandidate.external_id == identity]
        if p.doi_aliases:
            clauses.append(DiscoveryCandidate.doi.in_(p.doi_aliases))
        row = session.scalar(select(DiscoveryCandidate).where(or_(*clauses)))
        if row is None:
            row = DiscoveryCandidate(
                id=key, external_id=identity, doi=p.doi, title=p.title,
                abstract=p.abstract, year=int(p.date[:4]) if p.date else None,
                venue=p.venue, authors=[{"name": n} for n in p.authors],
                affiliations=[], source="author_monitor", status="queued",
                confidence=0.0, auto_eligible=False,
                triggers=[{"strategy": "author_monitor", "source": "openalex", "weight": 0.0,
                           "detail": ", ".join(p.tracked_authors)}],
                raw_payload=payload,
            )
            session.add(row)
        session.flush()
        return row.id

    from app.services.ingestion_service import _attach_authors

    row = PasPaper(id=key, title=p.title, abstract=p.abstract, doi=p.doi,
                   year=int(p.date[:4]) if p.date else None, venue=p.venue,
                   source="author_monitor", provenance="author_monitor",
                   corpus_sources=["AUTHOR_MONITOR"], raw_metadata={"author_monitor": payload})
    session.add(row)
    session.flush()
    _attach_authors(session, row, p.authors, [])
    session.flush()
    return row.id
