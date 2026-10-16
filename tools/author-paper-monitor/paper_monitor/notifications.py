"""Immediate private paper cards plus an independently receipted weekly recap."""

from __future__ import annotations

import datetime as dt
import json
import os
import time
import urllib.error

from . import slack_app


def _post(store, payload, before, success, rejected, *, callbacks_commit=False):
    retry_at = float(store.meta('slack_retry_after') or 0)
    if time.time() < retry_at:
        return ['Slack rate limit: waiting for Retry-After before delivery']
    token = os.environ.get('SLACK_BOT_TOKEN')
    if not token:
        return ['Slack credentials unavailable; no delivery was attempted']
    before()
    if not callbacks_commit:
        store.commit()  # The cloud store checkpoints this before the external write.
    try:
        result = slack_app.api(
            token, "chat.postMessage", payload
        )
        if not result.get("ts"):
            raise ValueError("Missing Slack receipt")
    except (slack_app.SlackRejected, urllib.error.HTTPError) as exc:
        delay = slack_app.retry_delay(exc)
        if delay is not None:
            store.set_meta('slack_retry_after', str(time.time() + delay))
            rejected()
            if not callbacks_commit:
                store.commit()
        return ["Slack rejected or failed delivery; inspect the saved delivery state"]
    except (OSError, ValueError):
        return ["Slack delivery uncertain; inspect Slack before reconciliation"]
    success(result["ts"])
    if not callbacks_commit:
        store.commit()
    time.sleep(1.1)
    return []


def send(store, queue, unsynced, *, now=None):
    channel = os.environ.get("SLACK_CHANNEL_ID", "")
    if not channel.startswith("D"):
        return ["Personal mode requires a direct-message destination"]
    errors = []
    legacy = json.loads(store.meta("weekly_digest") or "{}")
    if legacy.get("status") == "sending":
        return ["Legacy digest delivery uncertain; reconcile its parent receipt"]
    legacy_ids = set(legacy.get("ids", []))
    if legacy.get("status") == "posted" and any(i in legacy_ids for i, _ in store.pending(100000)):
        from . import digest
        errors.extend(digest.send(store, queue, unsynced, now=now))
        queue = [(i, p) for i, p in queue if i not in legacy_ids]
        if errors:
            return errors
    for row_id, paper in queue:
        if row_id in unsynced:
            continue
        receipt = store.db.execute("SELECT pas_id FROM ingestion WHERE paper_id=?", (row_id,)).fetchone()
        errors.extend(
            _post(
                store,
                {"channel": channel, **slack_app.card(paper, pas_id=receipt[0] if receipt else None)},
                lambda row_id=row_id: store.set_status(row_id, "sending"),
                lambda ts, row_id=row_id: store.mark_notified(row_id, channel, ts),
                lambda row_id=row_id: store.set_status(row_id, "pending"),
                callbacks_commit=True,
            )
        )
        if errors:
            break
    errors.extend(recap(store, now=now))
    return errors


def recap(store, *, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    end = (now - dt.timedelta(days=now.weekday())).replace(
        hour=12, minute=0, second=0, microsecond=0
    )
    if now < end:
        end -= dt.timedelta(days=7)
    week = end.date().isoformat()
    state = json.loads(store.meta("weekly_recap") or "{}")
    if state.get("status") == "sending" or "sending" in state.get("pages", {}).values():
        return ["Weekly recap delivery uncertain; reconcile before replay"]
    if state.get("week") == week and state.get("status") == "complete":
        return []
    # Finish an existing recap before starting a newer period.
    if state.get("status") not in ("pending", "posted"):
        start = end - dt.timedelta(days=7)
        rows = store.posted_between(start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds"))
        state = {
            "week": week,
            "status": "pending" if rows else "complete",
            "ids": [i for i, _ in rows],
            "pages": {},
            "channel": os.environ["SLACK_CHANNEL_ID"],
        }
        store.set_meta("weekly_recap", json.dumps(state))
        store.commit()
    if state["status"] == "complete":
        return []
    if state["channel"] != os.environ["SLACK_CHANNEL_ID"] or not state[
        "channel"
    ].startswith("D"):
        return ["Weekly recap destination changed; reconcile before sending"]

    def save(status=None):
        if status:
            state["status"] = status
        store.set_meta("weekly_recap", json.dumps(state))

    if state["status"] == "pending":
        text = f"AC · Weekly recap · {len(state['ids'])} papers\nThese papers were already sent privately during the week ending {state['week']}. The reading list is in the thread."

        def parent_ok(ts):
            state["ts"] = ts
            save("posted")

        errors = _post(
            store,
            {
                "channel": state["channel"],
                "text": text,
                "blocks": [slack_app.section(text)],
            },
            lambda: save("sending"),
            parent_ok,
            lambda: save("pending"),
        )
        if errors:
            return errors
    papers = dict(store.rows("SELECT id,data FROM papers"))
    for index in range(0, len(state["ids"]), 10):
        key = str(index // 10)
        if state["pages"].get(key) == "posted":
            continue
        entries = [papers[i] for i in state["ids"][index : index + 10]]
        blocks = [slack_app.section(slack_app.paper_link(p)) for p in entries]

        def page_state(value, ts=None, key=key):
            state["pages"][key] = value
            if ts:
                state.setdefault("page_receipts", {})[key] = ts
            save()

        errors = _post(
            store,
            {
                "channel": state["channel"],
                "thread_ts": state["ts"],
                "text": "Weekly reading list",
                "blocks": blocks,
            },
            lambda: page_state("sending"),
            lambda ts: page_state("posted", ts),
            lambda: page_state("pending"),
        )
        if errors:
            return errors
    save("complete")
    store.commit()
    return []
