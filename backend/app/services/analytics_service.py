"""Aggregations powering dashboard charts and reporting.

Everything in this module is plain SQL + Python aggregation against the
filtered paper set. RAG / LLM never touch these numbers (per figure.md
§"关键设计：图的数据必须来自结构化表").

v0.6 adds research-intelligence aggregations: year-over-year impact,
citation impact, top emerging collaborators, top growing themes. They are
the SQL half of the reporting assistant — the LLM half is in
`reporting_service.py`.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Author,
    Institution,
    Paper,
    PaperAuthor,
    PaperClassification,
    PaperReference,
)
from app.services.filter_spec import PaperFilter, apply_filter
from app.services.graph_service import build_institution_graph


@dataclass
class SankeyNode:
    id: str
    name: str
    layer: str  # "institution" / "topic" / "label"


@dataclass
class SankeyLink:
    source: str
    target: str
    value: int


@dataclass
class SankeyData:
    nodes: list[SankeyNode]
    links: list[SankeyLink]


@dataclass
class TimelinePoint:
    year: int
    series: str
    count: int


@dataclass
class TimelineSeries:
    name: str  # topic name or label
    data: list[tuple[int, int]]  # (year, count)


@dataclass
class InstitutionGraphNode:
    id: str
    label: str
    is_partner: bool
    country: str | None
    paper_count: int


@dataclass
class InstitutionGraphEdge:
    source: str
    target: str
    weight: int
    papers: list[str]
    normalized_weight: float = 0.0
    involves_partner: bool = False


def _paper_rows(session: Session, filt: PaperFilter):
    """Return (id, year, label, matched_topics) tuples — no full ORM objects.

    Replaces the old _papers_for() that loaded Paper with full eager-loaded
    relationships.  Loading only the four columns we actually need cuts memory
    by ~95 % on large unfiltered datasets.
    """
    return session.execute(
        apply_filter(
            select(
                Paper.id,
                Paper.year,
                PaperClassification.label,
                PaperClassification.matched_topics,
            ).outerjoin(PaperClassification, PaperClassification.paper_id == Paper.id),
            filt,
        )
    ).all()


def institution_topic_label_sankey(
    session: Session,
    filt: PaperFilter,
    *,
    top_institutions: int = 25,
    top_topics: int = 15,
) -> SankeyData:
    """Three-layer Sankey: Institution → Core Topic → Classification Label.

    top_institutions / top_topics cap node counts so the chart stays readable.
    """
    id_subq = apply_filter(select(Paper.id), filt).subquery()
    paper_ids = [row[0] for row in session.execute(select(id_subq.c.id)).all()]
    if not paper_ids:
        return SankeyData(nodes=[], links=[])

    # Institution per paper via lean JOIN — no Paper objects.
    inst_rows = session.execute(
        select(PaperAuthor.paper_id, Institution.id, Institution.canonical_name)
        .join(Author, Author.id == PaperAuthor.author_id)
        .join(Institution, Institution.id == Author.institution_id)
        .where(PaperAuthor.paper_id.in_(paper_ids))
    ).all()
    paper_institutions: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for paper_id, inst_id, inst_name in inst_rows:
        paper_institutions[paper_id].add((inst_id, inst_name))

    # Classification + sdl_tags per paper.
    # Middle layer: prefer matched_topics → fall back to sdl_tags → fall back to reasons prefix.
    cls_rows = session.execute(
        select(
            PaperClassification.paper_id,
            PaperClassification.label,
            PaperClassification.matched_topics,
            Paper.sdl_tags,
        )
        .join(Paper, Paper.id == PaperClassification.paper_id)
        .where(PaperClassification.paper_id.in_(paper_ids))
    ).all()

    inst_to_topic_label: Counter[tuple[str, str, str]] = Counter()
    inst_names: dict[str, str] = {}
    topic_names: dict[str, str] = {}
    label_set: set[str] = set()

    for paper_id, label, matched_topics, sdl_tags in cls_rows:
        if label is None:
            continue
        label_set.add(label)

        # Build topic list: matched_topics first, then sdl_tags as fallback.
        topics: list[tuple[str, str]] = []
        for t in (matched_topics or []):
            if (t.get("score") or 0) > 0.3 and t.get("topic_id") and t.get("name"):
                topics.append((t["topic_id"], t["name"]))
        if not topics:
            for tag in (sdl_tags or []):
                tag = str(tag).strip()
                if tag:
                    tag_id = f"sdl:{tag.lower().replace(' ', '_')}"
                    topics.append((tag_id, tag))

        if not topics:
            continue  # skip papers with neither matched topics nor sdl_tags
        for inst_id, inst_name in paper_institutions.get(paper_id, set()):
            inst_names[inst_id] = inst_name
            for topic_id, topic_name in topics:
                if topic_id is None:
                    continue
                topic_names[topic_id] = topic_name
                inst_to_topic_label[(inst_id, topic_id, label)] += 1

    # Aggregate institution totals and keep only top_institutions
    inst_totals: Counter[str] = Counter()
    for (inst_id, _topic_id, _label), v in inst_to_topic_label.items():
        inst_totals[inst_id] += v
    top_inst_ids = {iid for iid, _ in inst_totals.most_common(top_institutions)}

    # Aggregate topic totals and keep only top_topics
    topic_totals: Counter[str] = Counter()
    for (_inst_id, topic_id, _label), v in inst_to_topic_label.items():
        topic_totals[topic_id] += v
    top_topic_ids = {tid for tid, _ in topic_totals.most_common(top_topics)}

    institution_ids = sorted(top_inst_ids)
    topic_ids = sorted(top_topic_ids)
    label_ids = sorted(label_set)

    nodes = (
        [SankeyNode(id=f"inst:{i}", name=inst_names[i], layer="institution") for i in institution_ids]
        + [SankeyNode(id=f"topic:{t}", name=topic_names[t], layer="topic") for t in topic_ids]
        + [SankeyNode(id=f"label:{l}", name=l.replace("_", " "), layer="label") for l in label_ids]
    )
    inst_topic: Counter[tuple[str, str]] = Counter()
    topic_label: Counter[tuple[str, str]] = Counter()
    for (inst_id, topic_id, label), value in inst_to_topic_label.items():
        if inst_id not in top_inst_ids or topic_id not in top_topic_ids:
            continue
        inst_topic[(inst_id, topic_id)] += value
        topic_label[(topic_id, label)] += value

    links = [
        SankeyLink(source=f"inst:{i}", target=f"topic:{t}", value=v)
        for (i, t), v in inst_topic.items()
    ] + [
        SankeyLink(source=f"topic:{t}", target=f"label:{l}", value=v)
        for (t, l), v in topic_label.items()
    ]
    return SankeyData(nodes=nodes, links=links)


def topic_over_time(
    session: Session, filt: PaperFilter, *, by: str = "topic"
) -> list[TimelineSeries]:
    """Year × series counts. `by` ∈ {"topic", "label"}. Uses lean SQL queries."""
    id_subq = apply_filter(
        select(Paper.id, Paper.year).where(Paper.year.is_not(None)), filt
    ).subquery()
    buckets: dict[str, Counter[int]] = defaultdict(Counter)
    if by == "label":
        rows = session.execute(
            select(id_subq.c.year, PaperClassification.label, func.count())
            .outerjoin(PaperClassification, PaperClassification.paper_id == id_subq.c.id)
            .group_by(id_subq.c.year, PaperClassification.label)
        ).all()
        for year, label, cnt in rows:
            buckets[label or "UNCLASSIFIED"][year] = cnt
    else:  # by topic — load only year + matched_topics JSON, no Paper ORM objects
        rows = session.execute(
            select(id_subq.c.year, PaperClassification.matched_topics)
            .outerjoin(PaperClassification, PaperClassification.paper_id == id_subq.c.id)
        ).all()
        for year, matched_topics in rows:
            topics = [
                t["name"]
                for t in (matched_topics or [])
                if t.get("is_core") and (t.get("score") or 0) > 0.3
            ]
            if not topics:
                buckets["(no core topic)"][year] += 1
            else:
                for topic_name in topics:
                    buckets[topic_name][year] += 1

    series_list: list[TimelineSeries] = []
    for name in sorted(buckets):
        data = sorted(buckets[name].items())
        series_list.append(TimelineSeries(name=name, data=data))
    return series_list


def _norm_field(value: str | None) -> str | None:
    """Normalize semicolon-concatenated institution fields (e.g. 'China;China' → 'China')."""
    if not value:
        return value
    first = next((v.strip() for v in value.split(";") if v.strip()), None)
    return first


def institution_network(
    session: Session, filt: PaperFilter, *, min_papers: int = 1, top_n: int = 50
) -> tuple[list[InstitutionGraphNode], list[InstitutionGraphEdge]]:
    """Institution-level collaboration network restricted to the filtered set.

    top_n caps the number of institutions (by paper_count desc) so the graph
    stays renderable. Default 50; use top_n=200 for a full export.
    """
    paper_ids = {row[0] for row in session.execute(apply_filter(select(Paper.id), filt)).all()}
    g = build_institution_graph(session)

    contrib: Counter[str] = Counter()
    # Walk edges and accumulate paper counts against the filtered set.
    nodes_in_filter: set[str] = set()
    raw_edges: list[tuple[str, str, list[str]]] = []
    for src, dst, data in g.edges(data=True):
        joint = [p for p in data.get("papers", []) if p in paper_ids]
        if not joint:
            continue
        raw_edges.append((src, dst, joint))
        nodes_in_filter.add(src)
        nodes_in_filter.add(dst)
        contrib[src] += len(joint)
        contrib[dst] += len(joint)

    partner_nodes: set[str] = {
        node_id
        for node_id in nodes_in_filter
        if g.nodes[node_id].get("is_partner")
    }

    edges_filtered: list[InstitutionGraphEdge] = []
    for src, dst, joint in raw_edges:
        weight = len(joint)
        min_contrib = min(contrib.get(src, 1), contrib.get(dst, 1))
        normalized = round(weight / max(min_contrib, 1), 4)
        edges_filtered.append(
            InstitutionGraphEdge(
                source=src,
                target=dst,
                weight=weight,
                papers=joint,
                normalized_weight=min(normalized, 1.0),
                involves_partner=(src in partner_nodes or dst in partner_nodes),
            )
        )

    # Build all qualifying nodes
    all_nodes: list[InstitutionGraphNode] = []
    for node_id in nodes_in_filter:
        data = g.nodes[node_id]
        paper_count = contrib[node_id]
        if paper_count < min_papers:
            continue
        all_nodes.append(
            InstitutionGraphNode(
                id=node_id,
                label=data.get("label", node_id),
                is_partner=bool(data.get("is_partner", False)),
                country=_norm_field(data.get("country")),
                paper_count=paper_count,
            )
        )

    # Cap to top_n by paper_count so the graph stays renderable
    nodes_out = sorted(all_nodes, key=lambda n: -n.paper_count)[:top_n]
    keep_node_ids = {n.id for n in nodes_out}
    edges_out = [e for e in edges_filtered if e.source in keep_node_ids and e.target in keep_node_ids]

    return nodes_out, edges_out


def label_breakdown(session: Session, filt: PaperFilter) -> dict[str, int]:
    id_subq = apply_filter(select(Paper.id), filt).subquery()
    rows = session.execute(
        select(PaperClassification.label, func.count())
        .where(PaperClassification.paper_id.in_(select(id_subq.c.id)))
        .group_by(PaperClassification.label)
    ).all()
    return {label: cnt for label, cnt in rows if label}


# ---------------------------------------------------------------------------
# v0.6: Research impact aggregations
# ---------------------------------------------------------------------------


# Labels counted as "AC-attributed" for impact reporting purposes.
ATTRIBUTED_LABELS = {"CORE_RELEVANT", "RELATED_RELEVANT"}


@dataclass
class YearMetric:
    year: int
    value: int


@dataclass
class GrowthSeries:
    name: str
    points: list[YearMetric]


@dataclass
class EmergingEntity:
    """An institution or author that appears in the corpus for the first time
    in a given year. Used to surface 'who's new this year' in impact panels.
    """

    entity_type: str  # "institution" | "author"
    id: str
    label: str
    first_year: int
    paper_count: int
    is_partner: bool | None = None


@dataclass
class ThemeGrowth:
    topic_id: str
    name: str
    value_now: int
    value_then: int
    delta_pct: float


@dataclass
class ImpactReport:
    """Top-level shape for the /analytics/impact endpoint."""

    yoy_attributed: GrowthSeries
    yoy_by_label: list[GrowthSeries]
    citation_impact: GrowthSeries
    emerging_institutions: list[EmergingEntity]
    emerging_authors: list[EmergingEntity]
    top_growing_themes: list[ThemeGrowth]
    window_from: int | None
    window_to: int | None


def build_impact_report(session: Session, filt: PaperFilter) -> ImpactReport:
    """Build all impact metrics using lean SQL queries — no full Paper ORM objects."""
    rows = _paper_rows(session, filt)  # (id, year, label, matched_topics)
    if not rows:
        return ImpactReport(
            yoy_attributed=GrowthSeries(name="ac_attributed_papers", points=[]),
            yoy_by_label=[],
            citation_impact=GrowthSeries(name="corpus_citation_edges", points=[]),
            emerging_institutions=[],
            emerging_authors=[],
            top_growing_themes=[],
            window_from=filt.year_from,
            window_to=filt.year_to,
        )

    paper_ids = [r[0] for r in rows]
    year_by_id = {r[0]: r[1] for r in rows if r[1] is not None}

    # --- YoY attributed & by-label (no DB round-trip needed) ---
    attr_counts: Counter[int] = Counter()
    label_counts: dict[str, Counter[int]] = defaultdict(Counter)
    for pid, year, label, _ in rows:
        if year is None or label is None:
            continue
        if label in ATTRIBUTED_LABELS:
            attr_counts[year] += 1
        label_counts[label][year] += 1

    yoy_attributed = GrowthSeries(
        name="ac_attributed_papers",
        points=[YearMetric(year=y, value=attr_counts[y]) for y in sorted(attr_counts)],
    )
    yoy_by_label = [
        GrowthSeries(
            name=lbl,
            points=[YearMetric(year=y, value=cnt[y]) for y in sorted(cnt)],
        )
        for lbl, cnt in sorted(label_counts.items())
    ]

    # --- Citation impact: cite count grouped by citing-paper's year ---
    cite_rows = session.execute(
        select(PaperReference.citing_paper_id).where(
            PaperReference.citing_paper_id.in_(paper_ids),
            PaperReference.cited_paper_id.is_not(None),
        )
    ).all()
    cite_counts: Counter[int] = Counter()
    for (citing_id,) in cite_rows:
        yr = year_by_id.get(citing_id)
        if yr is not None:
            cite_counts[yr] += 1
    citation_impact = GrowthSeries(
        name="corpus_citation_edges",
        points=[YearMetric(year=y, value=cite_counts[y]) for y in sorted(cite_counts)],
    )

    # --- Emerging institutions (SQL JOIN, no Paper iteration) ---
    inst_pa_rows = session.execute(
        select(Paper.year, Institution.id, Institution.canonical_name, Institution.is_partner)
        .join(PaperAuthor, PaperAuthor.paper_id == Paper.id)
        .join(Author, Author.id == PaperAuthor.author_id)
        .join(Institution, Institution.id == Author.institution_id)
        .where(Paper.id.in_(paper_ids), Paper.year.is_not(None))
    ).all()
    inst_first: dict[str, tuple[int, str, bool]] = {}
    inst_paper_count: Counter[str] = Counter()
    for yr, inst_id, inst_name, is_partner in inst_pa_rows:
        existing = inst_first.get(inst_id)
        if existing is None or yr < existing[0]:
            inst_first[inst_id] = (yr, inst_name, bool(is_partner))
        inst_paper_count[inst_id] += 1
    wf, wt = filt.year_from, filt.year_to
    emerging_institutions = sorted(
        [
            EmergingEntity(entity_type="institution", id=iid, label=lbl, first_year=yr,
                           paper_count=inst_paper_count[iid], is_partner=isp)
            for iid, (yr, lbl, isp) in inst_first.items()
            if (wf is None or yr >= wf) and (wt is None or yr <= wt)
        ],
        key=lambda e: (-e.paper_count, e.first_year, e.label),
    )[:10]

    # --- Emerging authors ---
    auth_pa_rows = session.execute(
        select(Paper.year, Author.id, Author.canonical_name)
        .join(PaperAuthor, PaperAuthor.paper_id == Paper.id)
        .join(Author, Author.id == PaperAuthor.author_id)
        .where(Paper.id.in_(paper_ids), Paper.year.is_not(None))
    ).all()
    auth_first: dict[str, tuple[int, str]] = {}
    auth_count: Counter[str] = Counter()
    for yr, aid, aname in auth_pa_rows:
        existing = auth_first.get(aid)
        if existing is None or yr < existing[0]:
            auth_first[aid] = (yr, aname)
        auth_count[aid] += 1
    emerging_authors = sorted(
        [
            EmergingEntity(entity_type="author", id=aid, label=lbl, first_year=yr,
                           paper_count=auth_count[aid])
            for aid, (yr, lbl) in auth_first.items()
            if (wf is None or yr >= wf) and (wt is None or yr <= wt)
        ],
        key=lambda e: (-e.paper_count, e.first_year, e.label),
    )[:10]

    # --- Top growing themes ---
    all_years = [r[1] for r in rows if r[1] is not None]
    tw_from = wf if wf is not None else (min(all_years) if all_years else None)
    tw_to = wt if wt is not None else (max(all_years) if all_years else None)
    top_growing_themes: list[ThemeGrowth] = []
    if tw_from is not None and tw_to is not None and tw_to > tw_from:
        midpoint = (tw_from + tw_to) // 2
        before: Counter[tuple[str, str]] = Counter()
        after: Counter[tuple[str, str]] = Counter()
        for _, year, _, matched_topics in rows:
            if year is None or not (tw_from <= year <= tw_to):
                continue
            for tm in (matched_topics or []):
                if not tm.get("is_core") or (tm.get("score") or 0) < 0.3:
                    continue
                key = (tm.get("topic_id"), tm.get("name") or tm.get("topic_id"))
                if year <= midpoint:
                    before[key] += 1
                else:
                    after[key] += 1
        theme_list = []
        for key in set(before) | set(after):
            tid, name = key
            b, a = before[key], after[key]
            if a + b == 0:
                continue
            dp = float("inf") if b == 0 else round((a - b) / b * 100.0, 1)
            theme_list.append(ThemeGrowth(topic_id=tid, name=name, value_now=a, value_then=b, delta_pct=dp))
        theme_list.sort(key=lambda t: (0 if t.delta_pct == float("inf") else 1,
                                        -(t.value_now + t.value_then),
                                        -t.delta_pct if t.delta_pct != float("inf") else 0.0))
        top_growing_themes = theme_list[:10]

    return ImpactReport(
        yoy_attributed=yoy_attributed,
        yoy_by_label=yoy_by_label,
        citation_impact=citation_impact,
        emerging_institutions=emerging_institutions,
        emerging_authors=emerging_authors,
        top_growing_themes=top_growing_themes,
        window_from=filt.year_from,
        window_to=filt.year_to,
    )
