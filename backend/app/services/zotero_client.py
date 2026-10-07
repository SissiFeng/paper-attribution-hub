"""Small, deterministic client for Zotero group-library reads."""
from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import httpx


class ZoteroAPIError(RuntimeError):
    """Raised when a Zotero request cannot be completed safely."""


@dataclass(frozen=True)
class ZoteroDownload:
    content: bytes
    content_type: str
    filename: str | None


class ZoteroClient:
    def __init__(
        self,
        *,
        api_key: str,
        group_id: str,
        base_url: str = "https://api.zotero.org",
        timeout: float = 60.0,
        max_retries: int = 5,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not str(group_id).strip():
            raise ValueError("Zotero group_id is required")
        self.group_id = str(group_id).strip()
        self.max_retries = max_retries
        self._sleep = sleep
        headers = {
            "Accept": "application/json",
            "User-Agent": "paper-attribution-system/zotero-sync",
            "Zotero-API-Version": "3",
        }
        if api_key:
            headers["Zotero-API-Key"] = api_key
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ZoteroClient:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    @property
    def _group_prefix(self) -> str:
        return f"/groups/{self.group_id}"

    def verify_key(self) -> dict[str, Any]:
        return self._request_json("/keys/current")

    def iter_collections(self) -> Iterator[dict[str, Any]]:
        yield from self._iter_objects(f"{self._group_prefix}/collections")

    def resolve_collection(self, identifier: str) -> dict[str, Any]:
        wanted = identifier.strip()
        if not wanted:
            raise ValueError("Zotero collection identifier is required")
        matches = []
        for collection in self.iter_collections():
            key = str(collection.get("key") or "")
            name = str((collection.get("data") or {}).get("name") or "")
            if key == wanted or name.casefold() == wanted.casefold():
                matches.append(collection)
        if not matches:
            raise ZoteroAPIError(f"Zotero collection not found: {wanted!r}")
        exact_key = [row for row in matches if row.get("key") == wanted]
        if exact_key:
            return exact_key[0]
        if len(matches) > 1:
            raise ZoteroAPIError(
                f"Zotero collection name is ambiguous: {wanted!r}; configure its key"
            )
        return matches[0]

    def iter_collection_top_items(
        self, collection_key: str, *, limit: int | None = None
    ) -> Iterator[dict[str, Any]]:
        path = (
            f"{self._group_prefix}/collections/{collection_key}/items/top"
        )
        yield from self._iter_objects(path, limit=limit)

    def iter_attachments(self) -> Iterator[dict[str, Any]]:
        yield from self._iter_objects(
            f"{self._group_prefix}/items",
            params={"itemType": "attachment"},
        )

    def download_attachment(
        self, attachment_key: str, *, filename: str | None = None
    ) -> ZoteroDownload:
        response = self._request(
            f"{self._group_prefix}/items/{attachment_key}/file",
            accept="application/pdf,application/octet-stream",
        )
        return ZoteroDownload(
            content=response.content,
            content_type=response.headers.get(
                "content-type", "application/octet-stream"
            ).split(";", 1)[0],
            filename=filename,
        )

    def attachment_fulltext(self, attachment_key: str) -> str | None:
        response = self._request(
            f"{self._group_prefix}/items/{attachment_key}/fulltext",
            allow_not_found=True,
        )
        if response.status_code == 404:
            return None
        payload = self._json_payload(response)
        content = payload.get("content")
        return str(content) if content else None

    def _iter_objects(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        start = 0
        yielded = 0
        while True:
            page_params = {**(params or {}), "limit": 100, "start": start}
            response = self._request(path, params=page_params)
            payload = self._json_payload(response)
            if not isinstance(payload, list):
                raise ZoteroAPIError(f"Expected a Zotero list response for {path}")
            for row in payload:
                if not isinstance(row, dict):
                    continue
                yield row
                yielded += 1
                if limit is not None and yielded >= limit:
                    return
            if not payload:
                return
            start += len(payload)
            total = _optional_int(response.headers.get("Total-Results"))
            if total is not None and start >= total:
                return
            if len(payload) < 100:
                return

    def _request_json(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload = self._json_payload(self._request(path, params=params))
        if not isinstance(payload, dict):
            raise ZoteroAPIError(f"Expected a Zotero object response for {path}")
        return payload

    def _request(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        accept: str | None = None,
        allow_not_found: bool = False,
    ) -> httpx.Response:
        delay = 1.0
        for attempt in range(self.max_retries):
            try:
                response = self._client.get(
                    path,
                    params=params,
                    headers={"Accept": accept} if accept else None,
                )
            except httpx.HTTPError as exc:
                if attempt + 1 >= self.max_retries:
                    raise ZoteroAPIError(
                        f"Zotero request failed for {path}: {type(exc).__name__}"
                    ) from exc
                self._sleep(delay)
                delay *= 2
                continue

            if response.status_code == 404 and allow_not_found:
                return response
            if 200 <= response.status_code < 300:
                backoff = _optional_float(response.headers.get("Backoff"))
                if backoff:
                    self._sleep(backoff)
                return response
            if response.status_code in {429, 500, 502, 503, 504}:
                if attempt + 1 < self.max_retries:
                    retry_after = _optional_float(
                        response.headers.get("Retry-After")
                    )
                    self._sleep(retry_after if retry_after is not None else delay)
                    delay *= 2
                    continue
            raise ZoteroAPIError(
                f"Zotero request {path} returned HTTP {response.status_code}"
            )
        raise ZoteroAPIError(f"Zotero request failed for {path}")

    @staticmethod
    def _json_payload(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise ZoteroAPIError("Zotero returned invalid JSON") from exc


def _optional_int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _optional_float(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None
