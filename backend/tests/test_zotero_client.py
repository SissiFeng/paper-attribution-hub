from __future__ import annotations

import httpx

from app.services.zotero_client import ZoteroClient


def test_resolves_collection_and_sends_versioned_auth_headers():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/groups/42/collections"
        return httpx.Response(
            200,
            headers={"Total-Results": "1"},
            json=[{"key": "TIER1KEY", "data": {"name": "SDL keywords (tier 1)"}}],
        )

    with ZoteroClient(
        api_key="secret",
        group_id="42",
        transport=httpx.MockTransport(handler),
    ) as client:
        collection = client.resolve_collection("sdl KEYWORDS (TIER 1)")

    assert collection["key"] == "TIER1KEY"
    assert requests[0].headers["Zotero-API-Key"] == "secret"
    assert requests[0].headers["Zotero-API-Version"] == "3"


def test_retries_zotero_rate_limit_using_retry_after():
    calls = 0
    sleeps: list[float] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0.25"})
        return httpx.Response(200, json={"key": "ok"})

    with ZoteroClient(
        api_key="secret",
        group_id="42",
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
    ) as client:
        assert client.verify_key()["key"] == "ok"

    assert calls == 2
    assert sleeps == [0.25]


def test_collection_item_limit_stops_before_a_second_page():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["limit"] == "100"
        return httpx.Response(
            200,
            headers={"Total-Results": "100"},
            json=[{"key": f"K{index}", "data": {}} for index in range(100)],
        )

    with ZoteroClient(
        api_key="",
        group_id="42",
        transport=httpx.MockTransport(handler),
    ) as client:
        rows = list(client.iter_collection_top_items("TIER1", limit=3))

    assert [row["key"] for row in rows] == ["K0", "K1", "K2"]
