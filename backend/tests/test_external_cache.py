from datetime import timedelta

from app.services.external.cache import (
    cached_get,
    invalidate_cache,
    read_cache,
    write_cache,
)


def test_write_and_read_round_trip(session):
    write_cache(
        session,
        source="openalex",
        request_key="/works/doi:10.test",
        status_code=200,
        payload={"id": "W1", "title": "hello"},
    )
    status, payload = read_cache(session, "openalex", "/works/doi:10.test")
    assert status == 200
    assert payload["title"] == "hello"


def test_cached_get_skips_fetcher_on_hit(session):
    fetcher_calls = {"n": 0}

    def fetcher():
        fetcher_calls["n"] += 1
        return 200, {"hit": "first"}

    a = cached_get(session, "openalex", "/x", fetcher)
    b = cached_get(session, "openalex", "/x", fetcher)
    assert a == b == {"hit": "first"}
    assert fetcher_calls["n"] == 1


def test_invalidate_drops_rows(session):
    write_cache(session, "openalex", "/a", 200, {"v": 1})
    write_cache(session, "openalex", "/b", 200, {"v": 2})
    write_cache(session, "s2", "/c", 200, {"v": 3})
    removed = invalidate_cache(session, source="openalex")
    assert removed == 2
    assert read_cache(session, "openalex", "/a") is None
    assert read_cache(session, "s2", "/c") is not None
