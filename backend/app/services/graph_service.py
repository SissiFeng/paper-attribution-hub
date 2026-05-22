"""Unified graph layer over papers / authors / institutions / citations.

This is the *structural* layer that feeds:
  - per-paper graph signals used by the classifier (network_score, citation_score)
  - analytics endpoints (sankey, timeline, institution network)
  - graph-RAG explanations (second-degree collaborator paths, citing AC core)

Everything here is deterministic SQL + NetworkX. RAG only re-uses these
records to display "why" panels — it never invents new edges.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AcCorePaper,
    Author,
    Institution,
    Paper,
    PaperAuthor,
    PaperReference,
)


@dataclass
class SecondDegreePath:
    """Path showing how a paper's author connects to an AC member via a third author."""

    paper_id: str
    via_author_id: str
    via_author_name: str
    ac_author_id: str
    ac_author_name: str
    shared_papers: list[str] = field(default_factory=list)
    strength: float = 0.0


@dataclass
class CitationSignal:
    cited_ac_core_id: str
    cited_ac_core_title: str
    cited_doi: str | None
    raw_text: str


@dataclass
class GraphSignals:
    """Per-paper structural signals fed into the classifier and explanation API."""

    paper_id: str
    network_score: float = 0.0
    citation_score: float = 0.0
    second_degree_paths: list[SecondDegreePath] = field(default_factory=list)
    citation_signals: list[CitationSignal] = field(default_factory=list)
    cites_corpus: list[str] = field(default_factory=list)  # other papers in our corpus

    def to_dict(self) -> dict:
        return {
            "network_score": round(self.network_score, 3),
            "citation_score": round(self.citation_score, 3),
            "second_degree_paths": [
                {
                    "via_author_id": p.via_author_id,
                    "via_author_name": p.via_author_name,
                    "ac_author_id": p.ac_author_id,
                    "ac_author_name": p.ac_author_name,
                    "shared_papers": p.shared_papers,
                    "strength": round(p.strength, 3),
                }
                for p in self.second_degree_paths
            ],
            "citation_signals": [
                {
                    "cited_ac_core_id": s.cited_ac_core_id,
                    "cited_ac_core_title": s.cited_ac_core_title,
                    "cited_doi": s.cited_doi,
                }
                for s in self.citation_signals
            ],
            "cites_corpus": self.cites_corpus,
        }


def build_coauthor_graph(session: Session, only_relevant: bool = False) -> nx.Graph:
    """Author-level co-authorship graph (used by v0.1 endpoint + graph signals)."""
    g = nx.Graph()
    papers: Iterable[Paper] = session.execute(select(Paper)).scalars()

    for paper in papers:
        if only_relevant:
            cls = paper.classification
            if not cls or cls.label not in {"CORE_RELEVANT", "RELATED_RELEVANT"}:
                continue

        author_ids: list[str] = []
        for pa in paper.authors:
            a: Author = pa.author
            if a.id not in g:
                g.add_node(
                    a.id,
                    label=a.canonical_name,
                    is_ac_member=bool(a.is_ac_member),
                    institution=a.institution.canonical_name if a.institution else None,
                    paper_count=0,
                )
            g.nodes[a.id]["paper_count"] += 1
            author_ids.append(a.id)

        for i, src in enumerate(author_ids):
            for dst in author_ids[i + 1 :]:
                if g.has_edge(src, dst):
                    g[src][dst]["weight"] += 1
                    g[src][dst]["papers"].append(paper.id)
                else:
                    g.add_edge(src, dst, weight=1, papers=[paper.id])
    return g


def build_institution_graph(session: Session) -> nx.Graph:
    """Institution-level collaboration graph (figure.md §recommended-MVP-set)."""
    g = nx.Graph()
    institutions_by_id = {
        inst.id: inst for inst in session.execute(select(Institution)).scalars()
    }
    papers = session.execute(select(Paper)).scalars()

    for paper in papers:
        institution_ids: list[str] = []
        for pa in paper.authors:
            inst = pa.author.institution
            if inst is None:
                continue
            if inst.id not in institution_ids:
                institution_ids.append(inst.id)
            if inst.id not in g:
                g.add_node(
                    inst.id,
                    label=inst.canonical_name,
                    is_partner=bool(inst.is_partner),
                    country=inst.country,
                    paper_count=0,
                )
            g.nodes[inst.id]["paper_count"] += 1

        for i, src in enumerate(institution_ids):
            for dst in institution_ids[i + 1 :]:
                if g.has_edge(src, dst):
                    g[src][dst]["weight"] += 1
                    g[src][dst]["papers"].append(paper.id)
                else:
                    g.add_edge(src, dst, weight=1, papers=[paper.id])
    # Add isolated institutions (so the partner-only view doesn't drop AC nodes).
    for inst_id, inst in institutions_by_id.items():
        if inst_id not in g:
            g.add_node(
                inst_id,
                label=inst.canonical_name,
                is_partner=bool(inst.is_partner),
                country=inst.country,
                paper_count=0,
            )
    return g


def build_citation_graph(session: Session) -> nx.DiGraph:
    """Directed: citing_paper → cited_paper (corpus + AC core)."""
    g = nx.DiGraph()
    papers = list(session.execute(select(Paper)).scalars())
    for paper in papers:
        g.add_node(
            paper.id,
            label=paper.title,
            kind="paper",
            year=paper.year,
        )
    for core in session.execute(select(AcCorePaper)).scalars():
        g.add_node(
            core.id, label=core.title, kind="ac_core", year=core.year, doi=core.doi
        )
    for ref in session.execute(select(PaperReference)).scalars():
        if ref.cited_paper_id and ref.cited_paper_id != ref.citing_paper_id:
            g.add_edge(ref.citing_paper_id, ref.cited_paper_id, kind="corpus")
        if ref.cited_ac_core_id:
            g.add_edge(ref.citing_paper_id, ref.cited_ac_core_id, kind="ac_core")
    return g


def _build_ac_member_set(session: Session) -> set[str]:
    return {
        a.id for a in session.execute(select(Author).where(Author.is_ac_member)).scalars()
    }


def compute_graph_signals(session: Session) -> dict[str, GraphSignals]:
    """For every paper, compute network_score + citation_score + supporting paths.

    network_score:
      1.0 if any paper author IS an AC member (also covered by author_score, but
          we keep it consistent for the analytics layer)
      0.5 * min(1.0, len(unique_second_degree_paths) / 2) when only second-degree
      0.0 otherwise

    citation_score:
      sum of 0.5 per cited AC core (capped at 1.0)
    """
    ac_member_ids = _build_ac_member_set(session)

    # Map author_id → set of papers they appear on (corpus-wide).
    author_to_papers: dict[str, set[str]] = {}
    pa_rows = session.execute(
        select(PaperAuthor.author_id, PaperAuthor.paper_id)
    ).all()
    for author_id, paper_id in pa_rows:
        author_to_papers.setdefault(author_id, set()).add(paper_id)

    # Map paper_id → list of (author_id, name).
    paper_to_authors: dict[str, list[tuple[str, str]]] = {}
    for pa in session.execute(select(PaperAuthor)).scalars():
        paper_to_authors.setdefault(pa.paper_id, []).append(
            (pa.author_id, pa.author.canonical_name)
        )

    # Build reverse index for second-degree lookup:
    # for each non-AC author, find AC members they've co-authored with on
    # ANY paper. The lookup is shared across all papers.
    coauthor_of: dict[str, set[str]] = {}  # author_id → set of co-author ids
    author_pair_papers: dict[tuple[str, str], list[str]] = {}
    for paper_id, authors in paper_to_authors.items():
        ids = [a[0] for a in authors]
        for i, a in enumerate(ids):
            for b in ids[i + 1 :]:
                coauthor_of.setdefault(a, set()).add(b)
                coauthor_of.setdefault(b, set()).add(a)
                key = tuple(sorted((a, b)))
                author_pair_papers.setdefault(key, []).append(paper_id)

    author_names = {
        a.id: a.canonical_name for a in session.execute(select(Author)).scalars()
    }

    # Citations: paper_id → list of (ac_core_id, ac_core_title, doi, raw_text)
    citations: dict[str, list[CitationSignal]] = {}
    cites_corpus: dict[str, list[str]] = {}
    ac_cores = {c.id: c for c in session.execute(select(AcCorePaper)).scalars()}
    for ref in session.execute(select(PaperReference)).scalars():
        if ref.cited_ac_core_id:
            core = ac_cores.get(ref.cited_ac_core_id)
            if core is not None:
                citations.setdefault(ref.citing_paper_id, []).append(
                    CitationSignal(
                        cited_ac_core_id=core.id,
                        cited_ac_core_title=core.title,
                        cited_doi=core.doi,
                        raw_text=ref.raw_text,
                    )
                )
        if ref.cited_paper_id and ref.cited_paper_id != ref.citing_paper_id:
            cites_corpus.setdefault(ref.citing_paper_id, []).append(ref.cited_paper_id)

    signals: dict[str, GraphSignals] = {}
    for paper in session.execute(select(Paper)).scalars():
        paths: list[SecondDegreePath] = []
        author_ids = [aid for aid, _ in paper_to_authors.get(paper.id, [])]
        paper_has_ac_author = any(aid in ac_member_ids for aid in author_ids)

        if not paper_has_ac_author:
            seen_ac_pairs: set[tuple[str, str]] = set()
            for aid in author_ids:
                # Skip if this author IS an AC member (shouldn't happen here).
                for partner in coauthor_of.get(aid, set()):
                    if partner not in ac_member_ids:
                        continue
                    key = tuple(sorted((aid, partner)))
                    pair_id = (aid, partner)
                    if pair_id in seen_ac_pairs:
                        continue
                    seen_ac_pairs.add(pair_id)
                    shared = sorted(
                        pid
                        for pid in author_pair_papers.get(key, [])
                        if pid != paper.id
                    )
                    if not shared:
                        continue
                    paths.append(
                        SecondDegreePath(
                            paper_id=paper.id,
                            via_author_id=aid,
                            via_author_name=author_names.get(aid, aid),
                            ac_author_id=partner,
                            ac_author_name=author_names.get(partner, partner),
                            shared_papers=shared,
                            strength=min(1.0, 0.5 + 0.2 * len(shared)),
                        )
                    )

        if paper_has_ac_author:
            network_score = 1.0
        elif paths:
            network_score = min(1.0, 0.5 + 0.15 * len(paths))
        else:
            network_score = 0.0

        cite_signals = citations.get(paper.id, [])
        citation_score = min(1.0, 0.5 * len(cite_signals))

        signals[paper.id] = GraphSignals(
            paper_id=paper.id,
            network_score=network_score,
            citation_score=citation_score,
            second_degree_paths=paths,
            citation_signals=cite_signals,
            cites_corpus=cites_corpus.get(paper.id, []),
        )

    return signals
