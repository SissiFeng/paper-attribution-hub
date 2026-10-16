"""PAS ingestion inside the backend worker image, using its existing DB models.

Inbox mode preserves the authoritative Zotero corpus. Main mode is allowed only
when PAS itself permits a non-Zotero corpus. No classification is fabricated.
"""
from __future__ import annotations

import dataclasses
import hashlib
import os

from .models import Paper, normalize_title, title_matches


def configured() -> bool:
    return os.environ.get("PAS_MONITOR_INGEST") == "1"


def paper_id(p: Paper) -> str:
    identity = p.doi or p.openalex_id or p.arxiv_id
    if not identity:
        identity = "title:" + (p.title_key or "") + "|" + "|".join(sorted(p.authors))
    return "monitor_" + hashlib.sha256(identity.encode()).hexdigest()[:32]


def ingest(p: Paper, *, existing_id: str | None = None) -> str:
    from app.db import SessionLocal

    with SessionLocal() as session:
        receipt = ingest_session(session, p, os.environ.get("PAS_MONITOR_MODE", "inbox"), existing_id=existing_id)
        session.commit()
        return receipt


def ingest_session(session, p: Paper, mode: str = "inbox", *, existing_id: str | None = None) -> str:
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
    key = existing_id or paper_id(p)
    clauses = [PasPaper.id.in_([key, paper_id(p)])]
    if p.doi_aliases:
        clauses.append(PasPaper.doi.in_(p.doi_aliases))
    matches = list(session.scalars(select(PasPaper).where(or_(*clauses))))
    if not matches:
        # Match the existing PAS corpus too, not only monitor-created rows. A
        # title alone is never sufficient; use the same conservative ID/author rules.
        ids = [i for i, title in session.execute(select(PasPaper.id, PasPaper.title))
               if normalize_title(title) == p.title_key]
        for candidate in session.scalars(select(PasPaper).where(PasPaper.id.in_(ids))):
            data = (candidate.raw_metadata or {}).get('author_monitor')
            previous = Paper(**data) if data else Paper(candidate.title, doi=candidate.doi,
                authors=[link.author.canonical_name for link in candidate.authors])
            if title_matches(previous, p):
                matches.append(candidate)
    if len(matches) > 1:
        raise ValueError('Multiple PAS identities require reconciliation; no records were merged')
    existing = matches[0] if matches else None
    if existing:
        if existing_id and existing_id != existing.id and session.get(PasPaper, existing_id):
            raise ValueError('PAS identity conflict requires reconciliation')
        if existing.provenance == "author_monitor":
            existing.raw_metadata = {
                **(existing.raw_metadata or {}), "author_monitor": dataclasses.asdict(p)
            }
            for field in ('doi', 'abstract', 'venue'):
                if not getattr(existing, field) and getattr(p, field):
                    setattr(existing, field, getattr(p, field))
            if not existing.year and p.date:
                existing.year = int(p.date[:4])
            if not existing.keywords and p.keywords:
                existing.keywords = p.keywords
            session.flush()
        return existing.id

    payload = dataclasses.asdict(p)
    if mode == "inbox":
        clauses = [DiscoveryCandidate.id == key, DiscoveryCandidate.external_id == identity]
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
        else:
            row.raw_payload = payload
            row.doi = row.doi or p.doi
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
