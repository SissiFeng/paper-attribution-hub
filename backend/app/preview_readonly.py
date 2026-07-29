from __future__ import annotations

import hmac
import os
from collections.abc import Iterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.api import attribution_evidence_tree, papers
from app.db import SessionLocal, get_session

_READ_ONLY_METHODS = {"GET", "HEAD", "OPTIONS"}
_TOKEN_HEADER = "x-preview-token"

app = FastAPI(
    title="Paper Attribution System — Read-only Preview",
    version=__version__,
    description="Read-only API surface for the interactive attribution evidence map.",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


def get_read_only_session() -> Iterator[Session]:
    session = SessionLocal()
    is_sqlite = session.get_bind().dialect.name == "sqlite"
    try:
        if is_sqlite:
            session.execute(text("PRAGMA query_only = ON"))
        else:
            session.connection(
                execution_options={"postgresql_readonly": True}
            )
        yield session
    finally:
        session.rollback()
        if is_sqlite:
            session.execute(text("PRAGMA query_only = OFF"))
            session.commit()
        session.close()


app.dependency_overrides[get_session] = get_read_only_session


@app.middleware("http")
async def enforce_read_only(request: Request, call_next):
    if request.method not in _READ_ONLY_METHODS:
        return JSONResponse(
            status_code=405,
            content={"detail": "Read-only preview: method not allowed"},
        )
    if request.url.path != "/health":
        expected = os.environ.get("PAS_PREVIEW_API_TOKEN", "")
        provided = request.headers.get(_TOKEN_HEADER, "")
        if not expected:
            return JSONResponse(
                status_code=503,
                content={"detail": "Preview authentication is not configured"},
            )
        if not hmac.compare_digest(
            provided.encode("utf-8"), expected.encode("utf-8")
        ):
            return JSONResponse(
                status_code=401,
                content={"detail": "Preview authentication required"},
            )
    return await call_next(request)


app.add_api_route(
    "/papers",
    papers.list_papers,
    methods=["GET"],
    tags=["papers"],
)
app.add_api_route(
    "/papers/{paper_id}",
    papers.get_paper,
    methods=["GET"],
    tags=["papers"],
)
app.add_api_route(
    "/papers/{paper_id}/attribution-evidence-tree",
    attribution_evidence_tree.attribution_evidence_tree,
    methods=["GET"],
    tags=["attribution_evidence_tree"],
)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "version": __version__, "mode": "read-only-preview"}
