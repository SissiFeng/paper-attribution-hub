"""Frequent recent scans and a weekly wider scan with a quiet initial baseline."""

import datetime as dt
import os


def window(store, *, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    recent = max(1, int(os.environ.get("LOOKBACK_DAYS", "90")))
    deep = max(recent, int(os.environ.get("DEEP_LOOKBACK_DAYS", str(recent))))
    previous = store.meta("last_deep_collection")
    due = deep > recent and (
        not previous
        or (now - dt.datetime.fromisoformat(previous)).total_seconds() >= 7 * 86400
    )
    return {
        "since": (now.date() - dt.timedelta(days=deep if due else recent)).isoformat(),
        "recent_since": (now.date() - dt.timedelta(days=recent)).isoformat(),
        "deep": due,
        "seed_older": due and not store.meta("deep_initialized"),
        "at": now.isoformat(),
    }


def silent_history(paper, policy):
    return bool(
        policy["seed_older"]
        and paper.date
        and paper.date < policy["recent_since"]
        and "scholar_alert" not in paper.sources
    )
