"""Optional LLM step: one-line summary, plus a relevant/not call if a
relevance brief is given. Enabled only when ANTHROPIC_API_KEY is set.

The LLM never decides what is new or whether something is a duplicate - that
is deterministic (store.py). On any LLM error the paper is kept (fail open):
an extra post is cheaper than a missed paper.
"""
from __future__ import annotations

import json
import os
import re
import sys

from . import http
from .models import Paper

API = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")

PROMPT = """You screen new publications for a research team's Slack channel.
{brief_block}
Paper:
Title: {title}
Venue: {venue}
Abstract: {abstract}

Reply with JSON only: {{"relevant": true|false, "summary": "<one plain sentence, max 30 words, on what the paper shows>"}}
{relevant_rule}"""


def enabled() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def judge(p: Paper, brief: str | None) -> bool:
    """Sets p.summary; returns whether to post."""
    prompt = PROMPT.format(
        brief_block=f"Team focus:\n{brief}\n" if brief else "",
        title=p.title, venue=p.venue or "?", abstract=(p.abstract or "(none)")[:3000],
        relevant_rule="relevant = does it match the team focus?" if brief
        else "Always set relevant to true.",
    )
    try:
        raw = http.post_json(API, {
            "model": MODEL, "max_tokens": 200,
            "messages": [{"role": "user", "content": prompt}],
        }, headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"],
                    "anthropic-version": "2023-06-01"})
        text = json.loads(raw)["content"][0]["text"]
        out = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
    except Exception as e:  # noqa: BLE001 - fail open by design
        print(f"[relevance] LLM failed for {p.title[:60]!r}: {e}", file=sys.stderr)
        return True
    if not isinstance(out, dict) or not isinstance(out.get("relevant"), bool):
        return True
    p.summary = out["summary"].strip() if isinstance(out.get("summary"), str) else None
    return out["relevant"] if brief else True
