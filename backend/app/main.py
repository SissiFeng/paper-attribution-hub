from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import (
    admin,
    analytics,
    attribution_evidence_tree,
    attribution_skills,
    chat,
    discovery,
    evaluation,
    graph_explain,
    kb,
    labs,
    model_evolution,
    networks,
    papers,
    propositions,
    retrieval,
    review_queue,
    reviews,
    stage1,
    transfer_studio,
    wiki,
)
from app.config import settings
from app.db import init_database
from app.api import jev
from app.api import reader_auth, reading, access, research, catalog, exploration
from app.services.access_control import authorize_route


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_database()
    if settings.sdl_stage1_only:
        from app.db import SessionLocal
        from app.services.zotero_ingestion_service import validate_stage1_corpus

        with SessionLocal() as session:
            validate_stage1_corpus(session, require_nonempty=True)
    yield


app = FastAPI(
    title="Paper Attribution System",
    version=__version__,
    description=(
        "Evidence-based paper attribution pipeline. "
        "v0.1 ingests CSV metadata, normalizes entities, matches authors / "
        "institutions / topics, and produces an explainable relevance label "
        "with confidence and reasons."
    ),
    lifespan=lifespan,
    dependencies=[Depends(authorize_route)],
    docs_url=None, redoc_url=None, openapi_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

app.include_router(papers.router)
app.include_router(jev.router)
app.include_router(reviews.router)
app.include_router(networks.router)
app.include_router(chat.router)
app.include_router(reader_auth.router)
app.include_router(reading.router)
app.include_router(catalog.router)
app.include_router(research.router)
app.include_router(exploration.router)
from app.services.exploration_worker import install_worker
install_worker(app)
app.include_router(access.router)


@app.middleware('http')
async def private_response_cache(request, call_next):
    response = await call_next(request)
    if request.url.path != '/health':
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Vary'] = 'Cookie'
        response.headers['Referrer-Policy'] = 'no-referrer'
    return response

app.include_router(retrieval.router)
app.include_router(evaluation.router)
app.include_router(analytics.router)
app.include_router(graph_explain.router)
app.include_router(attribution_evidence_tree.router)
app.include_router(attribution_skills.router)
app.include_router(propositions.router)
app.include_router(admin.router)
app.include_router(discovery.router)
app.include_router(review_queue.router)
app.include_router(wiki.router)
app.include_router(labs.router)
app.include_router(model_evolution.router)
app.include_router(kb.router)
app.include_router(transfer_studio.router)
app.include_router(stage1.router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "version": __version__}


def _require_debug_endpoints() -> None:
    if not settings.debug_endpoints_enabled:
        raise HTTPException(status_code=404, detail="Not found")


@app.get(
    "/debug/db",
    tags=["meta"],
    include_in_schema=False,
    dependencies=[Depends(_require_debug_endpoints)],
)
def debug_db() -> dict:
    """Diagnostic: test DB connectivity and return first error encountered."""
    from sqlalchemy import text
    from app.db import engine
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"db": "ok"}
    except Exception as exc:
        return {"db": "error", "error": type(exc).__name__}


@app.get(
    "/debug/papers",
    tags=["meta"],
    include_in_schema=False,
    dependencies=[Depends(_require_debug_endpoints)],
)
def debug_papers() -> dict:
    """Diagnostic: run the simplest possible papers query and return any error."""
    import traceback
    from sqlalchemy import select
    from app.db import get_session
    from app.models import Paper
    try:
        with next(get_session()) as session:
            row = session.execute(select(Paper.id, Paper.title).limit(1)).first()
            return {"ok": True, "sample": {"id": row[0], "title": row[1]} if row else None}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "detail": str(exc)[:800],
                "trace": traceback.format_exc()[-1200:]}


@app.get(
    "/debug/multigraph",
    tags=["meta"],
    include_in_schema=False,
    dependencies=[Depends(_require_debug_endpoints)],
)
def debug_multigraph() -> dict:
    """Diagnostic: run the multi-graph build and return any error with full traceback."""
    import traceback
    from app.db import get_session
    from app.services.multi_graph import build_multi_graph, MultiGraphFilter
    from app.services.filter_spec import PaperFilter
    try:
        with next(get_session()) as session:
            filt = MultiGraphFilter(
                paper_filter=PaperFilter(year_from=2024, year_to=2025),
                node_types=["author", "institution"],
                edge_types=["affiliated_with"],
                group_by="by_institution",
                hop_limit=1,
                min_edge_weight=0.3,
            )
            result = build_multi_graph(session, filt)
            return {"ok": True, "nodes": len(result.nodes), "edges": len(result.edges)}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "detail": str(exc)[:800],
                "trace": traceback.format_exc()[-2000:]}


@app.get(
    "/debug/cors",
    tags=["meta"],
    include_in_schema=False,
    dependencies=[Depends(_require_debug_endpoints)],
)
def debug_cors() -> dict:
    """Show the CORS origins currently active on this instance."""
    return {"cors_origins": settings.cors_origins}
