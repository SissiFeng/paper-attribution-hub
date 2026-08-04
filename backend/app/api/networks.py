from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import NetworkOut
from app.services.filter_spec import (
    PaperFilter,
    build_filter_audit,
    paper_filter_query,
)
from app.services.graph_service import excess_centrality_mode
from app.services.network_service import build_coauthor_graph, graph_to_payload
from app.services.node_importance_service import (
    AUTHOR_DIMENSIONS,
    AUTHOR_DIMENSION_DEFINITIONS,
    AUTHOR_IMPORTANCE_FORMULA,
    author_profile_weights,
)

router = APIRouter(prefix="/network", tags=["network"])


@router.get("/coauthors", response_model=NetworkOut)
def coauthor_network(
    only_relevant: bool = Query(default=True),  # default True: AC-relevant papers only
    top_n_authors: int = Query(default=80, ge=10, le=300),
    min_papers: int = Query(default=1, ge=1, le=1000),
    node_search: str | None = Query(default=None, max_length=200),
    node_institution_ids: list[str] = Query(default_factory=list),
    importance_profile: Literal[
        "ac_attribution",
        "bridge_builders",
        "institution_hubs",
        "emerging_connectors",
        "topic_diffusion",
    ] = Query(default="bridge_builders"),
    importance_weights: str | None = Query(
        default=None,
        description="Optional comma-separated weights, e.g. ac_proximity:0.5,recency:0.2",
    ),
    filt: PaperFilter = Depends(paper_filter_query),
    session: Session = Depends(get_session),
) -> NetworkOut:
    effective_filt = (
        filt.model_copy(
            update={"labels": ["CORE_RELEVANT", "RELATED_RELEVANT"]}
        )
        if only_relevant
        else filt
    )
    parsed_weights = _parse_importance_weights(importance_weights)
    resolved_profile, effective_weights = author_profile_weights(
        importance_profile,
        parsed_weights,
    )
    g = build_coauthor_graph(session, filt=effective_filt)
    scoring_node_count = g.number_of_nodes()
    scoring_edge_count = g.number_of_edges()
    scoring_paper_count = int(g.graph.get("filtered_paper_count", 0))
    centrality_mode = excess_centrality_mode(g)
    recency_as_of_year = datetime.now(UTC).year
    # Structural scores must be computed over the complete paper-filtered
    # network. The controls below are presentation projections only; applying
    # them before PageRank/centrality would change an author's score merely by
    # searching for a name or changing top_n.
    payload = graph_to_payload(
        g,
        importance_profile=resolved_profile,
        importance_weights=effective_weights,
        recency_as_of_year=recency_as_of_year,
    )
    allowed_institutions = set(node_institution_ids)
    needle = (node_search or "").strip().casefold()
    payload = _project_payload(
        payload,
        limit=top_n_authors,
        min_papers=min_papers,
        node_search=needle,
        allowed_institutions=allowed_institutions,
    )
    payload["audit"] = build_filter_audit(
        session,
        effective_filt,
        algorithm="coauthor_collaboration_network.v3",
        metric_definitions={
            "node_paper_count": (
                "Distinct papers authored by the person inside the exact paper "
                "filter; this is the evidence count used by graph metrics."
            ),
            "node_corpus_paper_count": (
                "Distinct papers by the person across all papers ingested into "
                "PAS; display context only, not a lifetime publication claim."
            ),
            "edge_weight": "Distinct filtered papers coauthored by the two people.",
            "normalized_edge_weight": (
                "edge_weight / min(filtered paper count of the two authors)."
            ),
            "importance_score": AUTHOR_IMPORTANCE_FORMULA,
            "importance_rank": (
                "Deterministic rank in the complete filtered network by "
                "importance_score descending, filtered paper count descending, "
                "then author id ascending."
            ),
            "citation_affinity_scope": (
                "Stored resolved AC-core citation presence, not citation impact, "
                "raw citation count, field-weighted impact, or immediacy index. "
                "citation_reference_coverage reports the lower-bound evidence "
                "coverage; no stored reference row is not proof of no citation."
            ),
            "citation_reference_coverage": (
                "Fraction of the author's filtered papers having at least one "
                "stored parsed-reference row."
            ),
            **AUTHOR_DIMENSION_DEFINITIONS,
        },
        projection={
            "only_relevant_label_override": only_relevant,
            "top_n_authors": top_n_authors,
            "min_papers": min_papers,
            "node_search": (node_search or "").strip() or None,
            "node_institution_ids": sorted(set(node_institution_ids)),
            "importance_profile": resolved_profile,
            "importance_weights": effective_weights,
            "score_formula": AUTHOR_IMPORTANCE_FORMULA,
            "score_universe_node_count": scoring_node_count,
            "score_universe_edge_count": scoring_edge_count,
            "score_universe_paper_count": scoring_paper_count,
            "returned_node_count": len(payload["nodes"]),
            "returned_edge_count": len(payload["edges"]),
            "projection_applied_after_scoring": True,
            "excess_centrality_mode": centrality_mode,
            "recency_as_of_year": recency_as_of_year,
        },
    )
    return NetworkOut(**payload)


def _parse_importance_weights(raw: str | None) -> dict[str, float] | None:
    if not raw:
        return None
    out: dict[str, float] = {}
    for part in raw.split(","):
        if ":" not in part:
            raise HTTPException(
                status_code=422,
                detail="Each importance weight must use dimension:value format.",
            )
        key, value = part.split(":", 1)
        key = key.strip()
        if key not in AUTHOR_DIMENSIONS:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown importance dimension: {key or '<empty>'}.",
            )
        if key in out:
            raise HTTPException(
                status_code=422,
                detail=f"Duplicate importance dimension: {key}.",
            )
        try:
            parsed = float(value.strip())
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Importance weight for {key} must be numeric.",
            ) from None
        if not math.isfinite(parsed) or parsed < 0:
            raise HTTPException(
                status_code=422,
                detail=f"Importance weight for {key} must be finite and non-negative.",
            )
        out[key] = parsed
    if not out or sum(out.values()) <= 0:
        raise HTTPException(
            status_code=422,
            detail="At least one importance weight must be greater than zero.",
        )
    return out


def _project_payload(
    payload: dict,
    *,
    limit: int,
    min_papers: int,
    node_search: str,
    allowed_institutions: set[str],
) -> dict:
    eligible = [
        node
        for node in payload["nodes"]
        if int(node.get("paper_count", 0)) >= min_papers
        and (
            not allowed_institutions
            or node.get("institution_id") in allowed_institutions
        )
        and (
            not node_search
            or node_search in str(node.get("label", "")).casefold()
            or node_search in str(node.get("institution", "")).casefold()
        )
    ]
    nodes = sorted(
        eligible,
        key=lambda n: (
            -float(n.get("importance_score", n.get("ppr_score", 0.0))),
            -int(n.get("paper_count", 0)),
            str(n.get("id", "")),
        ),
    )[:limit]
    keep = {n["id"] for n in nodes}
    return {
        "nodes": nodes,
        "edges": [
            e
            for e in payload["edges"]
            if e["source"] in keep and e["target"] in keep
        ],
        "audit": payload.get("audit", {}),
    }
