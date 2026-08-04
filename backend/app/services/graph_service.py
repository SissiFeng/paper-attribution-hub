"""Unified graph layer over papers / authors / institutions / citations.

This is the *structural* layer that feeds:
  - per-paper graph signals used by the classifier (network_score, citation_score)
  - analytics endpoints (sankey, timeline, institution network)
  - graph-RAG explanations (second-degree collaborator paths, citing AC core)

Everything here is deterministic SQL + NetworkX. RAG only re-uses these
records to display "why" panels — it never invents new edges.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import networkx as nx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AcCorePaper,
    Author,
    Institution,
    Paper,
    PaperAuthor,
    PaperReference,
)
from app.services.author_matcher import preferred_author_display_name
from app.services.filter_spec import PaperFilter, apply_filter

_EXACT_C_NORM_NODE_LIMIT = 5000


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
    bridge_score: float = 0.0
    cross_sdl_diversity: float = 0.0
    second_degree_paths: list[SecondDegreePath] = field(default_factory=list)
    citation_signals: list[CitationSignal] = field(default_factory=list)
    cites_corpus: list[str] = field(default_factory=list)  # other papers in our corpus

    def to_dict(self) -> dict:
        return {
            "network_score": round(self.network_score, 3),
            "citation_score": round(self.citation_score, 3),
            "bridge_score": round(self.bridge_score, 3),
            "cross_sdl_diversity": round(self.cross_sdl_diversity, 3),
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


def build_coauthor_graph(
    session: Session,
    only_relevant: bool = False,
    *,
    filt: PaperFilter | None = None,
) -> nx.Graph:
    """Author-level co-authorship graph (used by v0.1 endpoint + graph signals).

    Uses lean SQL queries instead of loading full Paper ORM objects to stay
    within Render's 512 MB memory limit.
    """
    from collections import defaultdict
    from app.models import PaperClassification

    g = nx.Graph()

    # Query 1: paper-level data (id, sdl_tags, label, matched_topics).
    if filt is not None:
        # Isolate the shared paper filter before joining the classification row.
        # Some filter predicates use a correlated classification EXISTS; applying
        # them to a statement that also joins that table makes SQLAlchemy remove
        # every FROM clause through auto-correlation.
        filtered_ids = apply_filter(
            select(Paper.id.label("paper_id")), filt
        ).subquery()
        paper_cls_stmt = (
            select(
                Paper.id,
                Paper.year,
                Paper.sdl_tags,
                PaperClassification.label,
                PaperClassification.matched_topics,
            )
            .join(filtered_ids, filtered_ids.c.paper_id == Paper.id)
            .outerjoin(
                PaperClassification,
                PaperClassification.paper_id == Paper.id,
            )
        )
    else:
        paper_cls_stmt = (
            select(
                Paper.id,
                Paper.year,
                Paper.sdl_tags,
                PaperClassification.label,
                PaperClassification.matched_topics,
            )
            .outerjoin(
                PaperClassification,
                PaperClassification.paper_id == Paper.id,
            )
        )
    if only_relevant:
        paper_cls_stmt = paper_cls_stmt.where(
            PaperClassification.label.in_({"CORE_RELEVANT", "RELATED_RELEVANT"})
        )
    paper_data: dict[str, dict] = {}
    for pid, year, sdl_tags, label, matched_topics in session.execute(paper_cls_stmt).all():
        paper_data[pid] = {
            "year": year,
            "sdl_tags": sdl_tags or [],
            "matched_topics": matched_topics or [],
        }

    g.graph["filtered_paper_count"] = len(paper_data)

    if not paper_data:
        return g

    # Query 2: author + institution data.
    author_rows = session.execute(
        select(
            Author.id,
            Author.canonical_name,
            Author.is_ac_member,
            Author.institution_id,
            Institution.canonical_name.label("inst_name"),
        )
        .outerjoin(Institution, Institution.id == Author.institution_id)
    ).all()
    author_info: dict[str, dict] = {
        a_id: {
            "label": name,
            "is_ac_member": bool(is_ac),
            "institution": inst_name,
            "institution_id": inst_id,
        }
        for a_id, name, is_ac, inst_id, inst_name in author_rows
    }

    # Keep the analysis count distinct from the full ingested-corpus count.
    # The former follows ``filt`` and is used by every graph metric; the latter
    # is display-only context that explains why a filtered view may show fewer
    # papers than an author's complete PAS corpus record.
    corpus_paper_counts = dict(
        session.execute(
            select(
                PaperAuthor.author_id,
                func.count(func.distinct(PaperAuthor.paper_id)),
            ).group_by(PaperAuthor.author_id)
        ).all()
    )

    # Citation affinity is about resolved links to curated AC-core papers, not
    # raw citation volume. Multiple parsed reference rows from the same paper
    # intentionally count once.
    reference_rows = session.execute(
        select(
            PaperReference.citing_paper_id,
            PaperReference.cited_ac_core_id,
        ).where(PaperReference.citing_paper_id.in_(list(paper_data)))
    ).all()
    reference_evidence_papers = {paper_id for paper_id, _core_id in reference_rows}
    ac_core_citing_papers = {
        paper_id for paper_id, core_id in reference_rows if core_id is not None
    }

    # Query 3: paper-author associations (only for papers we care about).
    pa_rows = session.execute(
        select(PaperAuthor.paper_id, PaperAuthor.author_id).where(
            PaperAuthor.paper_id.in_(list(paper_data.keys()))
        )
    ).all()

    # Group by paper.
    paper_authors: dict[str, list[str]] = defaultdict(list)
    for paper_id, author_id in pa_rows:
        if author_id not in paper_authors[paper_id]:
            paper_authors[paper_id].append(author_id)

    # Build graph.
    for paper_id, author_ids in paper_authors.items():
        pdata = paper_data[paper_id]
        sdl_ctx = _sdl_contexts_from_data(pdata["sdl_tags"], pdata["matched_topics"])
        for a_id in author_ids:
            info = author_info.get(a_id)
            if info is None:
                continue
            if a_id not in g:
                g.add_node(
                    a_id,
                    label=info["label"],
                    is_ac_member=info["is_ac_member"],
                    institution=info["institution"],
                    institution_id=info["institution_id"],
                    paper_count=0,
                    corpus_paper_count=int(corpus_paper_counts.get(a_id, 0)),
                    active_years=set(),
                    sdl_contexts=set(),
                    institution_contexts=set(),
                    reference_evidence_papers=set(),
                    ac_core_citing_papers=set(),
                )
            g.nodes[a_id]["paper_count"] += 1
            if paper_id in reference_evidence_papers:
                g.nodes[a_id]["reference_evidence_papers"].add(paper_id)
            if paper_id in ac_core_citing_papers:
                g.nodes[a_id]["ac_core_citing_papers"].add(paper_id)
            if pdata["year"] is not None:
                g.nodes[a_id]["active_years"].add(int(pdata["year"]))
            g.nodes[a_id]["sdl_contexts"].update(sdl_ctx)
            if info["institution_id"]:
                g.nodes[a_id]["institution_contexts"].add(info["institution_id"])

        for i, src in enumerate(author_ids):
            if src not in g:
                continue
            for dst in author_ids[i + 1 :]:
                if dst not in g:
                    continue
                if g.has_edge(src, dst):
                    g[src][dst]["weight"] += 1
                    if paper_id not in g[src][dst]["papers"]:
                        g[src][dst]["papers"].append(paper_id)
                else:
                    g.add_edge(src, dst, weight=1, papers=[paper_id])
    return g


def _paper_sdl_contexts(paper: Paper) -> set[str]:
    contexts = set(paper.sdl_tags or [])
    if paper.classification and paper.classification.matched_topics:
        contexts.update(
            t.get("topic_id") or t.get("name")
            for t in paper.classification.matched_topics
            if t.get("topic_id") or t.get("name")
        )
    return {str(c) for c in contexts if c}


def _sdl_contexts_from_data(sdl_tags: list, matched_topics: list) -> set[str]:
    contexts = set(sdl_tags or [])
    for t in matched_topics or []:
        key = t.get("topic_id") or t.get("name")
        if key:
            contexts.add(key)
    return {str(c) for c in contexts if c}


def _normalized_diversity(count: int) -> float:
    if count <= 0:
        return 0.0
    return min(1.0, math.log1p(count) / math.log1p(5))


def build_institution_graph(session: Session) -> nx.Graph:
    """Institution-level collaboration graph (figure.md §recommended-MVP-set).

    Uses lean SQL JOINs instead of loading full Paper ORM objects to stay
    within Render's 512 MB memory limit.
    """
    from collections import defaultdict

    g = nx.Graph()
    # Seed all institutions as isolated nodes first.
    for inst in session.execute(select(Institution)).scalars():
        g.add_node(
            inst.id,
            label=inst.canonical_name,
            is_partner=bool(inst.is_partner),
            country=inst.country,
            paper_count=0,
        )

    # Lean query: one row per (paper, author) — no full Paper objects in memory.
    rows = session.execute(
        select(PaperAuthor.paper_id, Author.institution_id)
        .join(Author, Author.id == PaperAuthor.author_id)
        .where(Author.institution_id.is_not(None))
    ).all()

    paper_insts: dict[str, list[str]] = defaultdict(list)
    for paper_id, inst_id in rows:
        if inst_id not in g:
            continue
        g.nodes[inst_id]["paper_count"] += 1
        if inst_id not in paper_insts[paper_id]:
            paper_insts[paper_id].append(inst_id)

    for paper_id, inst_ids in paper_insts.items():
        for i, src in enumerate(inst_ids):
            for dst in inst_ids[i + 1 :]:
                if g.has_edge(src, dst):
                    g[src][dst]["weight"] += 1
                    g[src][dst]["papers"].append(paper_id)
                else:
                    g.add_edge(src, dst, weight=1, papers=[paper_id])
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


def add_normalized_weights(g: nx.Graph) -> None:
    """Add normalized_weight = weight / min(paper_count_u, paper_count_v) in-place."""
    for u, v, data in g.edges(data=True):
        w = int(data.get("weight", 1))
        deg_u = g.nodes[u].get("paper_count", 1)
        deg_v = g.nodes[v].get("paper_count", 1)
        data["normalized_weight"] = round(w / max(min(deg_u, deg_v), 1), 4)


def ppr_toward_ac(g: nx.Graph, ac_ids: set[str]) -> dict[str, float]:
    """
    AC-Personalized PageRank.

    Solves π = α·p + (1−α)·W^T·π where p_i = 1/|AC| if i∈AC, else 0.

    Interpretation: steady-state probability that a random walker, restarting
    toward AC members with probability (1−α), is found at node i. This models
    structural proximity to the AC-seeded coauthor network, not causal influence.

    Returns scores normalized to [0, 1] so the best-positioned AC-adjacent
    author maps to 1.0 and distant authors approach 0.
    """
    ac_nodes = [n for n in g.nodes() if n in ac_ids]
    if not ac_nodes or g.number_of_nodes() == 0:
        return {n: 0.0 for n in g.nodes()}

    personalization = {
        node: (1.0 / len(ac_nodes) if node in ac_ids else 0.0)
        for node in g.nodes()
    }
    pagerank_kwargs = {
        "alpha": 0.85,
        "personalization": personalization,
        "weight": "normalized_weight",
        "max_iter": 300,
        "tol": 1e-9,
    }
    try:
        ppr = nx.pagerank(g, **pagerank_kwargs)
    except (ImportError, ModuleNotFoundError):
        from networkx.algorithms.link_analysis.pagerank_alg import _pagerank_python

        ppr = _pagerank_python(g, **pagerank_kwargs)
    except nx.PowerIterationFailedConvergence:
        return {n: 0.0 for n in g.nodes()}

    max_val = max(ppr.values(), default=1.0)
    return {n: v / max_val for n, v in ppr.items()} if max_val > 0 else ppr


def evans_chen_c_norm(g: nx.Graph) -> dict[str, float]:
    """
    Excess centrality from Evans & Chen (2022), extended to weighted networks.

    Original result (unweighted trees):  1/c_r = −1/ln(z̄) · ln(k_r) + β
    Our extension: replace degree k_r with weighted degree k_r^(w) = Σ_j w_{rj},
    and compute harmonic centrality using 1/w as edge distance (Opsahl 2010).

    c_norm(r) = c_r / c_r^(fit) where c_r^(fit) = 1 / (β − ln(k_r^w) / ln(z̄^w))

    c_norm > 1 → node is MORE central than its weighted degree predicts
                  (bridge author, interdisciplinary connector)
    c_norm ≈ 1 → centrality fully explained by degree (Evans & Chen redundancy region)
    c_norm < 1 → structurally peripheral relative to productivity

    For large production graphs, exact harmonic centrality is intentionally
    skipped because it is all-pairs-distance work and can stall interactive
    endpoints. The bridge score still uses PPR_AC × diversity in that mode.
    """
    n = g.number_of_nodes()
    if n < 4:
        return {node: 1.0 for node in g.nodes()}
    if n > _EXACT_C_NORM_NODE_LIMIT:
        return {node: 1.0 for node in g.nodes()}

    # Evans & Chen use degree k_r = number of distinct neighbors (unweighted),
    # validated on coauthor-astro-ph with this definition.
    # z̄ = mean degree of the graph.
    degrees = {node: g.degree(node) for node in g.nodes()}
    z_bar = sum(degrees.values()) / n

    if z_bar <= 1.0:
        return {node: 1.0 for node in g.nodes()}

    ln_zbar = math.log(z_bar)

    # Harmonic centrality on the weighted distance graph.
    # Distance d(u,v) = 1/normalized_weight so stronger ties = shorter distance.
    # This is our extension of Evans & Chen to weighted networks (Opsahl 2010).
    g_dist = nx.Graph()
    g_dist.add_nodes_from(g.nodes())
    for u, v, data in g.edges(data=True):
        w = data.get("normalized_weight", 0.01)
        g_dist.add_edge(u, v, weight=1.0 / max(w, 1e-6))

    harm = nx.harmonic_centrality(g_dist, distance="weight")
    max_harm = max(harm.values(), default=1.0)
    if max_harm > 0:
        harm = {k: v / max_harm for k, v in harm.items()}

    # Calibrate β: from 1/c = −ln(k)/ln(z̄) + β → β = mean(1/c + ln(k)/ln(z̄))
    valid = [
        (degrees[node], harm[node])
        for node in g.nodes()
        if degrees[node] > 0 and harm[node] > 1e-9
    ]
    if len(valid) < 3:
        return {node: 1.0 for node in g.nodes()}

    beta = sum(1.0 / h + math.log(k) / ln_zbar for k, h in valid) / len(valid)

    c_norm: dict[str, float] = {}
    for node in g.nodes():
        k = degrees.get(node, 0)
        c_actual = harm.get(node, 0.0)
        if k <= 0 or c_actual <= 1e-9:
            c_norm[node] = 1.0
            continue
        try:
            denom = beta - math.log(k) / ln_zbar
            c_fit = 1.0 / denom if denom > 1e-9 else c_actual
            c_norm[node] = c_actual / c_fit
        except (ValueError, ZeroDivisionError):
            c_norm[node] = 1.0

    return c_norm


def excess_centrality_mode(g: nx.Graph) -> str:
    """Describe whether c_norm is computed or deliberately neutralized."""
    node_count = g.number_of_nodes()
    if node_count < 4:
        return "neutral_insufficient_nodes"
    if node_count > _EXACT_C_NORM_NODE_LIMIT:
        return "neutral_large_graph_fallback"
    mean_degree = sum(dict(g.degree()).values()) / node_count
    if mean_degree <= 1.0:
        return "neutral_sparse_graph"
    return "exact_weighted_harmonic"


def compute_graph_signals(session: Session) -> dict[str, GraphSignals]:
    """For every paper, compute network_score + citation_score + supporting paths.

    network_score (v2 — PPR + Evans & Chen):
      1.0  if any author IS an AC member (direct attribution)
      otherwise: max over paper authors of
          PPR_AC(author) × (1 + λ · max(0, c_norm(author) − 1))
      where
          PPR_AC  = AC-Personalized PageRank (α=0.85, weighted by normalized_weight)
                    models structural proximity to the AC-seeded coauthor network
          c_norm  = Evans & Chen (2022) excess centrality extended to weighted graphs:
                    c_norm = c_actual / c_fit, c_fit = 1/(β − ln(k_w)/ln(z̄_w))
                    captures authors who are MORE central than their degree predicts
          λ = 0.25 (bridge-author bonus weight)

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
    seen_paper_authors: set[tuple[str, str]] = set()
    for pa in session.execute(select(PaperAuthor)).scalars():
        key = (pa.paper_id, pa.author_id)
        if key in seen_paper_authors:
            continue
        seen_paper_authors.add(key)
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
                papers = author_pair_papers.setdefault(key, [])
                if paper_id not in papers:
                    papers.append(paper_id)

    author_names = {}
    for author in session.execute(select(Author)).scalars():
        author_names[author.id] = preferred_author_display_name(author)

    # ── Build weighted coauthor graph for PPR + Evans & Chen ──────────────────
    g = nx.Graph()
    for author_id, papers_set in author_to_papers.items():
        g.add_node(author_id, paper_count=len(papers_set))
    for key, papers_list in author_pair_papers.items():
        a, b = key
        g.add_edge(a, b, weight=len(papers_list), papers=papers_list)
    add_normalized_weights(g)

    ppr = ppr_toward_ac(g, ac_member_ids)
    c_norm = evans_chen_c_norm(g)
    author_diversity = {
        node: _normalized_diversity(
            len(g.nodes[node].get("sdl_contexts", set()))
            + len(g.nodes[node].get("institution_contexts", set()))
        )
        for node in g.nodes()
    }
    author_bridge = {
        node: min(
            1.0,
            ppr.get(node, 0.0)
            * max(c_norm.get(node, 1.0), 0.0)
            * max(author_diversity.get(node, 0.0), 0.0),
        )
        for node in g.nodes()
    }
    _BRIDGE_LAMBDA = 0.25  # bonus weight for Evans & Chen excess centrality

    # ── Citations ─────────────────────────────────────────────────────────────
    citations: dict[str, list[CitationSignal]] = {}
    cites_corpus: dict[str, list[str]] = {}
    ac_cores = {c.id: c for c in session.execute(select(AcCorePaper)).scalars()}
    for ref in session.execute(select(PaperReference)).scalars():
        if ref.cited_ac_core_id:
            core = ac_cores.get(ref.cited_ac_core_id)
            if core is not None:
                signals = citations.setdefault(ref.citing_paper_id, [])
                if any(s.cited_ac_core_id == core.id for s in signals):
                    continue
                signals.append(
                    CitationSignal(
                        cited_ac_core_id=core.id,
                        cited_ac_core_title=core.title,
                        cited_doi=core.doi,
                        raw_text=ref.raw_text,
                    )
                )
        if ref.cited_paper_id and ref.cited_paper_id != ref.citing_paper_id:
            cited = cites_corpus.setdefault(ref.citing_paper_id, [])
            if ref.cited_paper_id not in cited:
                cited.append(ref.cited_paper_id)

    signals: dict[str, GraphSignals] = {}
    for paper in session.execute(select(Paper)).scalars():
        paths: list[SecondDegreePath] = []
        author_ids = [aid for aid, _ in paper_to_authors.get(paper.id, [])]
        paper_has_ac_author = any(aid in ac_member_ids for aid in author_ids)

        if not paper_has_ac_author:
            seen_ac_pairs: set[tuple[str, str]] = set()
            for aid in author_ids:
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
                    # second_degree strength now uses normalized edge weight
                    edge_nw = g[aid][partner].get("normalized_weight", 0.0) if g.has_edge(aid, partner) else 0.0
                    paths.append(
                        SecondDegreePath(
                            paper_id=paper.id,
                            via_author_id=aid,
                            via_author_name=author_names.get(aid, aid),
                            ac_author_id=partner,
                            ac_author_name=author_names.get(partner, partner),
                            shared_papers=shared,
                            strength=min(1.0, edge_nw + 0.1 * (len(shared) - 1)),
                        )
                    )

        if paper_has_ac_author:
            network_score = 1.0
        else:
            # PPR_AC × (1 + λ · excess_centrality) — best author wins
            best = 0.0
            for aid in author_ids:
                ppr_score = ppr.get(aid, 0.0)
                excess = max(0.0, c_norm.get(aid, 1.0) - 1.0)
                score = ppr_score * (1.0 + _BRIDGE_LAMBDA * excess)
                best = max(best, score)
            network_score = min(1.0, best)

        bridge_score = max((author_bridge.get(aid, 0.0) for aid in author_ids), default=0.0)
        cross_sdl_diversity = max(
            (author_diversity.get(aid, 0.0) for aid in author_ids), default=0.0
        )

        cite_signals = citations.get(paper.id, [])
        citation_score = min(1.0, 0.5 * len(cite_signals))

        signals[paper.id] = GraphSignals(
            paper_id=paper.id,
            network_score=network_score,
            citation_score=citation_score,
            bridge_score=bridge_score,
            cross_sdl_diversity=cross_sdl_diversity,
            second_degree_paths=paths,
            citation_signals=cite_signals,
            cites_corpus=cites_corpus.get(paper.id, []),
        )

    return signals
