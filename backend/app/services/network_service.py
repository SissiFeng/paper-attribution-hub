"""Co-author network endpoint helpers — graph construction now lives in
`graph_service`. This file only exposes the v0.1 API shape."""
from __future__ import annotations

import networkx as nx
from sqlalchemy.orm import Session

from app.services.graph_service import (
    add_normalized_weights,
    build_coauthor_graph as _build_coauthor_graph,
    evans_chen_c_norm,
    ppr_toward_ac,
)


def build_coauthor_graph(session: Session, only_relevant: bool = False) -> nx.Graph:
    return _build_coauthor_graph(session, only_relevant=only_relevant)


def graph_to_payload(g: nx.Graph) -> dict:
    ac_members: set[str] = {
        node_id
        for node_id, data in g.nodes(data=True)
        if data.get("is_ac_member")
    }
    paper_counts: dict[str, int] = {
        node_id: int(data.get("paper_count", 0))
        for node_id, data in g.nodes(data=True)
    }

    # Ensure normalized_weight edges are present, then score nodes.
    add_normalized_weights(g)
    ppr = ppr_toward_ac(g, ac_members)
    c_norm = evans_chen_c_norm(g)

    nodes = [
        {
            "id": node_id,
            "label": data.get("label", node_id),
            "is_ac_member": bool(data.get("is_ac_member", False)),
            "institution": data.get("institution"),
            "paper_count": int(data.get("paper_count", 0)),
            "ppr_score": round(ppr.get(node_id, 0.0), 4),
            "c_norm": round(c_norm.get(node_id, 1.0), 4),
            "cross_sdl_diversity": round(_cross_sdl_diversity(data), 4),
            "bridge_score": round(
                min(
                    1.0,
                    ppr.get(node_id, 0.0)
                    * max(c_norm.get(node_id, 1.0), 0.0)
                    * _cross_sdl_diversity(data),
                ),
                4,
            ),
        }
        for node_id, data in g.nodes(data=True)
    ]

    edges = []
    for src, dst, data in g.edges(data=True):
        weight = int(data.get("weight", 1))
        min_degree = min(paper_counts.get(src, 1), paper_counts.get(dst, 1))
        normalized_weight = round(weight / max(min_degree, 1), 4)
        src_ac = src in ac_members
        dst_ac = dst in ac_members
        edges.append({
            "source": src,
            "target": dst,
            "weight": weight,
            "papers": list(data.get("papers", [])),
            "normalized_weight": min(normalized_weight, 1.0),
            "involves_ac": src_ac or dst_ac,
            "is_ac_ac": src_ac and dst_ac,
        })

    return {"nodes": nodes, "edges": edges}


def _cross_sdl_diversity(data: dict) -> float:
    context_count = len(data.get("sdl_contexts", set())) + len(
        data.get("institution_contexts", set())
    )
    if context_count <= 0:
        return 0.0
    import math

    return min(1.0, math.log1p(context_count) / math.log1p(5))
