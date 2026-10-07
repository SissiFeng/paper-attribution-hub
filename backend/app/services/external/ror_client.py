"""Cached client for the official ROR affiliation matcher."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.services.external.base import ExternalClient
from app.services.external.cache import cached_get


class RorClient(ExternalClient):
    name = "ror"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(base_url="https://api.ror.org/v2", **kwargs)

    def match_affiliation(self, session: Session, text: str) -> dict | None:
        affiliation = " ".join(str(text or "").split())
        if not affiliation:
            return None
        path = "/organizations"
        params = {"affiliation": affiliation}
        payload = cached_get(
            session,
            self.name,
            self.request_key(path, params),
            lambda: self.fetch_raw(path, params=params),
            ttl=timedelta(days=30),
        )
        for item in payload.get("items") or []:
            if item.get("chosen") is True and item.get("organization"):
                return item
        return None
