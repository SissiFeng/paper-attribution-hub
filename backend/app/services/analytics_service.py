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

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

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


def _papers_for(session: Session, filt: PaperFilter) -> list[Paper]:
    stmt = apply_filter(
        select(Paper).options(
            selectinload(Paper.classification),
            selectinload(Paper.authors)
            .selectinload(PaperAuthor.author)
            .selectinload(Author.institution),
        ),
        filt,
    )
    return list(session.execute(stmt).scalars())


def institution_topic_label_sankey(
    session: Session, filt: PaperFilter
) -> SankeyData:
    """Three-layer Sankey: Institution → Core Topic → Classification Label.

    A paper contributes 1 unit per (institution, topic, label) triple it covers.
    Multi-affiliation / multi-topic papers contribute multiple links — this is
    correct for "where do AC contributions come from"; consumers can weight
    later if they need fractional attribution.
    """
    papers = _papers_for(session, filt)
    paper_ids = [p.id for p in papers]
    if not paper_ids:
        return SankeyData(nodes=[], links=[])

    # Institutions per paper (via the ORM relationships).
    paper_institutions: dict[str, set[tuple[str, str]]] = {}
    for paper in papers:
        s: set[tuple[str, str]] = set()
        for pa in paper.authors:
            inst = pa.author.institution
            if inst is None:
                continue
            s.add((inst.id, inst.canonical_name))
        paper_institutions[paper.id] = s

    inst_to_topic_label: Counter[tuple[str, str, str]] = Counter()
    inst_names: dict[str, str] = {}
    topic_names: dict[str, str] = {}

    for paper in papers:
        cls = paper.classification
        if cls is None:
            continue
        topics = [
            (t.get("topic_id"), t.get("name"))
            for t in (cls.matched_topics or [])
            if t.get("is_core") and (t.get("score") or 0) > 0.3
        ]
        if not topics:
            topics = [("none", "(no core topic)")]

        for inst_id, inst_name in paper_institutions.get(paper.id, set()):
            inst_names[inst_id] = inst_name
            for topic_id, topic_name in topics:
                if topic_id is None:
                    continue
                topic_names[topic_id] = topic_name
                inst_to_topic_label[(inst_id, topic_id, cls.label)] += 1

    institution_ids = sorted(inst_names)
    topic_ids = sorted(topic_names)
    label_ids = sorted({cls.label for cls in (p.classification for p in papers) if cls})

    nodes = (
        [SankeyNode(id=f"inst:{i}", name=inst_names[i], layer="institution") for i in institution_ids]
        + [SankeyNode(id=f"topic:{t}", name=topic_names[t], layer="topic") for t in topic_ids]
        + [SankeyNode(id=f"label:{l}", name=l.replace("_", " "), layer="label") for l in label_ids]
    )

    inst_topic: Counter[tuple[str, str]] = Counter()
    topic_label: Counter[tuple[str, str]] = Counter()
    for (inst_id, topic_id, label), value in inst_to_topic_label.items():
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
    """Year × series counts. `by` ∈ {"topic", "label"}."""
    papers = _papers_for(session, filt)
    buckets: dict[str, Counter[int]] = defaultdict(Counter)
    for paper in papers:
        if paper.year is None:
            continue
        cls = paper.classification
        if by == "label":
            series = cls.label if cls else "UNCLASSIFIED"
            buckets[series][paper.year] += 1
        else:  # by topic
            topics = (
                [
                    t["name"]
                    for t in (cls.matched_topics or [])
                    if t.get("is_core") and (t.get("score") or 0) > 0.3
                ]
                if cls
                else []
            )
            if not topics:
                buckets["(no core topic)"][paper.year] += 1
            else:
                for topic_name in topics:
                    buckets[topic_name][paper.year] += 1

    series_list: list[TimelineSeries] = []
    for name in sorted(buckets):
        data = sorted(buckets[name].items())
        series_list.append(TimelineSeries(name=name, data=data))
    return series_list


def institution_network(
    session: Session, filt: PaperFilter, *, min_papers: int = 1
) -> tuple[list[InstitutionGraphNode], list[InstitutionGraphEdge]]:
    """Institution-level collaboration network restricted to the filtered set."""
    paper_ids = {p.id for p in _papers_for(session, filt)}
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

    nodes_out: list[InstitutionGraphNode] = []
    for node_id in nodes_in_filter:
        data = g.nodes[node_id]
        paper_count = contrib[node_id]
        if paper_count < min_papers:
            continue
        nodes_out.append(
            InstitutionGraphNode(
                id=node_id,
                label=data.get("label", node_id),
                is_partner=bool(data.get("is_partner", False)),
                country=data.get("country"),
                paper_count=paper_count,
            )
        )
    # Drop edges whose endpoints fell below the threshold.
    keep_node_ids = {n.id for n in nodes_out}
    edges_out = [e for e in edges_filtered if e.source in keep_node_ids and e.target in keep_node_ids]

    return nodes_out, edges_out


def label_breakdown(session: Session, filt: PaperFilter) -> dict[str, int]:
    papers = _papers_for(session, filt)
    out: Counter[str] = Counter()
    for p in papers:
        if p.classification:
            out[p.classification.label] += 1
    return dict(out)


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


def _yoy_attributed(papers: list[Paper]) -> GrowthSeries:
    counts: Counter[int] = Counter()
    for p in papers:
        if p.year is None or p.classification is None:
            continue
        if p.classification.label in ATTRIBUTED_LABELS:
            counts[p.year] += 1
    points = [YearMetric(year=y, value=counts[y]) for y in sorted(counts)]
    return GrowthSeries(name="ac_attributed_papers", points=points)


def _yoy_by_label(papers: list[Paper]) -> list[GrowthSeries]:
    buckets: dict[str, Counter[int]] = defaultdict(Counter)
    for p in papers:
        if p.year is None or p.classification is None:
            continue
        buckets[p.classification.label][p.year] += 1
    series: list[GrowthSeries] = []
    for label in sorted(buckets):
        years = sorted(buckets[label])
        series.append(
            GrowthSeries(
                name=label,
                points=[YearMetric(year=y, value=buckets[label][y]) for y in years],
            )
        )
    return series


def _citation_impact(session: Session, papers: list[Paper]) -> GrowthSeries:
    """For each year, count `paper_references.cited_paper_id` rows whose
    *citing* paper has that publication year. This measures "how many
    references our attributed papers made", which is the cleanest impact
    proxy we can compute from the corpus alone (a full impact metric would
    need cited_by_count from OpenAlex; that's a v0.7 add).
    """
    paper_year_by_id = {p.id: p.year for p in papers if p.year is not None}
    rows = session.execute(
        select(PaperReference.citing_paper_id).where(
            PaperReference.cited_paper_id.is_not(None)
        )
    ).all()
    counts: Counter[int] = Counter()
    for (citing_id,) in rows:
        year = paper_year_by_id.get(citing_id)
        if year is None:
            continue
        counts[year] += 1
    points = [YearMetric(year=y, value=counts[y]) for y in sorted(counts)]
    return GrowthSeries(name="corpus_citation_edges", points=points)


def _emerging_institutions(
    session: Session,
    papers: list[Paper],
    *,
    window_from: int | None,
    window_to: int | None,
    top_n: int = 10,
) -> list[EmergingEntity]:
    """Institutions whose first contribution to the corpus falls inside the
    window. Sorted by paper_count desc."""
    first_seen: dict[str, tuple[int, str, bool]] = {}
    counts: Counter[str] = Counter()
    for p in papers:
        if p.year is None:
            continue
        for pa in p.authors:
            inst = pa.author.institution
            if inst is None:
                continue
            existing = first_seen.get(inst.id)
            if existing is None or p.year < existing[0]:
                first_seen[inst.id] = (p.year, inst.canonical_name, bool(inst.is_partner))
            counts[inst.id] += 1

    out: list[EmergingEntity] = []
    for inst_id, (year, label, is_partner) in first_seen.items():
        if window_from is not None and year < window_from:
            continue
        if window_to is not None and year > window_to:
            continue
        out.append(
            EmergingEntity(
                entity_type="institution",
                id=inst_id,
                label=label,
                first_year=year,
                paper_count=counts[inst_id],
                is_partner=is_partner,
            )
        )
    out.sort(key=lambda e: (-e.paper_count, e.first_year, e.label))
    return out[:top_n]


def _emerging_authors(
    session: Session,
    papers: list[Paper],
    *,
    window_from: int | None,
    window_to: int | None,
    top_n: int = 10,
) -> list[EmergingEntity]:
    """Same logic for authors — earliest paper year inside the window."""
    first_seen: dict[str, tuple[int, str]] = {}
    counts: Counter[str] = Counter()
    for p in papers:
        if p.year is None:
            continue
        for pa in p.authors:
            a = pa.author
            existing = first_seen.get(a.id)
            if existing is None or p.year < existing[0]:
                first_seen[a.id] = (p.year, a.canonical_name)
            counts[a.id] += 1

    out: list[EmergingEntity] = []
    for author_id, (year, label) in first_seen.items():
        if window_from is not None and year < window_from:
            continue
        if window_to is not None and year > window_to:
            continue
        out.append(
            EmergingEntity(
                entity_type="author",
                id=author_id,
                label=label,
                first_year=year,
                paper_count=counts[author_id],
            )
        )
    out.sort(key=lambda e: (-e.paper_count, e.first_year, e.label))
    return out[:top_n]


def _top_growing_themes(
    papers: list[Paper],
    *,
    window_from: int | None,
    window_to: int | None,
    top_n: int = 10,
) -> list[ThemeGrowth]:
    """For each core topic, compare paper count in the latter half of the
    window to the former half. Themes with the highest delta_pct surface.
    """
    if window_from is None or window_to is None:
        years = [p.year for p in papers if p.year is not None]
        if not years:
            return []
        window_from = min(years)
        window_to = max(years)
    if window_to <= window_from:
        return []

    midpoint = (window_from + window_to) // 2
    before: Counter[tuple[str, str]] = Counter()  # (topic_id, name) -> count
    after: Counter[tuple[str, str]] = Counter()

    for p in papers:
        if p.year is None or p.classification is None:
            continue
        if not (window_from <= p.year <= window_to):
            continue
        for tm in p.classification.matched_topics or []:
            if not tm.get("is_core"):
                continue
            if (tm.get("score") or 0) < 0.3:
                continue
            key = (tm.get("topic_id"), tm.get("name") or tm.get("topic_id"))
            if p.year <= midpoint:
                before[key] += 1
            else:
                after[key] += 1

    out: list[ThemeGrowth] = []
    for key in set(before) | set(after):
        topic_id, name = key
        b = before[key]
        a = after[key]
        if a + b == 0:
            continue
        if b == 0:
            delta_pct = float("inf")
        else:
            delta_pct = round((a - b) / b * 100.0, 1)
        out.append(
            ThemeGrowth(
                topic_id=topic_id,
                name=name,
                value_now=a,
                value_then=b,
                delta_pct=delta_pct,
            )
        )
    # Sort: finite deltas first by delta desc; "infinite" (brand-new themes) at the top.
    out.sort(
        key=lambda t: (
            0 if t.delta_pct == float("inf") else 1,
            -(t.value_now + t.value_then),
            -t.delta_pct if t.delta_pct != float("inf") else 0.0,
        )
    )
    return out[:top_n]


def build_impact_report(session: Session, filt: PaperFilter) -> ImpactReport:
    papers = _papers_for(session, filt)
    return ImpactReport(
        yoy_attributed=_yoy_attributed(papers),
        yoy_by_label=_yoy_by_label(papers),
        citation_impact=_citation_impact(session, papers),
        emerging_institutions=_emerging_institutions(
            session, papers, window_from=filt.year_from, window_to=filt.year_to
        ),
        emerging_authors=_emerging_authors(
            session, papers, window_from=filt.year_from, window_to=filt.year_to
        ),
        top_growing_themes=_top_growing_themes(
            papers, window_from=filt.year_from, window_to=filt.year_to
        ),
        window_from=filt.year_from,
        window_to=filt.year_to,
    )
