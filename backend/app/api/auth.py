"""API-key auth dependency for mutating endpoints.

Set PAS_API_KEY to require the `X-API-Key` header on POST/PUT/DELETE
routes. When the key is empty (the default) auth is disabled — local dev.
"""
from __future__ import annotations

from fastapi import Header, HTTPException

from app.config import settings


def require_api_key(x_api_key: str = Header(default="")) -> None:
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
