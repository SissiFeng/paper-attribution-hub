"""Slack output via an Incoming Webhook (SLACK_WEBHOOK_URL).

This is the only piece that needs a Slack-side setup. Without the webhook,
`run` writes what it would post to outbox/pending.json and keeps those papers
pending, so they go out on the first run after the webhook is added.
"""
from __future__ import annotations

import os
import urllib.parse

from . import http
from .models import Paper

from .paper_preview import preview


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def configured() -> bool:
    return bool(os.environ.get("SLACK_WEBHOOK_URL") or
                (os.environ.get("SLACK_BOT_TOKEN") and os.environ.get("SLACK_CHANNEL_ID")))


def format_message(p: Paper) -> dict:
    tracked = _esc(", ".join(p.tracked_authors))
    meta = _esc(" · ".join(x for x in (p.venue, p.date) if x))
    title = _esc(p.title[:600]).replace("|", "¦")
    url = p.url if p.url and urllib.parse.urlsplit(p.url).scheme in {"http", "https"} else None
    url = _esc(url).replace("|", "%7C") if url else None
    lines = [f":page_facing_up: *<{url}|{title}>*" if url else f":page_facing_up: *{title}*"]
    kind, brief = preview(p)
    if brief:
        label = '*Keywords:* ' if kind == 'keywords' else ('*Abstract:* ' if kind == 'abstract' else '> ')
        lines.append(label + _esc(brief))
    if meta:
        lines.append(f"_{meta}_")
    return {
        "text": _esc(p.title[:600]) + (" · " + _esc(brief) if brief else ""),  # notification fallback
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)[:3000]}},
            {"type": "context", "elements": [{"type": "mrkdwn",
                "text": f"Tracked: {tracked} · via {', '.join(p.sources)}"[:2000]}]},
        ],
    }


def post(p: Paper) -> None:
    """Raises on failure; caller marks posted only after this returns."""
    import json
    response = http.request(os.environ["SLACK_WEBHOOK_URL"],
                            data=json.dumps(format_message(p)).encode(),
                            headers={"Content-Type": "application/json"}, retries=0)
    if response.strip() != b"ok":
        raise ValueError("Slack response was not 'ok'; delivery requires reconciliation")
