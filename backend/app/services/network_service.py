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
    edges = [
        {
            "source": src,
            "target": dst,
            "weight": int(data.get("weight", 1)),
            "papers": list(data.get("papers", [])),
        }
        for src, dst, data in g.edges(data=True)
    ]
    return {"nodes": nodes, "edges": edges}
