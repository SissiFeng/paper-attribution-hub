"""Provider abstract base classes + concrete implementations.

Each NodeProvider yields a list of GraphNode for entities of one type.
Each EdgeProvider yields GraphEdges between active nodes — it receives the
materialized node set and is responsible for not emitting dangling edges.
Each GroupProvider assigns a group key to every node.

All providers are stateless. They take a SQLAlchemy session + the active
MultiGraphFilter and return lists.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AcCorePaper,
    Author,
    Institution,
    Paper,
    PaperAuthor,
    PaperClassification,
    PaperProposition,
    PaperReference,
    Topic,
)
from app.services.filter_spec import apply_filter
from app.services.multi_graph.types import (
    GraphEdge,
    GraphNode,
    MultiGraphFilter,
)


# ---------------------------------------------------------------------------
# ABCs
# ---------------------------------------------------------------------------


class NodeProvider(ABC):
    type: str

    @abstractmethod
    def nodes(
        self, session: Session, filt: MultiGraphFilter
    ) -> Iterable[GraphNode]: ...


class EdgeProvider(ABC):
    type: str
    requires_node_types: tuple[str, ...] = ()  # both endpoint types must be active

    @abstractmethod
    def edges(
        self,
        session: Session,
        filt: MultiGraphFilter,
        active_node_ids: set[str],
    ) -> Iterable[GraphEdge]: ...


class GroupProvider(ABC):
    key: str

    @abstractmethod
    def assign(
        self,
        nodes: list[GraphNode],
        edges: list[GraphEdge],
    ) -> dict[str, str]:
        """Return node_id -> group_id mapping. Nodes without a group stay None."""


# ---------------------------------------------------------------------------
# Helpers used by multiple providers
# ---------------------------------------------------------------------------


def _filtered_papers(session: Session, filt: MultiGraphFilter) -> list[Paper]:
    return list(session.execute(apply_filter(select(Paper), filt.paper_filter)).scalars())


def _paper_id_set(session: Session, filt: MultiGraphFilter) -> set[str]:
    return {p.id for p in _filtered_papers(session, filt)}


def _author_ids_from_papers(papers: list[Paper]) -> set[str]:
    return {pa.author_id for p in papers for pa in p.authors}


def _institution_ids_from_papers(papers: list[Paper]) -> set[str]:
    out: set[str] = set()
    for p in papers:
        for pa in p.authors:
            inst = pa.author.institution
            if inst is not None:
                out.add(inst.id)
    return out


# ---------------------------------------------------------------------------
# Node providers
# ---------------------------------------------------------------------------


class AuthorNodes(NodeProvider):
    type = "author"

    def nodes(self, session, filt):
        papers = _filtered_papers(session, filt)
        ids = _author_ids_from_papers(papers)
        author_paper_count: dict[str, int] = defaultdict(int)
        for p in papers:
            for pa in p.authors:
                author_paper_count[pa.author_id] += 1
        for a in session.execute(select(Author).where(Author.id.in_(ids))).scalars():
            yield GraphNode(
                id=f"author:{a.id}",
                type=self.type,
                label=a.canonical_name,
                metadata={
                    "is_ac_member": bool(a.is_ac_member),
                    "orcid": a.orcid,
                    "institution": a.institution.canonical_name if a.institution else None,
                    "institution_id": a.institution_id,
                    "paper_count": author_paper_count[a.id],
                },
            )


class InstitutionNodes(NodeProvider):
    type = "institution"

    def nodes(self, session, filt):
        papers = _filtered_papers(session, filt)
        ids = _institution_ids_from_papers(papers)
        paper_count: dict[str, int] = defaultdict(int)
        for p in papers:
            seen: set[str] = set()
            for pa in p.authors:
                inst = pa.author.institution
                if inst is not None and inst.id not in seen:
                    seen.add(inst.id)
                    paper_count[inst.id] += 1
        for inst in session.execute(select(Institution).where(Institution.id.in_(ids))).scalars():
            yield GraphNode(
                id=f"institution:{inst.id}",
                type=self.type,
                label=inst.canonical_name,
                metadata={
                    "is_partner": bool(inst.is_partner),
                    "country": inst.country,
                    "city": inst.city,
                    "paper_count": paper_count[inst.id],
                },
            )


class PaperNodes(NodeProvider):
    type = "paper"

    def nodes(self, session, filt):
        for p in _filtered_papers(session, filt):
            cls = p.classification
            yield GraphNode(
                id=f"paper:{p.id}",
                type=self.type,
                label=p.title,
                metadata={
                    "year": p.year,
                    "venue": p.venue,
                    "doi": p.doi,
                    "label_class": cls.label if cls else None,
                    "confidence": cls.confidence if cls else None,
                    "provenance": getattr(p, "provenance", "csv"),
                },
            )


class TopicNodes(NodeProvider):
    type = "topic"

    def nodes(self, session, filt):
        # Only emit topics that actually attach to a filtered paper.
        papers = _filtered_papers(session, filt)
        topic_ids: dict[str, str] = {}  # topic_id -> display name
        topic_paper_count: dict[str, int] = defaultdict(int)
        for p in papers:
            if p.classification is None:
                continue
            for tm in p.classification.matched_topics or []:
                tid = tm.get("topic_id")
                if not tid:
                    continue
                if (tm.get("score") or 0) < 0.3:
                    continue
                topic_ids[tid] = tm.get("name") or tid
                topic_paper_count[tid] += 1
        for tid, name in topic_ids.items():
            topic_row = session.get(Topic, tid)
            yield GraphNode(
                id=f"topic:{tid}",
                type=self.type,
                label=name,
                metadata={
                    "is_core": bool(topic_row.is_core) if topic_row else None,
                    "paper_count": topic_paper_count[tid],
                },
            )


class MethodNodes(NodeProvider):
    """One node per distinct `uses_method` proposition object_key (e.g. one
    node per method like 'Bayesian optimization'). Methods aggregate evidence
    across all papers that use them."""

    type = "method"

    def nodes(self, session, filt):
        paper_ids = _paper_id_set(session, filt)
        if not paper_ids:
            return
        seen: dict[str, str] = {}
        method_paper_count: dict[str, int] = defaultdict(int)
        for prop in session.execute(
            select(PaperProposition).where(
                PaperProposition.predicate == "uses_method",
                PaperProposition.paper_id.in_(paper_ids),
            )
        ).scalars():
            key = prop.object_key or prop.object_value
            if not key:
                continue
            seen[key] = prop.object_value
            method_paper_count[key] += 1
        for key, label in seen.items():
            yield GraphNode(
                id=f"method:{key}",
                type=self.type,
                label=label,
                metadata={"paper_count": method_paper_count[key]},
            )


class FunderNodes(NodeProvider):
    """One node per funder mentioned in any `funded_by` proposition."""

    type = "funder"

    def nodes(self, session, filt):
        paper_ids = _paper_id_set(session, filt)
        if not paper_ids:
            return
        seen: dict[str, str] = {}
        funded_count: dict[str, int] = defaultdict(int)
        for prop in session.execute(
            select(PaperProposition).where(
                PaperProposition.predicate == "funded_by",
                PaperProposition.paper_id.in_(paper_ids),
            )
        ).scalars():
            key = prop.object_key or prop.object_value
            if not key:
                continue
            seen[key] = prop.object_value
            funded_count[key] += 1
        for key, label in seen.items():
            yield GraphNode(
                id=f"funder:{key}",
                type=self.type,
                label=label,
                metadata={"paper_count": funded_count[key]},
            )


class AcCoreNodes(NodeProvider):
    type = "ac_core"

    def nodes(self, session, filt):
        for c in session.execute(select(AcCorePaper)).scalars():
            yield GraphNode(
                id=f"ac_core:{c.id}",
                type=self.type,
                label=c.title,
                metadata={
                    "year": c.year,
                    "doi": c.doi,
                    "why_core": c.why_core,
                },
            )


NODE_PROVIDERS: dict[str, NodeProvider] = {
    p.type: p
    for p in (
        AuthorNodes(),
        InstitutionNodes(),
        PaperNodes(),
        TopicNodes(),
        MethodNodes(),
        FunderNodes(),
        AcCoreNodes(),
    )
}


def available_node_types() -> list[str]:
    return list(NODE_PROVIDERS.keys())


# ---------------------------------------------------------------------------
# Edge providers
# ---------------------------------------------------------------------------


class AuthoredEdges(EdgeProvider):
    type = "authored"
    requires_node_types = ("author", "paper")

    def edges(self, session, filt, active_node_ids):
        papers = _filtered_papers(session, filt)
        for p in papers:
            paper_node = f"paper:{p.id}"
            if paper_node not in active_node_ids:
                continue
            for pa in p.authors:
                author_node = f"author:{pa.author_id}"
                if author_node in active_node_ids:
                    yield GraphEdge(
                        source=author_node, target=paper_node, type=self.type, weight=1.0
                    )


class AffiliatedWithEdges(EdgeProvider):
    type = "affiliated_with"
    requires_node_types = ("author", "institution")

    def edges(self, session, filt, active_node_ids):
        seen: set[tuple[str, str]] = set()
        author_ids = {
            n.split(":", 1)[1] for n in active_node_ids if n.startswith("author:")
        }
        if not author_ids:
            return
        for a in session.execute(select(Author).where(Author.id.in_(author_ids))).scalars():
            if a.institution is None:
                continue
            source = f"author:{a.id}"
            target = f"institution:{a.institution.id}"
            if target not in active_node_ids:
                continue
            key = (source, target)
            if key in seen:
                continue
            seen.add(key)
            yield GraphEdge(source=source, target=target, type=self.type, weight=1.0)


class CoauthoredEdges(EdgeProvider):
    type = "coauthored"
    requires_node_types = ("author",)

    def edges(self, session, filt, active_node_ids):
        papers = _filtered_papers(session, filt)
        weights: dict[tuple[str, str], int] = defaultdict(int)
        shared: dict[tuple[str, str], list[str]] = defaultdict(list)
        for p in papers:
            ids = sorted(
                f"author:{pa.author_id}"
                for pa in p.authors
                if f"author:{pa.author_id}" in active_node_ids
            )
            for i, a in enumerate(ids):
                for b in ids[i + 1 :]:
                    key = (a, b)
                    weights[key] += 1
                    shared[key].append(p.id)
        for (a, b), w in weights.items():
            yield GraphEdge(
                source=a, target=b, type=self.type, weight=float(w),
                metadata={"papers": shared[(a, b)]},
            )


class InstitutionCollabEdges(EdgeProvider):
    type = "institution_collaboration"
    requires_node_types = ("institution",)

    def edges(self, session, filt, active_node_ids):
        papers = _filtered_papers(session, filt)
        weights: dict[tuple[str, str], int] = defaultdict(int)
        for p in papers:
            inst_ids = sorted({
                f"institution:{pa.author.institution.id}"
                for pa in p.authors
                if pa.author.institution is not None
                and f"institution:{pa.author.institution.id}" in active_node_ids
            })
            for i, a in enumerate(inst_ids):
                for b in inst_ids[i + 1 :]:
                    weights[(a, b)] += 1
        for (a, b), w in weights.items():
            yield GraphEdge(source=a, target=b, type=self.type, weight=float(w))


class CitesEdges(EdgeProvider):
    type = "cites"
    requires_node_types = ("paper",)

    def edges(self, session, filt, active_node_ids):
        for ref in session.execute(
            select(PaperReference).where(PaperReference.cited_paper_id.is_not(None))
        ).scalars():
            src = f"paper:{ref.citing_paper_id}"
            dst = f"paper:{ref.cited_paper_id}"
            if src in active_node_ids and dst in active_node_ids:
                yield GraphEdge(source=src, target=dst, type=self.type, weight=1.0)


class CitesAcCoreEdges(EdgeProvider):
    type = "cites_ac_core"
    requires_node_types = ("paper", "ac_core")

    def edges(self, session, filt, active_node_ids):
        for ref in session.execute(
            select(PaperReference).where(PaperReference.cited_ac_core_id.is_not(None))
        ).scalars():
            src = f"paper:{ref.citing_paper_id}"
            dst = f"ac_core:{ref.cited_ac_core_id}"
            if src in active_node_ids and dst in active_node_ids:
                yield GraphEdge(source=src, target=dst, type=self.type, weight=1.0)


class BelongsToTopicEdges(EdgeProvider):
    type = "belongs_to_topic"
    requires_node_types = ("paper", "topic")

    def edges(self, session, filt, active_node_ids):
        papers = _filtered_papers(session, filt)
        for p in papers:
            paper_node = f"paper:{p.id}"
            if paper_node not in active_node_ids or p.classification is None:
                continue
            for tm in p.classification.matched_topics or []:
                if (tm.get("score") or 0) < 0.3:
                    continue
                tid = tm.get("topic_id")
                if not tid:
                    continue
                topic_node = f"topic:{tid}"
                if topic_node not in active_node_ids:
                    continue
                yield GraphEdge(
                    source=paper_node,
                    target=topic_node,
                    type=self.type,
                    weight=float(tm.get("score") or 0.0),
                )


class UsesMethodEdges(EdgeProvider):
    type = "uses_method"
    requires_node_types = ("paper", "method")

    def edges(self, session, filt, active_node_ids):
        for prop in session.execute(
            select(PaperProposition).where(PaperProposition.predicate == "uses_method")
        ).scalars():
            src = f"paper:{prop.paper_id}"
            dst = f"method:{prop.object_key or prop.object_value}"
            if src in active_node_ids and dst in active_node_ids:
                yield GraphEdge(
                    source=src, target=dst, type=self.type, weight=float(prop.confidence)
                )


class FundedByEdges(EdgeProvider):
    type = "funded_by"
    requires_node_types = ("paper", "funder")

    def edges(self, session, filt, active_node_ids):
        for prop in session.execute(
            select(PaperProposition).where(PaperProposition.predicate == "funded_by")
        ).scalars():
            src = f"paper:{prop.paper_id}"
            dst = f"funder:{prop.object_key or prop.object_value}"
            if src in active_node_ids and dst in active_node_ids:
                yield GraphEdge(
                    source=src, target=dst, type=self.type, weight=float(prop.confidence)
                )


class TopicCooccurrenceEdges(EdgeProvider):
    """Topics that appear together on the same paper. Weight = number of
    papers they co-occur on."""

    type = "topic_cooccurrence"
    requires_node_types = ("topic",)

    def edges(self, session, filt, active_node_ids):
        papers = _filtered_papers(session, filt)
        weights: dict[tuple[str, str], int] = defaultdict(int)
        for p in papers:
            if p.classification is None:
                continue
            topic_ids = sorted({
                f"topic:{tm.get('topic_id')}"
                for tm in p.classification.matched_topics or []
                if tm.get("topic_id") and (tm.get("score") or 0) >= 0.3
            })
            topic_ids = [t for t in topic_ids if t in active_node_ids]
            for i, a in enumerate(topic_ids):
                for b in topic_ids[i + 1 :]:
                    weights[(a, b)] += 1
        for (a, b), w in weights.items():
            yield GraphEdge(source=a, target=b, type=self.type, weight=float(w))


class SimilarityEdges(EdgeProvider):
    """Paper-to-paper similarity computed on demand from chunk embeddings."""

    type = "similarity"
    requires_node_types = ("paper",)

    def edges(self, session, filt, active_node_ids):
        import numpy as np

        from app.models import PaperChunk

        paper_node_ids = [n for n in active_node_ids if n.startswith("paper:")]
        if len(paper_node_ids) < 2:
            return
        paper_ids = [n.split(":", 1)[1] for n in paper_node_ids]

        # Aggregate chunk embeddings into a paper-level mean (L2-renormalized).
        chunks_by_paper: dict[str, list[list[float]]] = defaultdict(list)
        for c in session.execute(
            select(PaperChunk).where(PaperChunk.paper_id.in_(paper_ids))
        ).scalars():
            if c.embedding:
                chunks_by_paper[c.paper_id].append(c.embedding)
        if not chunks_by_paper:
            return

        ordered_ids: list[str] = []
        vecs: list[np.ndarray] = []
        dim = None
        for pid in paper_ids:
            chunks = chunks_by_paper.get(pid)
            if not chunks:
                continue
            arr = np.asarray(chunks, dtype=np.float32)
            if dim is None:
                dim = arr.shape[1]
            elif arr.shape[1] != dim:
                # Skip papers whose embedding dimension differs (model swap mid-corpus).
                continue
            mean = arr.mean(axis=0)
            norm = float(np.linalg.norm(mean))
            if norm == 0.0:
                continue
            mean /= norm
            ordered_ids.append(pid)
            vecs.append(mean)
        if len(vecs) < 2:
            return

        matrix = np.vstack(vecs)
        sim = matrix @ matrix.T

        # For each paper, keep top-K most similar others above threshold.
        emitted: set[tuple[str, str]] = set()
        for i, pid in enumerate(ordered_ids):
            scores = sim[i].copy()
            scores[i] = -1.0
            top = np.argsort(-scores)[: filt.similarity_top_k]
            for j in top:
                score = float(scores[j])
                if score < filt.similarity_min:
                    continue
                other = ordered_ids[int(j)]
                a, b = sorted([pid, other])
                key = (a, b)
                if key in emitted:
                    continue
                emitted.add(key)
                yield GraphEdge(
                    source=f"paper:{a}",
                    target=f"paper:{b}",
                    type=self.type,
                    weight=round(score, 4),
                )


EDGE_PROVIDERS: dict[str, EdgeProvider] = {
    p.type: p
    for p in (
        AuthoredEdges(),
        AffiliatedWithEdges(),
        CoauthoredEdges(),
        InstitutionCollabEdges(),
        CitesEdges(),
        CitesAcCoreEdges(),
        BelongsToTopicEdges(),
        UsesMethodEdges(),
        FundedByEdges(),
        TopicCooccurrenceEdges(),
        SimilarityEdges(),
    )
}


def available_edge_types() -> list[str]:
    return list(EDGE_PROVIDERS.keys())


# ---------------------------------------------------------------------------
# Group providers
# ---------------------------------------------------------------------------


class ByInstitutionGroup(GroupProvider):
    key = "by_institution"

    def assign(self, nodes, edges):
        out: dict[str, str] = {}
        for n in nodes:
            if n.type == "institution":
                out[n.id] = n.id
            elif n.type == "author":
                inst_id = n.metadata.get("institution_id")
                if inst_id:
                    out[n.id] = f"institution:{inst_id}"
        # Papers inherit from the first authoring institution we saw.
        author_to_inst = {n.id: out.get(n.id) for n in nodes if n.type == "author"}
        for e in edges:
            if e.type != "authored":
                continue
            inst = author_to_inst.get(e.source)
            if inst and e.target not in out:
                out[e.target] = inst
        return out


class ByTopicGroup(GroupProvider):
    key = "by_topic"

    def assign(self, nodes, edges):
        out: dict[str, str] = {}
        for n in nodes:
            if n.type == "topic":
                out[n.id] = n.id
        # Papers inherit from highest-weight topic edge they participate in.
        best_for_paper: dict[str, tuple[float, str]] = {}
        for e in edges:
            if e.type != "belongs_to_topic":
                continue
            cur = best_for_paper.get(e.source)
            if cur is None or e.weight > cur[0]:
                best_for_paper[e.source] = (e.weight, e.target)
        for paper_id, (_, topic_id) in best_for_paper.items():
            out[paper_id] = topic_id
        return out


class ByCountryGroup(GroupProvider):
    key = "by_country"

    def assign(self, nodes, edges):
        out: dict[str, str] = {}
        country_for_inst: dict[str, str] = {}
        for n in nodes:
            if n.type == "institution":
                c = n.metadata.get("country") or "Unknown"
                country_for_inst[n.id] = c
                out[n.id] = f"country:{c}"
        for n in nodes:
            if n.type == "author":
                inst_id = n.metadata.get("institution_id")
                if inst_id:
                    c = country_for_inst.get(f"institution:{inst_id}")
                    if c:
                        out[n.id] = c
        return out


class ByYearBucketGroup(GroupProvider):
    key = "by_year_bucket"

    def assign(self, nodes, edges):
        out: dict[str, str] = {}
        for n in nodes:
            year = n.metadata.get("year")
            if year is None:
                continue
            bucket = (year // 2) * 2
            out[n.id] = f"era:{bucket}-{bucket+1}"
        return out


class ByLabelGroup(GroupProvider):
    key = "by_classification_label"

    def assign(self, nodes, edges):
        out: dict[str, str] = {}
        for n in nodes:
            label = n.metadata.get("label_class")
            if label:
                out[n.id] = f"label:{label}"
        return out


class ByCommunityGroup(GroupProvider):
    """Louvain community detection on the active subgraph."""

    key = "by_community"

    def assign(self, nodes, edges):
        if not nodes or not edges:
            return {}
        import networkx as nx

        g = nx.Graph()
        for n in nodes:
            g.add_node(n.id)
        for e in edges:
            if e.source in g and e.target in g:
                # networkx 3.x: combine repeated edges via additive weight.
                if g.has_edge(e.source, e.target):
                    g[e.source][e.target]["weight"] += e.weight
                else:
                    g.add_edge(e.source, e.target, weight=e.weight)

        try:
            communities = nx.community.louvain_communities(g, seed=42)
        except Exception:
            return {}

        out: dict[str, str] = {}
        for i, community in enumerate(communities):
            for node_id in community:
                out[node_id] = f"community:{i}"
        return out


class NoGroup(GroupProvider):
    key = "none"

    def assign(self, nodes, edges):
        return {}


GROUP_PROVIDERS: dict[str, GroupProvider] = {
    p.key: p
    for p in (
        ByInstitutionGroup(),
        ByTopicGroup(),
        ByCountryGroup(),
        ByYearBucketGroup(),
        ByLabelGroup(),
        ByCommunityGroup(),
        NoGroup(),
    )
}


def available_group_keys() -> list[str]:
    return list(GROUP_PROVIDERS.keys())
