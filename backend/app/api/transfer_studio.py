from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Paper, TransferKnowledgeUnit
from app.schemas import (
    EvolutionaryTransferOut,
    EvolutionaryTransferRequest,
    TransferDesignOut,
    TransferDesignRequest,
    TransferMatchOut,
    TransferTargetOut,
    TransferTkuOut,
)
from app.services.evolutionary_transfer_service import (
    EvolutionConfig,
    run_evolutionary_transfer_search,
)
from app.services.transfer_designer import generate_design, load_target, load_targets

router = APIRouter(prefix="/transfer", tags=["transfer"])


@router.get("/targets", response_model=list[TransferTargetOut])
def targets() -> list[TransferTargetOut]:
    """The curated SDL target profiles (data/sdl_targets.yaml)."""
    return [
        TransferTargetOut(
            id=t["id"],
            name=t.get("name", t["id"]),
            description=(t.get("description") or "").strip(),
            typical_signature=t.get("typical_signature") or {},
            typical_constraints=t.get("typical_constraints") or [],
            keywords=t.get("keywords") or [],
        )
        for t in load_targets()
    ]


@router.get("/tkus", response_model=list[TransferTkuOut])
def tkus(
    source_domain: str | None = Query(default=None),
    task_type: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[TransferTkuOut]:
    """List extracted TKUs with their source paper title/year, optionally
    filtered by source domain and/or problem-signature task type."""
    stmt = select(TransferKnowledgeUnit)
    if source_domain:
        stmt = stmt.where(TransferKnowledgeUnit.source_domain == source_domain)
    out: list[TransferTkuOut] = []
    for tku in session.execute(stmt).scalars():
        sig = tku.problem_signature or {}
        if task_type and sig.get("task_type") != task_type:
            continue
        paper = session.get(Paper, tku.paper_id)
        out.append(
            TransferTkuOut(
                id=tku.id,
                paper_id=tku.paper_id,
                paper_title=paper.title if paper else tku.paper_id,
                paper_year=paper.year if paper else None,
                source_domain=tku.source_domain,
                problem_signature=sig,
                method_core=tku.method_core or {},
            )
        )
    out.sort(key=lambda t: (t.source_domain, t.paper_id))
    return out


@router.post("/design", response_model=TransferDesignOut)
def design(
    payload: TransferDesignRequest,
    session: Session = Depends(get_session),
) -> TransferDesignOut:
    """Match TKUs against a target SDL and draft an experiment-design proposal.

    use_llm=false (default) is the deterministic template mode; use_llm=true
    attempts an LLM rewrite if a provider is configured, falling back to the
    template otherwise."""
    if load_target(payload.target_id) is None:
        raise HTTPException(
            status_code=404, detail=f"Unknown transfer target '{payload.target_id}'"
        )
    design = generate_design(
        session,
        payload.target_id,
        source_domain=payload.source_domain,
        llm_client=None if payload.use_llm else _NoLLM(),
        top_k=payload.top_k,
    )
    return TransferDesignOut(
        target=design["target"],
        markdown=design["markdown"],
        mode=design["mode"],
        matches=[TransferMatchOut(**m) for m in design["matches"]],
    )


@router.post("/evolve", response_model=EvolutionaryTransferOut)
def evolve(
    payload: EvolutionaryTransferRequest,
    session: Session = Depends(get_session),
) -> EvolutionaryTransferOut:
    """Evolve cross-domain TKU combinations into candidate transfer hypotheses."""
    if load_target(payload.target_id) is None:
        raise HTTPException(
            status_code=404, detail=f"Unknown transfer target '{payload.target_id}'"
        )
    report = run_evolutionary_transfer_search(
        session,
        EvolutionConfig(
            target_id=payload.target_id,
            source_domain=payload.source_domain,
            source_pool=payload.source_pool,
            population_size=payload.population_size,
            generations=payload.generations,
            genome_size=payload.genome_size,
            mutation_rate=payload.mutation_rate,
            seed=payload.seed,
            include_knowledge_json=payload.include_knowledge_json,
        ),
    )
    return EvolutionaryTransferOut(**report)


class _NoLLM:
    """Forces template mode by short-circuiting provider resolution."""

    def __call__(self, messages):
        raise RuntimeError("LLM disabled")
