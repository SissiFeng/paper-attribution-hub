"""Orchestrate the providers into a single MultiGraphPayload.

Pipeline:
    1. Run each selected NodeProvider, dedup nodes by id.
    2. For each selected EdgeProvider that has BOTH endpoint node-types
       active, run it and collect edges.
    3. Apply min_edge_weight filter.
    4. If `center_id` is set, restrict to a NetworkX ego_graph of radius
       `hop_limit` around that node.
    5. Drop orphan nodes (no remaining edge) when ego mode is on, since
       the user asked for a focused view.
    6. Run the selected GroupProvider to assign group ids.
    7. Materialize GraphGroup objects with a stable color palette.
"""
from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from app.services.multi_graph.providers import (
    EDGE_PROVIDERS,
    GROUP_PROVIDERS,
    NODE_PROVIDERS,
    _filtered_papers,
    available_edge_types,
    available_group_keys,
    available_node_types,
)
from app.services.multi_graph.types import (
    GraphEdge,
    GraphGroup,
    GraphNode,
    MultiGraphFilter,
    MultiGraphPayload,
)


_GROUP_COLORS = [
    "#7aa2f7", "#34d399", "#fbbf24", "#f97316",
    "#a78bfa", "#f472b6", "#22d3ee", "#facc15",
    "#94a3b8", "#fb7185",
]


def _color_for_group(group_id: str) -> str:
    """Stable hash-based color for a group id so the same group keeps the
    same color across requests."""
    h = hashlib.sha1(group_id.encode("utf-8")).digest()
    idx = h[0] % len(_GROUP_COLORS)
    return _GROUP_COLORS[idx]


def _materialize_nodes(
    session: Session, filt: MultiGraphFilter
) -> dict[str, GraphNode]:
    nodes: dict[str, GraphNode] = {}
    for node_type in filt.node_types:
        provider = NODE_PROVIDERS.get(node_type)
        if provider is None:
            continue
        for node in provider.nodes(session, filt):
            nodes[node.id] = node
    return nodes


def _materialize_edges(
    session: Session,
    filt: MultiGraphFilter,
    active_node_ids: set[str],
) -> list[GraphEdge]:
    edges: list[GraphEdge] = []
    active_types = set(filt.node_types)
    for edge_type in filt.edge_types:
        provider = EDGE_PROVIDERS.get(edge_type)
        if provider is None:
            continue
        # Both endpoint types must be active.
        if any(t not in active_types for t in provider.requires_node_types):
            continue
        for e in provider.edges(session, filt, active_node_ids):
            if e.weight >= filt.min_edge_weight:
                edges.append(e)
    return edges


def _ego_subgraph(
    nodes: dict[str, GraphNode],
    edges: list[GraphEdge],
    center_id: str,
    hop_limit: int,
) -> tuple[dict[str, GraphNode], list[GraphEdge]]:
    import networkx as nx

    if center_id not in nodes:
        # Center isn't in the materialized set — return empty result.
        return {}, []
    g = nx.Graph()
    for nid in nodes:
        g.add_node(nid)
    for e in edges:
        if e.source in g and e.target in g:
            g.add_edge(e.source, e.target)
    ego = nx.ego_graph(g, center_id, radius=max(1, hop_limit))
    keep = set(ego.nodes())
    filtered_nodes = {nid: n for nid, n in nodes.items() if nid in keep}
    filtered_edges = [e for e in edges if e.source in keep and e.target in keep]
    return filtered_nodes, filtered_edges


def _materialize_groups(
    nodes: list[GraphNode],
    edges: list[GraphEdge],
    group_by: str,
) -> tuple[dict[str, str], list[GraphGroup]]:
    provider = GROUP_PROVIDERS.get(group_by) or GROUP_PROVIDERS["none"]
    assignment = provider.assign(nodes, edges)
    if not assignment:
        return {}, []

    counts: dict[str, int] = {}
    labels: dict[str, str] = {}
    for node_id, group_id in assignment.items():
        counts[group_id] = counts.get(group_id, 0) + 1
        if group_id not in labels:
            # Derive a friendly label from the group id.
            labels[group_id] = _friendly_label(group_id, node_id, nodes)

    groups = [
        GraphGroup(
            id=gid,
            label=labels.get(gid, gid),
            color=_color_for_group(gid),
            node_count=counts[gid],
        )
        for gid in counts
    ]
    return assignment, groups


def _friendly_label(group_id: str, sample_node_id: str, nodes: list[GraphNode]) -> str:
    # Many group ids are already friendly (country:Canada, era:2022-2023).
    # For institution: prefer the institution node's label.
    if group_id.startswith("institution:"):
        for n in nodes:
            if n.id == group_id:
                return n.label
        return group_id.split(":", 1)[1]
    if group_id.startswith("topic:"):
        for n in nodes:
            if n.id == group_id:
                return n.label
        return group_id.split(":", 1)[1]
    if group_id.startswith("country:"):
        return group_id.split(":", 1)[1]
    if group_id.startswith("era:"):
        return group_id.split(":", 1)[1]
    if group_id.startswith("label:"):
        return group_id.split(":", 1)[1].replace("_", " ")
    if group_id.startswith("community:"):
        return f"Community {group_id.split(':', 1)[1]}"
    return group_id


def build_multi_graph(
    session: Session, filt: MultiGraphFilter
) -> MultiGraphPayload:
    # Pre-fetch papers once; providers reuse this instead of re-querying.
    _filtered_papers(session, filt)
    nodes_map = _materialize_nodes(session, filt)
    edges = _materialize_edges(session, filt, set(nodes_map.keys()))

    if filt.center_id:
        nodes_map, edges = _ego_subgraph(
            nodes_map, edges, filt.center_id, filt.hop_limit
        )

    nodes_list = list(nodes_map.values())
    assignment, groups = _materialize_groups(nodes_list, edges, filt.group_by)
    for n in nodes_list:
        n.group = assignment.get(n.id)

    return MultiGraphPayload(
        nodes=nodes_list,
        edges=edges,
        groups=groups,
        available_node_types=available_node_types(),
        available_edge_types=available_edge_types(),
        available_group_keys=available_group_keys(),
    )
