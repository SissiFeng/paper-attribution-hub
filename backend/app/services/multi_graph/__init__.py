"""Configurable multi-graph explorer (v0.7).

Three orthogonal axes the user can mix:

    node types    {author, institution, paper, topic, method, funder, ac_core}
    edge types    {authored, affiliated_with, coauthored, cites, cites_ac_core,
                   belongs_to_topic, uses_method, funded_by,
                   institution_collaboration, topic_cooccurrence, similarity}
    group rule    {by_institution, by_topic, by_country, by_year_bucket,
                   by_classification_label, by_community, none}

The architecture is provider-based: each axis is a list of plug-in classes
(`NodeProvider`, `EdgeProvider`, `GroupProvider`). Adding a new entity type
or new edge semantic = drop in another provider, ~50 lines.
"""

from app.services.multi_graph.types import (
    GraphEdge,
    GraphGroup,
    GraphNode,
    MultiGraphFilter,
    MultiGraphPayload,
)
from app.services.multi_graph.providers import (
    EdgeProvider,
    GroupProvider,
    NodeProvider,
    available_edge_types,
    available_group_keys,
    available_node_types,
)
from app.services.multi_graph.service import build_multi_graph

__all__ = [
    "GraphEdge",
    "GraphGroup",
    "GraphNode",
    "MultiGraphFilter",
    "MultiGraphPayload",
    "NodeProvider",
    "EdgeProvider",
    "GroupProvider",
    "available_node_types",
    "available_edge_types",
    "available_group_keys",
    "build_multi_graph",
]
