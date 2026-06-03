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
    # Cap node count: keep the top-N authors by paper_count to avoid OOM
    if g.number_of_nodes() > top_n_authors:
        top = sorted(g.nodes, key=lambda n: -g.nodes[n].get("paper_count", 0))
        keep = set(top[:top_n_authors])
        g.remove_nodes_from([n for n in list(g.nodes) if n not in keep])
    payload = graph_to_payload(
        g,
        importance_profile=importance_profile,
        importance_weights=_parse_importance_weights(importance_weights),
    )
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
