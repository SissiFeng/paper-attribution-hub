"""Admin / status endpoints used by the frontend to show which parse
backend is live."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
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


@router.post("/seed-chunks", response_model=dict)
def seed_chunks(
    background_tasks: BackgroundTasks,
    force: bool = False,
    session: Session = Depends(get_session),
) -> dict:
    """Trigger abstract-chunk seeding in the background.

    Idempotent: skips papers that already have chunks unless force=true.
    Call once after first deploy to populate the RAG corpus.
    """
    from app.models import PaperChunk
    from sqlalchemy import select, func

    chunk_count = session.scalar(select(func.count()).select_from(PaperChunk)) or 0
    if chunk_count > 0 and not force:
        return {
            "status": "skipped",
            "reason": f"corpus already has {chunk_count} chunks; pass force=true to rebuild",
        }

    def _run():
        from app.scripts.seed_abstract_chunks import run
        run(force=force)

    background_tasks.add_task(_run)
    return {"status": "started", "message": "seeding chunks in background; check /admin/chunk-stats shortly"}


@router.get("/accuracy", response_model=dict)
def accuracy_report(session: Session = Depends(get_session)) -> dict:
    """Live accuracy report against the AC Publications gold set.

    Returns precision, recall, F1, and a list of any gold-set papers that
    are labelled below RELATED_RELEVANT (failures).
    """
    from app.scripts.measure_accuracy import measure
    return measure(session)


@router.get("/vocabulary-suggestions", response_model=list[dict])
def vocabulary_suggestions(
    max_suggestions: int = 20,
    min_positive_freq: int = 3,
    session: Session = Depends(get_session),
) -> list[dict]:
    """Candidate terms mined from the AC gold set for human review.

    Returns bigrams that are distinctive to ac_known_publication=True papers
    versus the background corpus.  action is one of:
      - "add_protected_phrase": add to domain_vocabulary.yaml protected_phrases
      - "add_keyword":          add to topic_taxonomy.yaml keywords
    Nothing is written automatically — this is read-only.
    """
    from app.services.active_learning import mine_positive_vocabulary

    suggestions = mine_positive_vocabulary(
        session,
        max_suggestions=max_suggestions,
        min_positive_freq=min_positive_freq,
    )
    return [
        {
            "topic_id": s.topic_id,
            "topic_name": s.topic_name,
            "suggested_term": s.suggested_term,
            "score": s.score,
            "action": s.action,
            "rationale": s.rationale,
        }
        for s in suggestions
    ]


@router.post("/reclassify", response_model=dict)
def reclassify(
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    """Re-run classify_all() in the background.

    Call this after deploying a classifier change to apply it to the full
    corpus without a redeploy. Takes ~5 minutes on the full 11K-paper set.
    Returns immediately; check /admin/accuracy afterwards.
    """
    def _run():
        from app.services.relevance_classifier import classify_all
        from app.db import SessionLocal
        with SessionLocal() as s:
            classify_all(s)

    background_tasks.add_task(_run)
    return {"status": "started", "message": "reclassification running in background"}


@router.post("/apply-ac-members", response_model=dict)
def apply_ac_members(
    background_tasks: BackgroundTasks,
    skip_classify: bool = False,
) -> dict:
    """Apply the updated ac_members.csv to the DB.

    Matches all 82 CSV members against existing Author records, marks them
    is_ac_member=True, creates new Author rows for any missing members,
    updates Paper.ac_members_matched, then re-classifies (unless
    skip_classify=true).

    Safe to call multiple times — idempotent.
    """
    def _run():
        from app.scripts.apply_ac_members import run
        run(dry_run=False, skip_classify=skip_classify)

    background_tasks.add_task(_run)
    return {
        "status": "started",
        "message": (
            "Applying AC members in background. "
            "Watch server logs; then call GET /admin/accuracy to verify."
        ),
    }
