from __future__ import annotations

from dataclasses import dataclass, field

from app.services.filter_spec import PaperFilter


@dataclass
class GraphNode:
    id: str
    type: str        # "author" | "institution" | "paper" | "topic" | "method" | "funder" | "ac_core"
    label: str
    group: str | None = None    # assigned by the active GroupProvider
    metadata: dict = field(default_factory=dict)


@dataclass
class GraphEdge:
    source: str
    target: str
    type: str        # "coauthored" | "cites" | ...
    weight: float = 1.0
    metadata: dict = field(default_factory=dict)


@dataclass
class GraphGroup:
    id: str
    label: str
    color: str
    node_count: int = 0


@dataclass
class MultiGraphFilter:
    """Composite filter for the multi-graph endpoint. Extends PaperFilter
    semantics with axis-specific options."""

    paper_filter: PaperFilter = field(default_factory=PaperFilter)
    node_types: list[str] = field(
        default_factory=lambda: ["author", "institution", "paper"]
    )
    edge_types: list[str] = field(
        default_factory=lambda: ["coauthored", "affiliated_with", "cites"]
    )
    group_by: str = "by_institution"
    min_edge_weight: float = 0.3

    # Optional ego-graph mode (NetworkX-style).
    center_id: str | None = None
    hop_limit: int = 2

    # Optional similarity-edge tuning (only matters when "similarity" in edge_types).
    similarity_min: float = 0.7
    similarity_top_k: int = 5

    # Internal: populated once by build_multi_graph so providers share one DB fetch.
    _papers_cache: list | None = field(default=None, repr=False, compare=False)


@dataclass
class MultiGraphPayload:
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    groups: list[GraphGroup]
    available_node_types: list[str]
    available_edge_types: list[str]
    available_group_keys: list[str]
