"""Admin / status endpoints used by the frontend to show which parse
backend is live."""
from __future__ import annotations

import os

from fastapi import APIRouter

from app.config import settings
from app.schemas import ParseBackendStatusOut

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/parse-backend", response_model=ParseBackendStatusOut)
def parse_backend_status() -> ParseBackendStatusOut:
    from app.services.grobid_adapter import is_grobid_available

    try:
        import pymupdf  # noqa: F401

        pymupdf_available = True
    except ImportError:
        pymupdf_available = False

    return ParseBackendStatusOut(
        grobid_url=settings.grobid_url,
        grobid_reachable=is_grobid_available(settings.grobid_url),
        pymupdf_available=pymupdf_available,
        contextual_chunking=settings.contextual_chunking,
        embedding_backend=os.environ.get("PAS_EMBEDDING_BACKEND", "tfidf"),
        reranker_backend=os.environ.get("PAS_RERANKER", "none") or "none",
    )
