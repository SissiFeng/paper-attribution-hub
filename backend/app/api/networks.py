from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import NetworkOut
from app.services.network_service import build_coauthor_graph, graph_to_payload

router = APIRouter(prefix="/network", tags=["network"])


@router.get("/coauthors", response_model=NetworkOut)
def coauthor_network(
    only_relevant: bool = Query(default=True),  # default True: AC-relevant papers only
    top_n_authors: int = Query(default=80, ge=10, le=300),
    importance_profile: str = Query(default="bridge_builders"),
    importance_weights: str | None = Query(
        default=None,
        description="Optional comma-separated weights, e.g. ac_proximity:0.5,recency:0.2",
    ),
    session: Session = Depends(get_session),
) -> NetworkOut:
    g = build_coauthor_graph(session, only_relevant=only_relevant)
    # Keep a larger candidate pool by paper_count for runtime, then rank that
    # pool by the selected explainable importance score. Ranking only by
    # paper_count made profile switches look identical in the UI.
    candidate_limit = min(max(top_n_authors * 4, top_n_authors), 1200)
    if g.number_of_nodes() > candidate_limit:
        top = sorted(g.nodes, key=lambda n: -g.nodes[n].get("paper_count", 0))
        ac_nodes = {n for n in g.nodes if g.nodes[n].get("is_ac_member")}
        keep = set(top[:candidate_limit]) | ac_nodes
        g.remove_nodes_from([n for n in list(g.nodes) if n not in keep])
    payload = graph_to_payload(
        g,
        importance_profile=importance_profile,
        importance_weights=_parse_importance_weights(importance_weights),
    )
    if len(payload["nodes"]) > top_n_authors:
        payload = _trim_payload_by_importance(payload, top_n_authors)
    return NetworkOut(**payload)


def _parse_importance_weights(raw: str | None) -> dict[str, float] | None:
    if not raw:
        return None
    out: dict[str, float] = {}
    for part in raw.split(","):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        key = key.strip()
        try:
            out[key] = float(value.strip())
        except ValueError:
            continue
    return out or None


def _trim_payload_by_importance(payload: dict, limit: int) -> dict:
    nodes = sorted(
        payload["nodes"],
        key=lambda n: (
            n.get("importance_score", n.get("ppr_score", 0.0)),
            n.get("paper_count", 0),
        ),
        reverse=True,
    )[:limit]
    keep = {n["id"] for n in nodes}
    return {
        "nodes": nodes,
        "edges": [
            e
            for e in payload["edges"]
            if e["source"] in keep and e["target"] in keep
        ],
    }
