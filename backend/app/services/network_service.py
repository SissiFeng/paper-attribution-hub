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
from app.services.node_importance_service import (
    author_metrics_from_graph,
    compute_author_importance,
    recency_from_years,
)
from app.services.filter_spec import PaperFilter


def build_coauthor_graph(
    session: Session,
    only_relevant: bool = False,
    *,
    filt: PaperFilter | None = None,
) -> nx.Graph:
    return _build_coauthor_graph(
        session,
        only_relevant=only_relevant,
        filt=filt,
    )


def graph_to_payload(
    g: nx.Graph,
    *,
    importance_profile: str = "bridge_builders",
    importance_weights: dict[str, float] | None = None,
    recency_as_of_year: int | None = None,
) -> dict:
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
    relationship_strength = _relationship_strength_by_node(g, ac_members)

    nodes = []
    for node_id, data in g.nodes(data=True):
        diversity = _cross_sdl_diversity(data)
        filtered_paper_count = int(data.get("paper_count", 0))
        reference_evidence_paper_count = len(
            set(data.get("reference_evidence_papers", set()))
        )
        ac_core_citing_paper_count = len(
            set(data.get("ac_core_citing_papers", set()))
        )
        citation_affinity = (
            ac_core_citing_paper_count / filtered_paper_count
            if filtered_paper_count > 0
            else 0.0
        )
        citation_reference_coverage = (
            reference_evidence_paper_count / filtered_paper_count
            if filtered_paper_count > 0
            else 0.0
        )
        active_years = sorted(
            int(year) for year in set(data.get("active_years", set()))
        )
        importance = compute_author_importance(
            metrics=author_metrics_from_graph(
                ppr_score=ppr.get(node_id, 0.0),
                c_norm=c_norm.get(node_id, 1.0),
                cross_sdl_diversity=diversity,
                relationship_strength=relationship_strength.get(node_id, 0.0),
                citation_affinity=citation_affinity,
                recency=recency_from_years(
                    active_years,
                    now_year=recency_as_of_year,
                ),
            ),
            profile=importance_profile,
            weights_override=importance_weights,
        )
        nodes.append(
            {
                "id": node_id,
                "label": data.get("label", node_id),
                "is_ac_member": bool(data.get("is_ac_member", False)),
                "institution": data.get("institution"),
                "institution_id": data.get("institution_id"),
                "paper_count": filtered_paper_count,
                "corpus_paper_count": int(
                    data.get("corpus_paper_count", filtered_paper_count)
                ),
                "ac_core_citing_paper_count": ac_core_citing_paper_count,
                "citation_affinity": round(citation_affinity, 4),
                "reference_evidence_paper_count": reference_evidence_paper_count,
                "citation_reference_coverage": round(
                    citation_reference_coverage,
                    4,
                ),
                "active_years": active_years,
                "ppr_score": round(ppr.get(node_id, 0.0), 4),
                "c_norm": round(c_norm.get(node_id, 1.0), 4),
                "cross_sdl_diversity": round(diversity, 4),
                "bridge_score": round(
                    min(
                        1.0,
                        ppr.get(node_id, 0.0)
                        * max(c_norm.get(node_id, 1.0), 0.0)
                        * diversity,
                    ),
                    4,
                ),
                "importance_score": importance.score,
                "importance_profile": importance.profile,
                "importance_components": importance.components,
                "importance_radar_axes": importance.radar_axes,
                "importance_explanation": importance.explanation,
                "importance_weights": importance.weights,
            }
        )

    ranked_nodes = sorted(
        nodes,
        key=lambda node: (
            -float(node.get("importance_score", 0.0)),
            -int(node.get("paper_count", 0)),
            str(node.get("id", "")),
        ),
    )
    for rank, node in enumerate(ranked_nodes, start=1):
        node["importance_rank"] = rank

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


def _relationship_strength_by_node(g: nx.Graph, ac_members: set[str]) -> dict[str, float]:
    out: dict[str, float] = {node_id: 0.0 for node_id in g.nodes()}
    for src, dst, data in g.edges(data=True):
        strength = float(data.get("normalized_weight", 0.0))
        if src in ac_members or dst in ac_members:
            out[src] = max(out.get(src, 0.0), strength)
            out[dst] = max(out.get(dst, 0.0), strength)
        else:
            out[src] = max(out.get(src, 0.0), strength * 0.5)
            out[dst] = max(out.get(dst, 0.0), strength * 0.5)
    return out


def _cross_sdl_diversity(data: dict) -> float:
    context_count = len(data.get("sdl_contexts", set())) + len(
        data.get("institution_contexts", set())
    )
    if context_count <= 0:
        return 0.0
    import math

    return min(1.0, math.log1p(context_count) / math.log1p(5))
