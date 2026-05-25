"""Co-author network endpoint helpers — graph construction now lives in
`graph_service`. This file only exposes the v0.1 API shape."""
from __future__ import annotations

import networkx as nx
from sqlalchemy.orm import Session

from app.services.graph_service import build_coauthor_graph as _build_coauthor_graph


def build_coauthor_graph(session: Session, only_relevant: bool = False) -> nx.Graph:
    return _build_coauthor_graph(session, only_relevant=only_relevant)


def graph_to_payload(g: nx.Graph) -> dict:
    nodes = [
        {
            "id": node_id,
            "label": data.get("label", node_id),
            "is_ac_member": bool(data.get("is_ac_member", False)),
            "institution": data.get("institution"),
            "paper_count": int(data.get("paper_count", 0)),
        }
        for node_id, data in g.nodes(data=True)
    ]

    ac_members: set[str] = {
        node_id
        for node_id, data in g.nodes(data=True)
        if data.get("is_ac_member")
    }
    paper_counts: dict[str, int] = {
        node_id: int(data.get("paper_count", 0))
        for node_id, data in g.nodes(data=True)
    }

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
