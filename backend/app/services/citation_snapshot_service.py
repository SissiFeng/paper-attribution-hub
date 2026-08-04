"""Persist time-stamped external citation counts for impact analytics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Paper
from app.services.external.openalex_client import OpenAlexClient


@dataclass(frozen=True)
class CitationSnapshot:
    count: int
    source: str
    updated_at: datetime


def citation_snapshot_from_raw(
    raw: dict | None,
    *,
    source: str,
    updated_at: datetime | None = None,
) -> CitationSnapshot | None:
    """Extract a citation count from supported ingestion payloads."""
    if not isinstance(raw, dict):
        return None
    nested = raw.get("raw") if isinstance(raw.get("raw"), dict) else raw
    for key in (
        "cited_by_count",
        "citationCount",
        "citedby-count",
        "cited_by",
    ):
        value = nested.get(key)
        try:
            count = int(value)
        except (TypeError, ValueError):
            continue
        if count < 0:
            continue
        return CitationSnapshot(
            count=count,
            source=source,
            updated_at=updated_at or datetime.now(UTC),
        )
    return None


def apply_citation_snapshot(paper: Paper, snapshot: CitationSnapshot) -> None:
    paper.citation_count = snapshot.count
    paper.citation_count_source = snapshot.source
    paper.citation_count_updated_at = snapshot.updated_at


def refresh_openalex_citation_snapshots(
    session: Session,
    *,
    client: OpenAlexClient | None = None,
    limit: int | None = None,
) -> dict[str, int]:
    """Refresh every resolvable paper from cached/polite OpenAlex work calls."""
    owns_client = client is None
    client = client or OpenAlexClient()
    stmt = select(Paper).order_by(Paper.id)
    if limit is not None:
        stmt = stmt.limit(limit)
    papers = list(session.scalars(stmt))
    snapshots: dict[str, CitationSnapshot] = {}
    misses = 0
    try:
        for paper in papers:
            metadata = paper.raw_metadata or {}
            openalex_id = metadata.get("openalex_id")
            work = None
            if paper.doi:
                work = client.work_by_doi(session, paper.doi)
            elif isinstance(openalex_id, str):
                work = client.work_by_id(session, openalex_id)
            snapshot = citation_snapshot_from_raw(
                work,
                source="openalex",
            )
            if snapshot is None:
                misses += 1
                continue
            snapshots[paper.id] = snapshot
    finally:
        if owns_client:
            client.close()

    for paper in papers:
        snapshot = snapshots.get(paper.id)
        if snapshot is not None:
            apply_citation_snapshot(paper, snapshot)
    session.commit()
    return {
        "papers_targeted": len(papers),
        "snapshots_updated": len(snapshots),
        "unresolved": misses,
    }
