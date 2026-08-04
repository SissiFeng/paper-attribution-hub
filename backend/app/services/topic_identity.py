from __future__ import annotations

from collections.abc import Collection, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Topic


def canonical_topic_names(
    session: Session,
    aliases: Mapping[str, Collection[str]],
) -> dict[str, str]:
    """Resolve one deterministic display name for every stable topic ID."""
    topic_ids = sorted(aliases)
    registered = dict(
        session.execute(
            select(Topic.id, Topic.name).where(Topic.id.in_(topic_ids))
        ).all()
    )
    resolved: dict[str, str] = {}
    for topic_id in topic_ids:
        if registered.get(topic_id):
            resolved[topic_id] = registered[topic_id]
            continue
        candidates = {name.strip() for name in aliases[topic_id] if name.strip()}
        resolved[topic_id] = (
            min(candidates, key=lambda name: (name.casefold(), name))
            if candidates
            else topic_id
        )
    return resolved
