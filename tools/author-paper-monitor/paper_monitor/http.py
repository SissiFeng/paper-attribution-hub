"""Tiny stdlib HTTP helper with retries on 429/5xx. No third-party deps."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "author-paper-monitor/1.0 (mailto:{})".format(
    os.environ.get("CONTACT_EMAIL", "unknown@example.org")
)
RETRY_STATUS = {429, 500, 502, 503, 504}


def retry_delay(value: str | None, attempt: int) -> float:
    try:
        delay = float(value)
    except (ValueError, TypeError):
        try:
            delay = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            delay = 2 ** attempt
    return max(0, min(delay, 300))


def request(url: str, params: dict | None = None, *, data: bytes | None = None,
            headers: dict | None = None, retries: int = 4) -> bytes:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params, safe=':|,*')}"
    hdrs = {"User-Agent": USER_AGENT, **(headers or {})}
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code not in RETRY_STATUS or attempt == retries:
                raise
            wait = retry_delay(e.headers.get("Retry-After"), attempt)
            if e.code == 429 and wait >= 300:
                raise  # Daily budget exhaustion cannot recover within this run.
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries:
                raise
            wait = 2 ** attempt
        time.sleep(wait)
    raise RuntimeError("unreachable")


def get_json(url: str, params: dict | None = None) -> dict:
    return json.loads(request(url, params))


def post_json(url: str, payload: dict, headers: dict | None = None) -> bytes:
    return request(url, data=json.dumps(payload).encode(),
                   headers={"Content-Type": "application/json", **(headers or {})})
