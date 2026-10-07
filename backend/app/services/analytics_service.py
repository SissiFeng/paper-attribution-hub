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
import hashlib
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.country_normalization import canonical_country_entries
from app.models import (
    Author,
    Institution,
    Paper,
    PaperAuthor,
    PaperClassification,
    PaperEntity,
    PaperReference,
)
from app.services.filter_spec import (
    PAPER_SET_ENCODING,
    PaperFilter,
    apply_filter,
    build_filter_audit,
    paper_set_sha256,
    split_semicolon_values,
)
from app.services.graph_service import build_institution_graph
from app.services.topic_identity import canonical_topic_names


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


def _stage1_institution_id(name: str) -> str:
    identity = re.sub(r"\s+", " ", name.strip()).casefold()
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16]
    return f"stage1:{digest}"


def _stage1_paper_institutions(
    session: Session,
    paper_ids: set[str] | list[str],
) -> tuple[dict[str, set[tuple[str, str]]], dict[str, str]]:
    ids = set(paper_ids)
    if not ids:
        return {}, {}
    rows = session.execute(
        select(PaperEntity.paper_id, PaperEntity.normalized_name).where(
            PaperEntity.paper_id.in_(ids),
            PaperEntity.entity_type == "institution",
        )
    ).all()
    by_paper: dict[str, set[tuple[str, str]]] = defaultdict(set)
    names: dict[str, str] = {}
    for paper_id, normalized_name in rows:
        name = str(normalized_name or "").strip()
        if not name:
            continue
        institution_id = _stage1_institution_id(name)
        by_paper[paper_id].add((institution_id, name))
        names[institution_id] = name
    return dict(by_paper), names


def _paper_rows(session: Session, filt: PaperFilter):
    """Return (id, year, label, matched_topics) tuples — no full ORM objects.

    Replaces the old _papers_for() that loaded Paper with full eager-loaded
    relationships.  Loading only the four columns we actually need cuts memory
    by ~95 % on large unfiltered datasets.
    """
    filtered_ids = apply_filter(select(Paper.id), filt).subquery()
    return session.execute(
        select(
            filtered_ids.c.id,
            Paper.year,
            PaperClassification.label,
            PaperClassification.matched_topics,
        )
        .join(Paper, Paper.id == filtered_ids.c.id)
        .outerjoin(PaperClassification, PaperClassification.paper_id == Paper.id)
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

    # In Stage 1, institutions are paper-level Markdown affiliation mentions.
    if settings.sdl_stage1_only:
        paper_institutions, inst_names = _stage1_paper_institutions(
            session,
            paper_ids,
        )
    else:
        inst_rows = session.execute(
            select(
                PaperAuthor.paper_id,
                Institution.id,
                Institution.canonical_name,
            )
            .join(Author, Author.id == PaperAuthor.author_id)
            .join(Institution, Institution.id == Author.institution_id)
            .where(PaperAuthor.paper_id.in_(paper_ids))
        ).all()
        paper_institutions = defaultdict(set)
        inst_names = {}
        for paper_id, inst_id, inst_name in inst_rows:
            paper_institutions[paper_id].add((inst_id, inst_name))
            inst_names[inst_id] = inst_name

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

    path_papers: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    topic_names: dict[str, str] = {}

    for paper_id, label, matched_topics, sdl_tags in cls_rows:
        if label is None:
            continue

        # Build topic list: matched_topics first, then sdl_tags as fallback.
        topics: dict[str, str] = {}
        for t in (matched_topics or []):
            if (t.get("score") or 0) > 0.3 and t.get("topic_id") and t.get("name"):
                topics[t["topic_id"]] = t["name"]
        if not topics:
            for tag in (sdl_tags or []):
                tag = str(tag).strip()
                if tag:
                    tag_id = f"sdl:{tag.lower().replace(' ', '_')}"
                    topics[tag_id] = tag

        if not topics:
            continue  # skip papers with neither matched topics nor sdl_tags
        for inst_id, inst_name in paper_institutions.get(paper_id, set()):
            inst_names[inst_id] = inst_name
            for topic_id, topic_name in topics.items():
                if topic_id is None:
                    continue
                topic_names[topic_id] = topic_name
                path_papers[(inst_id, topic_id, label)].add(paper_id)

    # Aggregate institution totals and keep only top_institutions
    inst_totals: dict[str, set[str]] = defaultdict(set)
    for (inst_id, _topic_id, _label), papers in path_papers.items():
        inst_totals[inst_id].update(papers)
    top_inst_ids = {
        inst_id
        for inst_id, _papers in sorted(
            inst_totals.items(), key=lambda item: (-len(item[1]), item[0])
        )[:top_institutions]
    }

    # Aggregate topic totals and keep only top_topics
    topic_totals: dict[str, set[str]] = defaultdict(set)
    for (_inst_id, topic_id, _label), papers in path_papers.items():
        topic_totals[topic_id].update(papers)
    top_topic_ids = {
        topic_id
        for topic_id, _papers in sorted(
            topic_totals.items(), key=lambda item: (-len(item[1]), item[0])
        )[:top_topics]
    }

    institution_ids = sorted(top_inst_ids)
    topic_ids = sorted(top_topic_ids)
    inst_topic: dict[tuple[str, str], set[str]] = defaultdict(set)
    topic_label: dict[tuple[str, str], set[str]] = defaultdict(set)
    for (inst_id, topic_id, label), papers in path_papers.items():
        if inst_id not in top_inst_ids or topic_id not in top_topic_ids:
            continue
        inst_topic[(inst_id, topic_id)].update(papers)
        topic_label[(topic_id, label)].update(papers)

    label_ids = sorted({label for _topic, label in topic_label})
    nodes = (
        [
            SankeyNode(
                id=f"inst:{institution_id}",
                name=inst_names[institution_id],
                layer="institution",
            )
            for institution_id in institution_ids
        ]
        + [
            SankeyNode(
                id=f"topic:{topic_id}",
                name=topic_names[topic_id],
                layer="topic",
            )
            for topic_id in topic_ids
        ]
        + [
            SankeyNode(
                id=f"label:{label}",
                name=label.replace("_", " "),
                layer="label",
            )
            for label in label_ids
        ]
    )

    links = [
        SankeyLink(
            source=f"inst:{institution_id}",
            target=f"topic:{topic_id}",
            value=len(papers),
        )
        for (institution_id, topic_id), papers in inst_topic.items()
    ] + [
        SankeyLink(
            source=f"topic:{topic}",
            target=f"label:{label}",
            value=len(papers),
        )
        for (topic, label), papers in topic_label.items()
    ]
    return SankeyData(nodes=nodes, links=links)


def topic_over_time(
    session: Session,
    filt: PaperFilter,
    *,
    by: str = "topic",
    top_n: int | None = None,
) -> list[TimelineSeries]:
    """Year × distinct-paper counts for a supported grouping dimension."""
    id_subq = apply_filter(
        select(Paper.id, Paper.year).where(Paper.year.is_not(None)), filt
    ).subquery()
    buckets: dict[str, Counter[int]] = defaultdict(Counter)
    country_display: dict[str, str] = {}
    if by == "label":
        rows = session.execute(
            select(id_subq.c.year, PaperClassification.label, func.count())
            .outerjoin(PaperClassification, PaperClassification.paper_id == id_subq.c.id)
            .group_by(id_subq.c.year, PaperClassification.label)
        ).all()
        for year, label, cnt in rows:
            buckets[label or "UNCLASSIFIED"][year] = cnt
    elif by == "institution":
        if settings.sdl_stage1_only:
            rows = session.execute(
                select(
                    id_subq.c.year,
                    id_subq.c.id,
                    PaperEntity.normalized_name,
                )
                .join(PaperEntity, PaperEntity.paper_id == id_subq.c.id)
                .where(PaperEntity.entity_type == "institution")
            ).all()
        else:
            rows = session.execute(
                select(
                    id_subq.c.year,
                    id_subq.c.id,
                    Institution.canonical_name,
                )
                .join(PaperAuthor, PaperAuthor.paper_id == id_subq.c.id)
                .join(Author, Author.id == PaperAuthor.author_id)
                .join(Institution, Institution.id == Author.institution_id)
            ).all()
        seen: set[tuple[int, str, str]] = set()
        for year, paper_id, institution_name in rows:
            key = (year, paper_id, institution_name)
            if key in seen:
                continue
            seen.add(key)
            buckets[institution_name][year] += 1
    elif by == "country":
        rows = session.execute(
            select(id_subq.c.year, id_subq.c.id, Institution.country)
            .join(PaperAuthor, PaperAuthor.paper_id == id_subq.c.id)
            .join(Author, Author.id == PaperAuthor.author_id)
            .join(Institution, Institution.id == Author.institution_id)
            .where(Institution.country.is_not(None))
        ).all()
        seen: set[tuple[int, str, str]] = set()
        for year, paper_id, raw_country in rows:
            for country in canonical_country_entries(raw_country):
                key = (year, paper_id, country.identity)
                if key in seen:
                    continue
                seen.add(key)
                country_display[country.identity] = country.display
                buckets[country.identity][year] += 1
    elif by == "field":
        rows = session.execute(
            select(
                id_subq.c.year,
                id_subq.c.id,
                Paper.sdl_tags,
                Paper.research_tags,
            ).join(Paper, Paper.id == id_subq.c.id)
        ).all()
        for year, _paper_id, sdl_tags, research_tags in rows:
            fields = {
                str(value).strip()
                for values in (sdl_tags or [], research_tags or [])
                for value in values
                if str(value).strip()
            }
            if not fields:
                buckets["(no field)"][year] += 1
            else:
                for field in fields:
                    buckets[field][year] += 1
    else:  # by topic — load only year + matched_topics JSON, no Paper ORM objects
        rows = session.execute(
            select(id_subq.c.year, PaperClassification.matched_topics)
            .outerjoin(PaperClassification, PaperClassification.paper_id == id_subq.c.id)
        ).all()
        for year, matched_topics in rows:
            topics = {
                t["name"]
                for t in (matched_topics or [])
                if t.get("is_core") and (t.get("score") or 0) > 0.3
            }
            if not topics:
                buckets["(no core topic)"][year] += 1
            else:
                for topic_name in topics:
                    buckets[topic_name][year] += 1

    ranked_names = sorted(
        buckets,
        key=lambda name: (
            -sum(buckets[name].values()),
            country_display.get(name, name).casefold(),
            country_display.get(name, name),
            name,
        ),
    )
    if top_n is not None:
        ranked_names = ranked_names[:top_n]
    series_list: list[TimelineSeries] = []
    for name in ranked_names:
        data = sorted(buckets[name].items())
        series_list.append(
            TimelineSeries(name=country_display.get(name, name), data=data)
        )
    return series_list


def _norm_field(value: str | None) -> str | None:
    """Normalize a semicolon-concatenated field without dropping values."""
    normalized = split_semicolon_values(value)
    return "; ".join(normalized) or None


def institution_network(
    session: Session, filt: PaperFilter, *, min_papers: int = 1, top_n: int = 50
) -> tuple[list[InstitutionGraphNode], list[InstitutionGraphEdge]]:
    """Institution-level collaboration network restricted to the filtered set.

    top_n caps the number of institutions (by paper_count desc) so the graph
    stays renderable. Default 50; use top_n=200 for a full export.
    """
    paper_ids = {row[0] for row in session.execute(apply_filter(select(Paper.id), filt)).all()}
    if settings.sdl_stage1_only:
        if filt.partner_only:
            return [], []
        paper_institutions, institution_names = _stage1_paper_institutions(
            session,
            paper_ids,
        )
        institution_papers: dict[str, set[str]] = defaultdict(set)
        shared_papers: dict[tuple[str, str], set[str]] = defaultdict(set)
        for paper_id, institutions in paper_institutions.items():
            institution_ids = sorted(inst_id for inst_id, _name in institutions)
            for institution_id in institution_ids:
                institution_papers[institution_id].add(paper_id)
            for index, source in enumerate(institution_ids):
                for target in institution_ids[index + 1 :]:
                    shared_papers[(source, target)].add(paper_id)

        ranked_ids = [
            institution_id
            for institution_id in sorted(
                institution_papers,
                key=lambda inst_id: (
                    -len(institution_papers[inst_id]),
                    institution_names[inst_id].casefold(),
                    institution_names[inst_id],
                    inst_id,
                ),
            )
            if len(institution_papers[institution_id]) >= min_papers
        ][:top_n]
        keep_ids = set(ranked_ids)
        nodes = [
            InstitutionGraphNode(
                id=institution_id,
                label=institution_names[institution_id],
                is_partner=False,
                country=None,
                paper_count=len(institution_papers[institution_id]),
            )
            for institution_id in ranked_ids
        ]
        edges = []
        for (source, target), shared in sorted(shared_papers.items()):
            if source not in keep_ids or target not in keep_ids:
                continue
            smaller_count = min(
                len(institution_papers[source]),
                len(institution_papers[target]),
            )
            edges.append(
                InstitutionGraphEdge(
                    source=source,
                    target=target,
                    weight=len(shared),
                    papers=sorted(shared),
                    normalized_weight=round(
                        len(shared) / max(smaller_count, 1),
                        4,
                    ),
                    involves_partner=False,
                )
            )
        return nodes, edges

    g = build_institution_graph(session)

    paper_contrib: Counter[str] = Counter()
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

    # Include institutions that appear in filtered papers even when they have
    # no remaining collaboration edge. Partner-only views can otherwise look
    # empty for papers with a single partner institution.
    inst_rows = session.execute(
        select(PaperAuthor.paper_id, Author.institution_id)
        .join(Author, Author.id == PaperAuthor.author_id)
        .where(
            PaperAuthor.paper_id.in_(paper_ids),
            Author.institution_id.is_not(None),
        )
    ).all()
    seen_paper_inst: set[tuple[str, str]] = set()
    for paper_id, inst_id in inst_rows:
        if inst_id not in g:
            continue
        if filt.partner_only and not g.nodes[inst_id].get("is_partner"):
            continue
        key = (paper_id, inst_id)
        if key in seen_paper_inst:
            continue
        seen_paper_inst.add(key)
        nodes_in_filter.add(inst_id)
        paper_contrib[inst_id] += 1

    partner_nodes: set[str] = {
        node_id
        for node_id in nodes_in_filter
        if g.nodes[node_id].get("is_partner")
    }

    edges_filtered: list[InstitutionGraphEdge] = []
    for src, dst, joint in raw_edges:
        weight = len(joint)
        smaller_endpoint_count = min(
            paper_contrib.get(src, 0),
            paper_contrib.get(dst, 0),
        )
        normalized = round(weight / max(smaller_endpoint_count, 1), 4)
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
        paper_count = paper_contrib[node_id]
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
    if filt.partner_only:
        partner_keep = {n.id for n in nodes_out if n.is_partner}
        nodes_out = [n for n in nodes_out if n.id in partner_keep]
        edges_out = [
            e for e in edges_out if e.source in partner_keep and e.target in partner_keep
        ]

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
    """An entity whose first paper in the selected non-temporal scope falls in
    the requested year window. Used to surface "who's new" in impact panels.
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
class InstitutionCitationIndex:
    institution_id: str
    institution_name: str
    paper_count: int
    normalized_index: float


@dataclass
class NormalizedCitationImpact:
    metric_name: str
    normalized_index: float | None
    covered_papers: int
    total_papers: int
    coverage: float
    snapshot_oldest_at: str | None
    snapshot_newest_at: str | None
    source_breakdown: dict[str, int]
    by_institution: list[InstitutionCitationIndex]


@dataclass
class ImpactReport:
    """Top-level shape for the /analytics/impact endpoint."""

    yoy_attributed: GrowthSeries
    yoy_by_label: list[GrowthSeries]
    citation_impact: GrowthSeries
    normalized_citation_impact: NormalizedCitationImpact
    emerging_institutions: list[EmergingEntity]
    emerging_authors: list[EmergingEntity]
    top_growing_themes: list[ThemeGrowth]
    window_from: int | None
    window_to: int | None
    audit: dict


def _emerging_history_filter(filt: PaperFilter) -> PaperFilter:
    return filt.model_copy(update={"year_from": None, "year_to": None})


def build_emerging_history_audit(session: Session, filt: PaperFilter) -> dict:
    """Audit the non-temporal paper set used to establish true first years."""
    history_filter = _emerging_history_filter(filt)
    audit = build_filter_audit(
        session,
        history_filter,
        algorithm="impact_emerging_history.v1",
        metric_definitions={
            "emerging_first_year": "Earliest publication year for an entity among papers in this non-temporal filter scope.",
        },
    )
    audit["purpose"] = (
        "Historical dependency used to determine institution and author first years; "
        "all selected filters except year_from/year_to remain active."
    )
    return audit


def _citation_baseline_filter(filt: PaperFilter) -> PaperFilter:
    """Keep evidence/classification scope while removing entity selection."""
    return filt.model_copy(
        update={
            "institution_ids": [],
            "countries": [],
            "partner_only": False,
            "ac_author_only": False,
            "search": None,
        }
    )


def _primary_citation_field(paper: Paper) -> str:
    fields = {
        str(value).strip()
        for values in (paper.research_tags or [], paper.sdl_tags or [])
        for value in values
        if str(value).strip()
    }
    if not fields:
        return "(no field)"
    return sorted(fields, key=lambda value: (value.casefold(), value))[0]


def _normalized_citation_impact(
    session: Session,
    filt: PaperFilter,
    selected_paper_ids: list[str],
) -> tuple[NormalizedCitationImpact, dict]:
    baseline_filter = _citation_baseline_filter(filt)
    baseline_audit = build_filter_audit(
        session,
        baseline_filter,
        algorithm="citation_field_year_baseline.v1",
        metric_definitions={
            "expected_citations": "Arithmetic mean of external citation snapshots for papers in the same publication year and deterministic primary field.",
            "paper_index": "External citation snapshot divided by the field-year expected citation count; zero-over-zero is neutral at 1.0.",
        },
    )
    baseline_papers = list(
        session.scalars(apply_filter(select(Paper), baseline_filter))
    )
    covered_baseline = [
        paper
        for paper in baseline_papers
        if paper.citation_count is not None and paper.year is not None
    ]
    baseline_counts: dict[tuple[int, str], list[int]] = defaultdict(list)
    for paper in covered_baseline:
        baseline_counts[(paper.year, _primary_citation_field(paper).casefold())].append(
            int(paper.citation_count)
        )
    expected = {
        key: sum(values) / len(values)
        for key, values in baseline_counts.items()
    }

    selected = [
        paper
        for paper in session.scalars(
            select(Paper).where(Paper.id.in_(selected_paper_ids))
        )
    ] if selected_paper_ids else []
    paper_indices: dict[str, float] = {}
    for paper in selected:
        if paper.citation_count is None or paper.year is None:
            continue
        expected_count = expected.get(
            (paper.year, _primary_citation_field(paper).casefold())
        )
        if expected_count is None:
            continue
        index = (
            float(paper.citation_count) / expected_count
            if expected_count > 0
            else 1.0
        )
        paper_indices[paper.id] = index

    institution_indices: dict[str, list[tuple[str, float]]] = defaultdict(list)
    if paper_indices:
        affiliation_rows = session.execute(
            select(
                PaperAuthor.paper_id,
                Institution.id,
                Institution.canonical_name,
            )
            .join(Author, Author.id == PaperAuthor.author_id)
            .join(Institution, Institution.id == Author.institution_id)
            .where(PaperAuthor.paper_id.in_(paper_indices))
        ).all()
        seen_affiliations: set[tuple[str, str]] = set()
        for paper_id, institution_id, institution_name in affiliation_rows:
            key = (paper_id, institution_id)
            if key in seen_affiliations:
                continue
            seen_affiliations.add(key)
            institution_indices[institution_id].append(
                (institution_name, paper_indices[paper_id])
            )
    by_institution = [
        InstitutionCitationIndex(
            institution_id=institution_id,
            institution_name=values[0][0],
            paper_count=len(values),
            normalized_index=round(
                sum(value for _name, value in values) / len(values), 3
            ),
        )
        for institution_id, values in institution_indices.items()
    ]
    by_institution.sort(
        key=lambda item: (
            -item.paper_count,
            -item.normalized_index,
            item.institution_name.casefold(),
            item.institution_id,
        )
    )

    covered_selected = [
        paper for paper in selected if paper.id in paper_indices
    ]
    timestamps = sorted(
        paper.citation_count_updated_at.isoformat()
        for paper in covered_selected
        if paper.citation_count_updated_at is not None
    )
    sources = Counter(
        paper.citation_count_source or "unknown"
        for paper in covered_selected
    )
    baseline_audit["snapshot_coverage"] = {
        "covered_papers": len(covered_baseline),
        "total_papers": len(baseline_papers),
        "covered_paper_set_sha256": paper_set_sha256(
            [paper.id for paper in covered_baseline]
        ),
        "paper_set_encoding": PAPER_SET_ENCODING,
    }
    normalized = NormalizedCitationImpact(
        metric_name="corpus_field_year_normalized_citation_index.v1",
        normalized_index=(
            round(sum(paper_indices.values()) / len(paper_indices), 3)
            if paper_indices
            else None
        ),
        covered_papers=len(covered_selected),
        total_papers=len(selected),
        coverage=(
            round(len(covered_selected) / len(selected), 4)
            if selected
            else 0.0
        ),
        snapshot_oldest_at=timestamps[0] if timestamps else None,
        snapshot_newest_at=timestamps[-1] if timestamps else None,
        source_breakdown=dict(sorted(sources.items())),
        by_institution=by_institution[:10],
    )
    return normalized, baseline_audit


def build_impact_report(session: Session, filt: PaperFilter) -> ImpactReport:
    """Build all impact metrics using lean SQL queries — no full Paper ORM objects."""
    audit = build_filter_audit(
        session,
        filt,
        algorithm="research_impact.v4",
        metric_definitions={
            "yoy_attributed": "Distinct filtered papers per publication year with a CORE_RELEVANT or RELATED_RELEVANT classification.",
            "yoy_by_label": "Distinct filtered papers per publication year and classification label.",
            "citation_impact": "Persisted citation edges from filtered papers, grouped by the citing paper's publication year.",
            "normalized_citation_impact": "Mean external-citation index per covered paper, normalized to the corresponding corpus field-year baseline; this is not a proprietary global FWCI.",
            "emerging_first_year": "Earliest publication year among papers satisfying the same filter with only year_from/year_to removed.",
            "emerging_paper_count": "Distinct filtered papers in the selected window contributed by the entity.",
            "theme_growth": "Distinct filtered papers containing the core topic in the earlier versus later half of the selected window.",
        },
    )
    history_audit = build_emerging_history_audit(session, filt)
    rows = _paper_rows(session, filt)  # (id, year, label, matched_topics)
    paper_ids = [row[0] for row in rows]
    normalized_citations, citation_baseline_audit = _normalized_citation_impact(
        session,
        filt,
        paper_ids,
    )
    audit["dependencies"] = {
        "emerging_history": history_audit,
        "citation_baseline": citation_baseline_audit,
    }
    if not rows:
        return ImpactReport(
            yoy_attributed=GrowthSeries(name="ac_attributed_papers", points=[]),
            yoy_by_label=[],
            citation_impact=GrowthSeries(name="corpus_citation_edges", points=[]),
            normalized_citation_impact=normalized_citations,
            emerging_institutions=[],
            emerging_authors=[],
            top_growing_themes=[],
            window_from=filt.year_from,
            window_to=filt.year_to,
            audit=audit,
        )

    current_paper_ids = set(paper_ids)
    year_by_id = {r[0]: r[1] for r in rows if r[1] is not None}
    history_filter = _emerging_history_filter(filt)
    history_paper_ids = [row[0] for row in _paper_rows(session, history_filter)]

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
        select(
            Paper.id,
            Paper.year,
            Institution.id,
            Institution.canonical_name,
            Institution.is_partner,
        )
        .join(PaperAuthor, PaperAuthor.paper_id == Paper.id)
        .join(Author, Author.id == PaperAuthor.author_id)
        .join(Institution, Institution.id == Author.institution_id)
        .where(Paper.id.in_(history_paper_ids), Paper.year.is_not(None))
    ).all()
    inst_first: dict[str, tuple[int, str, bool]] = {}
    inst_window_papers: dict[str, set[str]] = defaultdict(set)
    for paper_id, yr, inst_id, inst_name, is_partner in inst_pa_rows:
        existing = inst_first.get(inst_id)
        if existing is None or yr < existing[0]:
            inst_first[inst_id] = (yr, inst_name, bool(is_partner))
        if paper_id in current_paper_ids:
            inst_window_papers[inst_id].add(paper_id)
    wf, wt = filt.year_from, filt.year_to
    emerging_institutions = sorted(
        [
            EmergingEntity(entity_type="institution", id=iid, label=lbl, first_year=yr,
                           paper_count=len(inst_window_papers[iid]), is_partner=isp)
            for iid, (yr, lbl, isp) in inst_first.items()
            if iid in inst_window_papers
            if (wf is None or yr >= wf) and (wt is None or yr <= wt)
        ],
        key=lambda entity: (
            -entity.paper_count,
            entity.first_year,
            entity.label.casefold(),
            entity.label,
            entity.id,
        ),
    )[:10]

    # --- Emerging authors ---
    auth_pa_rows = session.execute(
        select(Paper.id, Paper.year, Author.id, Author.canonical_name)
        .join(PaperAuthor, PaperAuthor.paper_id == Paper.id)
        .join(Author, Author.id == PaperAuthor.author_id)
        .where(Paper.id.in_(history_paper_ids), Paper.year.is_not(None))
    ).all()
    auth_first: dict[str, tuple[int, str]] = {}
    auth_window_papers: dict[str, set[str]] = defaultdict(set)
    for paper_id, yr, aid, aname in auth_pa_rows:
        existing = auth_first.get(aid)
        if existing is None or yr < existing[0]:
            auth_first[aid] = (yr, aname)
        if paper_id in current_paper_ids:
            auth_window_papers[aid].add(paper_id)
    emerging_authors = sorted(
        [
            EmergingEntity(entity_type="author", id=aid, label=lbl, first_year=yr,
                           paper_count=len(auth_window_papers[aid]))
            for aid, (yr, lbl) in auth_first.items()
            if aid in auth_window_papers
            if (wf is None or yr >= wf) and (wt is None or yr <= wt)
        ],
        key=lambda entity: (
            -entity.paper_count,
            entity.first_year,
            entity.label.casefold(),
            entity.label,
            entity.id,
        ),
    )[:10]

    # --- Top growing themes ---
    all_years = [r[1] for r in rows if r[1] is not None]
    tw_from = wf if wf is not None else (min(all_years) if all_years else None)
    tw_to = wt if wt is not None else (max(all_years) if all_years else None)
    top_growing_themes: list[ThemeGrowth] = []
    if tw_from is not None and tw_to is not None and tw_to > tw_from:
        midpoint = (tw_from + tw_to) // 2
        before: Counter[str] = Counter()
        after: Counter[str] = Counter()
        topic_aliases: dict[str, set[str]] = defaultdict(set)
        for _, year, _, matched_topics in rows:
            if year is None or not (tw_from <= year <= tw_to):
                continue
            paper_topics: set[str] = set()
            for tm in (matched_topics or []):
                if not tm.get("is_core") or (tm.get("score") or 0) < 0.3:
                    continue
                topic_id = tm.get("topic_id")
                if not topic_id:
                    continue
                paper_topics.add(topic_id)
                topic_aliases.setdefault(topic_id, set())
                topic_name = tm.get("name")
                if topic_name:
                    topic_aliases[topic_id].add(str(topic_name))
            for topic_id in paper_topics:
                if year <= midpoint:
                    before[topic_id] += 1
                else:
                    after[topic_id] += 1
        topic_names = canonical_topic_names(session, topic_aliases)
        theme_list = []
        for topic_id in sorted(set(before) | set(after)):
            b, a = before[topic_id], after[topic_id]
            if a + b == 0:
                continue
            dp = float("inf") if b == 0 else round((a - b) / b * 100.0, 1)
            theme_list.append(
                ThemeGrowth(
                    topic_id=topic_id,
                    name=topic_names.get(topic_id, topic_id),
                    value_now=a,
                    value_then=b,
                    delta_pct=dp,
                )
            )
        theme_list.sort(
            key=lambda theme: (
                0 if theme.delta_pct == float("inf") else 1,
                -(theme.value_now + theme.value_then),
                -theme.delta_pct if theme.delta_pct != float("inf") else 0.0,
                theme.topic_id,
            )
        )
        top_growing_themes = theme_list[:10]

    return ImpactReport(
        yoy_attributed=yoy_attributed,
        yoy_by_label=yoy_by_label,
        citation_impact=citation_impact,
        normalized_citation_impact=normalized_citations,
        emerging_institutions=emerging_institutions,
        emerging_authors=emerging_authors,
        top_growing_themes=top_growing_themes,
        window_from=filt.year_from,
        window_to=filt.year_to,
        audit=audit,
    )
