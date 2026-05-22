"""Graph-RAG explanation endpoint.

This is the "why" layer figure.md describes: when a user clicks a paper, we
return a structured explanation of all graph paths supporting (or undermining)
its classification. No LLM is involved — the explanation is assembled from
graph signals already computed by `graph_service`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import AcCorePaper, Paper, PaperReference
from app.schemas import (
    CitationSignalOut,
    GraphExplanationOut,
    SecondDegreePathOut,
)
from app.services.graph_service import compute_graph_signals

router = APIRouter(prefix="/papers", tags=["graph_rag"])


@router.get("/{paper_id}/graph-explanation", response_model=GraphExplanationOut)
def graph_explanation(
    paper_id: str, session: Session = Depends(get_session)
) -> GraphExplanationOut:
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail=f"Paper {paper_id} not found")

    signals = compute_graph_signals(session).get(paper_id)
    if signals is None:
        raise HTTPException(status_code=500, detail="Graph signals missing")

    direct_ac_authors = [
        pa.author.canonical_name for pa in paper.authors if pa.author.is_ac_member
    ]

    cited_by_corpus = [
        r.citing_paper_id
        for r in session.execute(
            select(PaperReference).where(PaperReference.cited_paper_id == paper_id)
        ).scalars()
    ]

    summary = _summarize(
        paper_id=paper_id,
        direct=direct_ac_authors,
        second_degree=signals.second_degree_paths,
        citation_signals=signals.citation_signals,
        cited_by=cited_by_corpus,
    )

    return GraphExplanationOut(
        paper_id=paper_id,
        summary=summary,
        direct_ac_authors=direct_ac_authors,
        second_degree_paths=[
            SecondDegreePathOut(
                via_author_id=p.via_author_id,
                via_author_name=p.via_author_name,
                ac_author_id=p.ac_author_id,
                ac_author_name=p.ac_author_name,
                shared_papers=p.shared_papers,
                strength=p.strength,
            )
            for p in signals.second_degree_paths
        ],
        citation_signals=[
            CitationSignalOut(
                cited_ac_core_id=s.cited_ac_core_id,
                cited_ac_core_title=s.cited_ac_core_title,
                cited_doi=s.cited_doi,
            )
            for s in signals.citation_signals
        ],
        cites_corpus=signals.cites_corpus,
        cited_by_corpus=cited_by_corpus,
    )


def _summarize(
    *,
    paper_id: str,
    direct: list[str],
    second_degree,
    citation_signals,
    cited_by,
) -> str:
    parts: list[str] = []
    if direct:
        parts.append(f"Direct AC author(s): {', '.join(direct)}.")
    if second_degree:
        names = ", ".join(
            f"{p.via_author_name} ↔ {p.ac_author_name}" for p in second_degree[:3]
        )
        parts.append(
            f"{len(second_degree)} second-degree collaborator path(s): {names}."
        )
    if citation_signals:
        titles = ", ".join(s.cited_ac_core_title for s in citation_signals[:3])
        parts.append(
            f"Cites {len(citation_signals)} AC core paper(s): {titles}."
        )
    if cited_by:
        parts.append(f"Cited by {len(cited_by)} other paper(s) in the corpus.")
    if not parts:
        parts.append(
            "No direct or graph-based AC connection detected; only topic / "
            "metadata signals (if any) apply."
        )
    return " ".join(parts)
