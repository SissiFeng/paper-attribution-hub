"""SQLite-backed cache for external API responses.

Why a DB cache and not a file cache:
- It rides on the same SQLAlchemy session machinery we already use for tests.
- Tests can pre-populate it (via `write_cache`) to bypass HTTP entirely.
- Invalidation / inspection through the same query layer.
- No new infra for a tiny throughput requirement (<10k calls/day).

Cache key convention: `<endpoint>` + a stable canonical query string. Callers
should normalize DOIs / IDs before passing them in.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ExternalCache


def _utcnow() -> datetime:
    return datetime.now(UTC)


def read_cache(
    session: Session, source: str, request_key: str
) -> tuple[int, dict] | None:
    row = session.execute(
        select(ExternalCache)
        .where(ExternalCache.source == source)
        .where(ExternalCache.request_key == request_key)
        .order_by(ExternalCache.fetched_at.desc())
    ).scalars().first()
    if row is None:
        return None
    if row.expires_at is not None:
        # Compare naively when stored without timezone — SQLite drops tz info.
        expires = row.expires_at
        now = _utcnow()
        if expires.tzinfo is None:
            now = now.replace(tzinfo=None)
        if expires < now:
            return None
    return row.status_code, (row.payload or {})


def write_cache(
    session: Session,
    source: str,
    request_key: str,
    status_code: int,
    payload: dict,
    ttl: timedelta | None = None,
) -> None:
    expires_at = None
    if ttl is not None:
        expires_at = _utcnow() + ttl
    session.add(
        ExternalCache(
            id=f"cache_{uuid.uuid4().hex[:12]}",
            source=source,
            request_key=request_key,
            status_code=status_code,
            payload=payload,
            fetched_at=_utcnow(),
            expires_at=expires_at,
        )
    )
    session.commit()


def invalidate_cache(
    session: Session, source: str | None = None, request_key: str | None = None
) -> int:
    """Drop matching cache rows. Returns number deleted."""
    stmt = select(ExternalCache)
    if source:
        stmt = stmt.where(ExternalCache.source == source)
    if request_key:
        stmt = stmt.where(ExternalCache.request_key == request_key)
    rows = session.execute(stmt).scalars().all()
    for r in rows:
        session.delete(r)
    session.commit()
    return len(rows)


def cached_get(
    session: Session,
    source: str,
    request_key: str,
    fetcher,
    ttl: timedelta | None = None,
) -> dict:
    """Try cache; on miss, call `fetcher()` and store its result.

    `fetcher()` must return `(status_code, payload_dict)`. Tests can pass a
    fetcher that returns canned data — no network involved.

    Behavior on non-2xx (4xx most common — "not found"):
      - Cache the response so we don't hammer the API.
      - Return the payload (usually `{}` for 404). Callers must treat empty
        payloads as "no data" rather than expecting an exception.
      - Use a shorter TTL for non-2xx so we eventually re-check once the
        external API indexes the resource.
    """
    cached = read_cache(session, source, request_key)
    if cached is not None:
        _status, payload = cached
        return payload
    status, payload = fetcher()
    effective_ttl = ttl
    if status >= 400 and ttl is not None:
        # Short negative cache so we re-check soon.
        effective_ttl = min(ttl, timedelta(hours=1))
    write_cache(session, source, request_key, status, payload, ttl=effective_ttl)
    return payload
