"""Shared HTTP plumbing for external clients.

Behaviors:
  - polite headers (User-Agent + optional `mailto` for OpenAlex)
  - exponential backoff on 5xx / 429 (up to 3 retries)
  - canonicalized request keys for the cache layer
  - injectable transport for tests (`transport` kwarg on the client)
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from app.config import settings


class ExternalError(RuntimeError):
    """Raised when an external API call fails after retries."""


class ExternalClient:
    name: str = "external"
    base_url: str = ""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        max_retries: int = 3,
        polite_mailto: str | None = None,
    ) -> None:
        self.base_url = (base_url or self.base_url).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.polite_mailto = polite_mailto or settings.openalex_mailto or None
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            transport=transport,
            headers={
                "User-Agent": (
                    f"paper-attribution-system/0.5 (+mailto:{self.polite_mailto})"
                    if self.polite_mailto
                    else "paper-attribution-system/0.5"
                ),
                "Accept": "application/json",
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def request_key(self, path: str, params: dict[str, Any] | None = None) -> str:
        """Stable canonical key for the cache layer."""
        if not params:
            return path
        items = sorted((k, str(v)) for k, v in params.items() if v is not None)
        return path + "?" + "&".join(f"{k}={v}" for k, v in items)

    def fetch_raw(
        self, path: str, params: dict[str, Any] | None = None
    ) -> tuple[int, dict]:
        """Single network call. Returns `(status, payload)` for the cache.

        Retries on 429/5xx with exponential backoff. Other 4xx responses are
        returned as-is so the cache can remember them (we don't want to retry
        a 404 forever).
        """
        delay = 1.0
        last_status = 0
        last_payload: dict = {}
        for attempt in range(self.max_retries):
            try:
                r = self._client.get(path, params=params)
            except httpx.HTTPError as e:
                last_status = 0
                last_payload = {"error": str(e)}
                time.sleep(delay)
                delay *= 2
                continue
            last_status = r.status_code
            try:
                last_payload = r.json()
            except ValueError:
                last_payload = {"raw": r.text[:1000]}
            if 200 <= r.status_code < 300:
                return r.status_code, last_payload
            if r.status_code in (429, 500, 502, 503, 504) and attempt + 1 < self.max_retries:
                time.sleep(delay)
                delay *= 2
                continue
            return r.status_code, last_payload
        return last_status or 599, last_payload
