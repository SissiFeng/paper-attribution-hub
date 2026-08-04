from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Author, Institution, Paper, PaperAuthor, PaperClassification
from app.schemas import (
    AdoptionLagOut,
    AnalyticsOverviewOut,
    DriftEventOut,
    DriftReportOut,
    EmergingEntityOut,
    GraphEdgeOut,
    GraphGroupOut,
    GraphNodeOut,
    GrowthSeriesOut,
    ImpactReportOut,
    InstitutionCitationIndexOut,
    InstitutionEdgeOut,
    InstitutionNetworkOut,
    InstitutionNodeOut,
    MetricTripleOut,
    MissedPaperGroupOut,
    MultiGraphPayloadOut,
    NormalizedCitationImpactOut,
    ReportOut,
    ReportMetricEvidenceOut,
    ReportRequest,
    ReportSectionOut,
    SankeyLinkOut,
    SankeyNodeOut,
    SankeyOut,
    ThemeGrowthOut,
    TimelineOut,
    TimelineSeriesOut,
    TopicShareOut,
    TransferFlowsOut,
    TransferSummaryOut,
    YearMetricOut,
    YearTopicsOut,
)
from app.services.analytics_service import (
    build_emerging_history_audit,
    build_impact_report,
    institution_network,
    institution_topic_label_sankey,
    label_breakdown,
    topic_over_time,
)
from app.services.drift_service import build_drift_report
from app.services.duplicate_service import build_duplicate_report
from app.services.evidence_gap_service import build_evidence_gap_report
from app.services.knowledge_lint_service import build_knowledge_lint_report
from app.services.filter_spec import (
    PaperFilter,
    apply_filter,
    available_filter_options,
    build_filter_audit,
    paper_filter_query,
)
from app.services.missed_papers_service import build_missed_paper_groups
from app.services.multi_graph import (
    MultiGraphFilter,
    available_edge_types,
    available_group_keys,
    available_node_types,
    build_multi_graph,
)
from app.report_evidence_policy import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    ReportEvidencePolicy,
)
from app.services.reporting_service import (
    apply_report_evidence_policy,
    build_report,
    build_report_evidence_audit,
)
from app.services.transfer_service import (
    adoption_lags,
    lab_flow_matrix,
    transfer_summary,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/scope")
def analysis_scope(
    filt: PaperFilter = Depends(paper_filter_query),
    session: Session = Depends(get_session),
) -> dict:
    """Replayable description of the paper set selected by a shared filter."""
    return build_filter_audit(
        session,
        filt,
        algorithm="paper_filter.v1",
        metric_definitions={
            "included_papers": "Distinct persisted papers matching every active filter condition.",
            "classified_papers": "Included papers with a persisted classifier result.",
            "reviewed_papers": "Included papers with a persisted human-review record.",
            "fulltext_papers": "Included papers with locally available full-text evidence.",
        },
    )


@router.get("/filter-options")
def filter_options(session: Session = Depends(get_session)) -> dict:
    return available_filter_options(session)


@router.get("/multi-graph", response_model=MultiGraphPayloadOut)
def multi_graph_endpoint(
    node_types: list[str] = Query(
        default_factory=lambda: ["author", "institution", "paper", "topic"]
    ),
    edge_types: list[str] = Query(
        default_factory=lambda: [
            "coauthored",
            "affiliated_with",
            "belongs_to_topic",
            "cites_ac_core",
        ]
    ),
    group_by: str = Query(default="by_institution"),
    min_edge_weight: float = Query(default=0.3, ge=0.0),
    min_papers: int = Query(default=1, ge=1),
    min_degree: int = Query(default=0, ge=0),
    top_n: int | None = Query(default=None, ge=1, le=500),
    excluded_node_ids: list[str] = Query(default_factory=list),
    center_id: str | None = Query(default=None),
    hop_limit: int = Query(default=2, ge=1, le=4),
    similarity_min: float = Query(default=0.7, ge=0.0, le=1.0),
    similarity_top_k: int = Query(default=5, ge=1, le=50),
    filt: PaperFilter = Depends(paper_filter_query),
    session: Session = Depends(get_session),
) -> MultiGraphPayloadOut:
    """Unified multi-entity graph (v0.7 §1). Composes author + institution +
    paper + topic + method + funder + ac_core nodes with 10 edge types into
    one ECharts-renderable payload. Supports ego-graph mode by passing
    center_id."""
    node_types = list(dict.fromkeys(node_types))
    edge_types = list(dict.fromkeys(edge_types))
    invalid_node_types = sorted(set(node_types) - set(available_node_types()))
    invalid_edge_types = sorted(set(edge_types) - set(available_edge_types()))
    invalid_group = group_by not in available_group_keys()
    if len(excluded_node_ids) > 500 or any(
        len(node_id) > 500 for node_id in excluded_node_ids
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "excluded_node_ids accepts at most 500 IDs of at most "
                "500 characters"
            ),
        )
    if invalid_node_types or invalid_edge_types or invalid_group:
        raise HTTPException(
            status_code=422,
            detail={
                "invalid_node_types": invalid_node_types,
                "invalid_edge_types": invalid_edge_types,
                "invalid_group_by": group_by if invalid_group else None,
            },
        )
    spec = MultiGraphFilter(
        paper_filter=filt,
        node_types=node_types,
        edge_types=edge_types,
        group_by=group_by,
        min_edge_weight=min_edge_weight,
        min_papers=min_papers,
        min_degree=min_degree,
        top_n=top_n,
        excluded_node_ids=list(dict.fromkeys(excluded_node_ids)),
        center_id=center_id,
        hop_limit=hop_limit,
        similarity_min=similarity_min,
        similarity_top_k=similarity_top_k,
    )
    payload = build_multi_graph(session, spec)
    return MultiGraphPayloadOut(
        nodes=[
            GraphNodeOut(
                id=n.id, type=n.type, label=n.label, group=n.group, metadata=n.metadata
            )
            for n in payload.nodes
        ],
        edges=[
            GraphEdgeOut(
                source=e.source,
                target=e.target,
                type=e.type,
                weight=e.weight,
                metadata=e.metadata,
            )
            for e in payload.edges
        ],
        groups=[
            GraphGroupOut(
                id=g.id, label=g.label, color=g.color, node_count=g.node_count
            )
            for g in payload.groups
        ],
        available_node_types=payload.available_node_types,
        available_edge_types=payload.available_edge_types,
        available_group_keys=payload.available_group_keys,
        audit=payload.audit,
    )


@router.get("/geographic")
def geographic_endpoint(
    center_type: Literal["country", "institution"] | None = Query(default=None),
    center_id: str | None = Query(default=None, max_length=200),
    center_country: str | None = Query(default=None, max_length=200),
    filt: PaperFilter = Depends(paper_filter_query),
    session: Session = Depends(get_session),
) -> dict:
    """Audited geographic collaboration and center-growth projection.

    The default projection shows country pairs involving AC partners. Supplying
    a country or institution center returns all incident collaborations plus a
    year-resolved distinct-paper/partner growth series.
    """
    from app.services.geographic_service import (
        GeographicCenterError,
        build_geographic_payload,
    )

    try:
        payload = build_geographic_payload(
            session,
            filt,
            center_type=center_type,
            center_id=center_id,
            center_country=center_country,
        )
    except GeographicCenterError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return payload


@router.get("/people-grid")
def people_grid_endpoint(
    session: Session = Depends(get_session),
) -> dict:
    """Periodic-table view of AC members. Each cell carries the data needed
    to render an "element": symbol (2 letters from surname), atomic number
    (paper count), color group (top topic), institution, recent papers."""
    from app.services.people_grid_service import build_people_grid

    return build_people_grid(session)


@router.get("/evidence-gaps")
def evidence_gaps(
    session: Session = Depends(get_session),
) -> dict:
    """Surface papers whose classification appears confident but has gaps —
    missing funding/methods evidence, contradictory disqualifying rows, or
    low-confidence auto-ingests."""
    report = build_evidence_gap_report(session)
    return {
        "total_papers_scanned": report.total_papers_scanned,
        "buckets": [
            {
                "bucket": b.bucket,
                "label": b.label,
                "description": b.description,
                "count": b.count,
                "entries": [
                    {
                        "paper_id": e.paper_id,
                        "title": e.title,
                        "label": e.label,
                        "confidence": e.confidence,
                        "missing_types": e.missing_types,
                        "present_types": e.present_types,
                        "reason": e.reason,
                    }
                    for e in b.entries
                ],
            }
            for b in report.buckets
        ],
    }


@router.get("/lint-report")
def lint_report(
    session: Session = Depends(get_session),
) -> dict:
    """Knowledge-base lint report for website-ready attribution claims."""
    report = build_knowledge_lint_report(session)
    return {
        "total_papers_scanned": report.total_papers_scanned,
        "website_blockers": report.website_blockers,
        "reporting_warnings": report.reporting_warnings,
        "buckets": [
            {
                "bucket": b.bucket,
                "label": b.label,
                "description": b.description,
                "severity": b.severity,
                "count": b.count,
                "entries": [
                    {
                        "paper_id": e.paper_id,
                        "title": e.title,
                        "label": e.label,
                        "severity": e.severity,
                        "reason": e.reason,
                    }
                    for e in b.entries
                ],
            }
            for b in report.buckets
        ],
    }


@router.get("/duplicate-candidates")
def duplicate_candidates(
    session: Session = Depends(get_session),
) -> dict:
    """Group same-title / different-DOI candidates with canonical suggestions."""
    report = build_duplicate_report(session)
    return {
        "group_count": report["group_count"],
        "paper_count": report["paper_count"],
        "blocker_groups": report["blocker_groups"],
        "warning_groups": report["warning_groups"],
        "groups": [
            {
                "key": g.key,
                "title": g.title,
                "group_type": g.group_type,
                "severity": g.severity,
                "canonical_paper_id": g.canonical_paper_id,
                "reason": g.reason,
                "candidates": [
                    {
                        "paper_id": c.paper_id,
                        "title": c.title,
                        "doi": c.doi,
                        "year": c.year,
                        "provenance": c.provenance,
                        "label": c.label,
                        "is_preprint": c.is_preprint,
                        "score": c.score,
                    }
                    for c in g.candidates
                ],
            }
            for g in report["groups"]
        ],
    }


@router.get("/overview", response_model=AnalyticsOverviewOut)
def overview(
    filt: PaperFilter = Depends(paper_filter_query),
    session: Session = Depends(get_session),
) -> AnalyticsOverviewOut:
    id_subq = apply_filter(select(Paper.id, Paper.year), filt).subquery()
    total = session.scalar(select(func.count()).select_from(id_subq)) or 0
    years = sorted(
        r[0] for r in session.execute(
            select(id_subq.c.year.distinct()).where(id_subq.c.year.is_not(None))
        ).all()
    )
    breakdown = label_breakdown(session, filt)
    return AnalyticsOverviewOut(
        total_papers=total,
        label_breakdown=breakdown,
        years=years,
    )


# ---------------------------------------------------------------------------
# Network Growth Page endpoints (previously missing — 404)
# ---------------------------------------------------------------------------


@router.get("/network-growth")
def network_growth(
    filt: PaperFilter = Depends(paper_filter_query),
    session: Session = Depends(get_session),
) -> dict:
    """Yearly and cumulative growth of papers, authors, institutions, countries, collaborations."""
    id_subq = apply_filter(select(Paper.id, Paper.year), filt).where(Paper.year.is_not(None)).subquery()

    papers_by_year = dict(session.execute(
        select(id_subq.c.year, func.count()).group_by(id_subq.c.year)
    ).all())

    authors_by_year = dict(session.execute(
        select(id_subq.c.year, func.count(PaperAuthor.author_id.distinct()))
        .join(PaperAuthor, PaperAuthor.paper_id == id_subq.c.id)
        .group_by(id_subq.c.year)
    ).all())

    inst_by_year = dict(session.execute(
        select(id_subq.c.year, func.count(Author.institution_id.distinct()))
        .join(PaperAuthor, PaperAuthor.paper_id == id_subq.c.id)
        .join(Author, Author.id == PaperAuthor.author_id)
        .where(Author.institution_id.is_not(None))
        .group_by(id_subq.c.year)
    ).all())

    country_by_year = dict(session.execute(
        select(id_subq.c.year, func.count(Institution.country.distinct()))
        .join(PaperAuthor, PaperAuthor.paper_id == id_subq.c.id)
        .join(Author, Author.id == PaperAuthor.author_id)
        .join(Institution, Institution.id == Author.institution_id)
        .where(Institution.country.is_not(None))
        .group_by(id_subq.c.year)
    ).all())

    # Collaborations = papers with authors from >1 institution
    collab_rows = session.execute(
        select(id_subq.c.year, id_subq.c.id, func.count(Author.institution_id.distinct()).label("inst_count"))
        .join(PaperAuthor, PaperAuthor.paper_id == id_subq.c.id)
        .join(Author, Author.id == PaperAuthor.author_id)
        .where(Author.institution_id.is_not(None))
        .group_by(id_subq.c.year, id_subq.c.id)
        .having(func.count(Author.institution_id.distinct()) > 1)
    ).all()
    collab_by_year: dict[int, int] = {}
    for yr, _pid, _ in collab_rows:
        collab_by_year[yr] = collab_by_year.get(yr, 0) + 1

    author_year_rows = session.execute(
        select(id_subq.c.year, PaperAuthor.author_id)
        .join(PaperAuthor, PaperAuthor.paper_id == id_subq.c.id)
    ).all()
    inst_year_rows = session.execute(
        select(id_subq.c.year, Author.institution_id)
        .join(PaperAuthor, PaperAuthor.paper_id == id_subq.c.id)
        .join(Author, Author.id == PaperAuthor.author_id)
        .where(Author.institution_id.is_not(None))
    ).all()
    country_year_rows = session.execute(
        select(id_subq.c.year, Institution.country)
        .join(PaperAuthor, PaperAuthor.paper_id == id_subq.c.id)
        .join(Author, Author.id == PaperAuthor.author_id)
        .join(Institution, Institution.id == Author.institution_id)
        .where(Institution.country.is_not(None))
    ).all()

    years = sorted(papers_by_year)
    yearly = [
        {
            "year": y,
            "papers": papers_by_year.get(y, 0),
            "authors": authors_by_year.get(y, 0),
            "institutions": inst_by_year.get(y, 0),
            "countries": country_by_year.get(y, 0),
            "collaborations": collab_by_year.get(y, 0),
        }
        for y in years
    ]
    cumulative = []
    cumulative_papers = 0
    cumulative_collaborations = 0
    seen_authors: set[str] = set()
    seen_institutions: set[str] = set()
    seen_countries: set[str] = set()
    for pt in yearly:
        year = pt["year"]
        cumulative_papers += pt["papers"]
        cumulative_collaborations += pt["collaborations"]
        seen_authors.update(aid for yr, aid in author_year_rows if yr <= year)
        seen_institutions.update(inst_id for yr, inst_id in inst_year_rows if yr <= year)
        seen_countries.update(country for yr, country in country_year_rows if yr <= year)
        cumulative.append(
            {
                "year": year,
                "papers": cumulative_papers,
                "authors": len(seen_authors),
                "institutions": len(seen_institutions),
                "countries": len(seen_countries),
                "collaborations": cumulative_collaborations,
            }
        )
    return {"yearly": yearly, "cumulative": cumulative}


@router.get("/topic-stream")
def topic_stream(
    filt: PaperFilter = Depends(paper_filter_query),
    session: Session = Depends(get_session),
) -> dict:
    """Topic frequency by year for ECharts themeRiver — returns {data, topics}."""
    id_subq = apply_filter(
        select(Paper.id, Paper.year).where(Paper.year.is_not(None)), filt
    ).subquery()
    rows = session.execute(
        select(id_subq.c.year, PaperClassification.matched_topics)
        .outerjoin(PaperClassification, PaperClassification.paper_id == id_subq.c.id)
    ).all()

    from collections import Counter, defaultdict
    counts: dict[int, Counter] = defaultdict(Counter)
    for year, matched_topics in rows:
        for tm in (matched_topics or []):
            name = tm.get("name")
            if name and (tm.get("score") or 0) >= 0.3:
                counts[year][name] += 1

    all_topics = sorted({t for yr_counts in counts.values() for t in yr_counts})
    data = [
        [str(year), count, topic]
        for year, yr_counts in sorted(counts.items())
        for topic, count in yr_counts.items()
    ]
    return {"data": data, "topics": all_topics}


@router.get("/inst-topic-heatmap")
def inst_topic_heatmap(
    year: int | None = Query(default=None),
    filt: PaperFilter = Depends(paper_filter_query),
    session: Session = Depends(get_session),
) -> dict:
    """Institution × SDL-topic paper-count heatmap.

    Middle axis uses sdl_tags (e.g. 'SDL 0 - AI & Automation') since
    matched_topics is populated only after topic-classification runs.
    """
    from collections import Counter

    # Build filtered paper set with sdl_tags + institution in one query.
    stmt = (
        select(Institution.canonical_name, Paper.sdl_tags)
        .select_from(Paper)
        .join(PaperAuthor, PaperAuthor.paper_id == Paper.id)
        .join(Author, Author.id == PaperAuthor.author_id)
        .join(Institution, Institution.id == Author.institution_id)
        .where(Author.institution_id.is_not(None))
    )
    if year is not None:
        stmt = stmt.where(Paper.year == year)
    else:
        # Apply normal filter (year_from/year_to/labels etc.)
        id_subq = apply_filter(select(Paper.id), filt).subquery()
        stmt = stmt.where(Paper.id.in_(select(id_subq.c.id)))

    rows = session.execute(stmt).all()

    cell_counts: Counter = Counter()
    for inst_name, sdl_tags in rows:
        inst_short = (inst_name or "")[:40]
        for tag in (sdl_tags or []):
            tag = str(tag).strip()
            if tag:
                cell_counts[(inst_short, tag)] += 1

    if not cell_counts:
        return {"institutions": [], "topics": [], "cells": [], "year": year}

    # Top-30 institutions and top-20 SDL tags by total count
    inst_totals: Counter = Counter()
    topic_totals: Counter = Counter()
    for (inst, topic), cnt in cell_counts.items():
        inst_totals[inst] += cnt
        topic_totals[topic] += cnt
    institutions = [i for i, _ in inst_totals.most_common(30)]
    topics = [t for t, _ in topic_totals.most_common(20)]
    inst_set, topic_set = set(institutions), set(topics)
    cells = [
        {"institution": inst, "topic": topic, "count": count}
        for (inst, topic), count in cell_counts.items()
        if inst in inst_set and topic in topic_set
    ]
    return {"institutions": institutions, "topics": topics, "cells": cells, "year": year}


@router.get("/hub-score")
def hub_score(
    institution: str = Query(default="uoft"),
    session: Session = Depends(get_session),
) -> dict:
    """Yearly hub metrics for a given institution (degree/betweenness centrality + partner/intl collab counts)."""
    import networkx as nx

    # Find institution by partial name match
    inst_row = session.execute(
        select(Institution).where(
            func.lower(Institution.canonical_name).contains(institution.lower())
        ).limit(1)
    ).scalar()
    inst_label = inst_row.canonical_name if inst_row else institution
    inst_id = inst_row.id if inst_row else None

    # Per-year collaboration data
    rows = session.execute(
        select(Paper.year, Institution.id, Institution.is_partner, Institution.country)
        .join(PaperAuthor, PaperAuthor.paper_id == Paper.id)
        .join(Author, Author.id == PaperAuthor.author_id)
        .join(Institution, Institution.id == Author.institution_id)
        .where(Paper.year.is_not(None))
    ).all()

    from collections import defaultdict
    # year → set of (paper_id, institution_id) pairs
    year_paper_insts: dict[int, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for yr, iid, _is_partner, _country in rows:
        year_paper_insts[yr]  # ensure key exists

    rows2 = session.execute(
        select(Paper.year, Paper.id, Institution.id, Institution.is_partner, Institution.country)
        .join(PaperAuthor, PaperAuthor.paper_id == Paper.id)
        .join(Author, Author.id == PaperAuthor.author_id)
        .join(Institution, Institution.id == Author.institution_id)
        .where(Paper.year.is_not(None))
    ).all()

    year_data: dict[int, dict] = {}
    for yr, pid, iid, is_partner, country in rows2:
        if yr not in year_data:
            year_data[yr] = {"paper_insts": defaultdict(set)}
        year_data[yr]["paper_insts"][pid].add((iid, bool(is_partner), country))

    result = []
    for yr in sorted(year_data):
        paper_insts = year_data[yr]["paper_insts"]
        # Build collaboration graph for this year
        g = nx.Graph()
        for pid, inst_set in paper_insts.items():
            inst_list = list(inst_set)
            for i, (iid, _, _) in enumerate(inst_list):
                g.add_node(iid)
                for (jid, _, _) in inst_list[i + 1:]:
                    if g.has_edge(iid, jid):
                        g[iid][jid]["weight"] += 1
                    else:
                        g.add_edge(iid, jid, weight=1)
        if inst_id not in g:
            continue

        deg_cent = nx.degree_centrality(g).get(inst_id, 0.0)
        try:
            bet_cent = nx.betweenness_centrality(g, normalized=True).get(inst_id, 0.0)
        except Exception:
            bet_cent = 0.0

        # Partner and international collab counts
        neighbors = set(g.neighbors(inst_id))
        inst_meta = {iid: (is_p, cty) for pid, inst_set in paper_insts.items()
                     for (iid, is_p, cty) in inst_set}
        target_country = (inst_meta.get(inst_id) or (None, None))[1]
        partner_count = sum(1 for n in neighbors if inst_meta.get(n, (False, None))[0])
        intl_count = sum(1 for n in neighbors
                         if inst_meta.get(n, (None, None))[1] not in (None, target_country))

        hub_score_val = round(0.4 * deg_cent + 0.4 * bet_cent + 0.1 * min(partner_count / 10, 1.0) + 0.1 * min(intl_count / 10, 1.0), 4)
        result.append({
            "year": yr,
            "degree_centrality": round(deg_cent, 4),
            "betweenness_centrality": round(bet_cent, 4),
            "partner_count": partner_count,
            "intl_collab_count": intl_count,
            "hub_score": hub_score_val,
        })

    return {"institution": inst_label, "data": result}


@router.get("/sankey", response_model=SankeyOut)
def sankey(
    top_institutions: int = Query(default=100, ge=1, le=500),
    top_topics: int = Query(default=50, ge=1, le=200),
    filt: PaperFilter = Depends(paper_filter_query),
    session: Session = Depends(get_session),
) -> SankeyOut:
    data = institution_topic_label_sankey(session, filt,
                                          top_institutions=top_institutions,
                                          top_topics=top_topics)
    return SankeyOut(
        nodes=[SankeyNodeOut(id=n.id, name=n.name, layer=n.layer) for n in data.nodes],
        links=[
            SankeyLinkOut(
                source=link.source,
                target=link.target,
                value=link.value,
            )
            for link in data.links
        ],
        audit=build_filter_audit(
            session,
            filt,
            algorithm="institution_topic_label_sankey.v2",
            metric_definitions={
                "institution_topic_value": "Distinct filtered papers connected to the institution and topic.",
                "topic_label_value": "Distinct filtered papers connected to the topic and effective classification label.",
                "top_n_projection": "Institutions and topics are ranked by distinct-paper support before projection.",
            },
            projection={
                "top_institutions": top_institutions,
                "top_topics": top_topics,
                "layers": ["institution", "topic", "label"],
            },
        ),
    )


@router.get("/timeline", response_model=TimelineOut)
def timeline(
    by: str = Query(
        default="topic",
        pattern="^(topic|label|institution|country|field)$",
    ),
    top_n: int = Query(default=10, ge=1, le=100),
    filt: PaperFilter = Depends(paper_filter_query),
    session: Session = Depends(get_session),
) -> TimelineOut:
    series_data = topic_over_time(session, filt, by=by, top_n=top_n)
    all_years: set[int] = set()
    for s in series_data:
        for year, _count in s.data:
            all_years.add(year)
    return TimelineOut(
        by=by,
        top_n=top_n,
        years=sorted(all_years),
        series=[TimelineSeriesOut(name=s.name, data=s.data) for s in series_data],
        audit=build_filter_audit(
            session,
            filt,
            algorithm=f"timeline_distinct_papers_by_{by}.v2",
            metric_definitions={
                "series_value": (
                    "Distinct filtered papers in the year and grouping value; "
                    "one paper may appear in multiple institution, country, or topic series."
                ),
                "year": "Persisted publication year.",
            },
            projection={"by": by, "top_n": top_n},
        ),
    )


@router.get("/institution-network", response_model=InstitutionNetworkOut)
def institution_network_endpoint(
    min_papers: int = Query(default=1, ge=1),
    top_n: int = Query(default=50, ge=5, le=200),
    filt: PaperFilter = Depends(paper_filter_query),
    session: Session = Depends(get_session),
) -> InstitutionNetworkOut:
    nodes, edges = institution_network(session, filt, min_papers=min_papers, top_n=top_n)
    return InstitutionNetworkOut(
        nodes=[
            InstitutionNodeOut(
                id=n.id,
                label=n.label,
                is_partner=n.is_partner,
                country=n.country,
                paper_count=n.paper_count,
            )
            for n in nodes
        ],
        edges=[
            InstitutionEdgeOut(
                source=e.source,
                target=e.target,
                weight=e.weight,
                papers=e.papers,
                normalized_weight=e.normalized_weight,
                involves_partner=e.involves_partner,
            )
            for e in edges
        ],
        audit=build_filter_audit(
            session,
            filt,
            algorithm="institution_collaboration_network.v1",
            metric_definitions={
                "node_paper_count": "Distinct filtered papers attached to the institution.",
                "edge_weight": "Distinct filtered papers coauthored across the two institutions.",
                "normalized_weight": "Shared-paper count divided by the smaller institution paper count.",
            },
            projection={"min_papers": min_papers, "top_n": top_n},
        ),
    )


# ---------------------------------------------------------------------------
# v0.6: research intelligence
# ---------------------------------------------------------------------------


def _series_to_out(series) -> GrowthSeriesOut:
    return GrowthSeriesOut(
        name=series.name,
        points=[YearMetricOut(year=p.year, value=p.value) for p in series.points],
    )


@router.get("/impact", response_model=ImpactReportOut)
def impact(
    filt: PaperFilter = Depends(paper_filter_query),
    session: Session = Depends(get_session),
) -> ImpactReportOut:
    report = build_impact_report(session, filt)
    return ImpactReportOut(
        yoy_attributed=_series_to_out(report.yoy_attributed),
        yoy_by_label=[_series_to_out(s) for s in report.yoy_by_label],
        citation_impact=_series_to_out(report.citation_impact),
        normalized_citation_impact=NormalizedCitationImpactOut(
            metric_name=report.normalized_citation_impact.metric_name,
            normalized_index=report.normalized_citation_impact.normalized_index,
            covered_papers=report.normalized_citation_impact.covered_papers,
            total_papers=report.normalized_citation_impact.total_papers,
            coverage=report.normalized_citation_impact.coverage,
            snapshot_oldest_at=report.normalized_citation_impact.snapshot_oldest_at,
            snapshot_newest_at=report.normalized_citation_impact.snapshot_newest_at,
            source_breakdown=report.normalized_citation_impact.source_breakdown,
            by_institution=[
                InstitutionCitationIndexOut(
                    institution_id=item.institution_id,
                    institution_name=item.institution_name,
                    paper_count=item.paper_count,
                    normalized_index=item.normalized_index,
                )
                for item in report.normalized_citation_impact.by_institution
            ],
        ),
        emerging_institutions=[
            EmergingEntityOut(
                entity_type=e.entity_type,
                id=e.id,
                label=e.label,
                first_year=e.first_year,
                paper_count=e.paper_count,
                is_partner=e.is_partner,
            )
            for e in report.emerging_institutions
        ],
        emerging_authors=[
            EmergingEntityOut(
                entity_type=e.entity_type,
                id=e.id,
                label=e.label,
                first_year=e.first_year,
                paper_count=e.paper_count,
                is_partner=e.is_partner,
            )
            for e in report.emerging_authors
        ],
        top_growing_themes=[
            ThemeGrowthOut(
                topic_id=t.topic_id,
                name=t.name,
                value_now=t.value_now,
                value_then=t.value_then,
                delta_pct=("new" if t.delta_pct == float("inf") else t.delta_pct),
            )
            for t in report.top_growing_themes
        ],
        window_from=report.window_from,
        window_to=report.window_to,
        audit=report.audit,
    )


@router.get("/drift", response_model=DriftReportOut)
def drift(
    drift_threshold: float = Query(default=0.7, ge=0.0, le=1.0),
    top_n_per_year: int = Query(default=5, ge=1, le=20),
    filt: PaperFilter = Depends(paper_filter_query),
    session: Session = Depends(get_session),
) -> DriftReportOut:
    report = build_drift_report(
        session,
        filt,
        drift_threshold=drift_threshold,
        top_n_per_year=top_n_per_year,
    )
    return DriftReportOut(
        per_year=[
            YearTopicsOut(
                year=y.year,
                total_papers=y.total_papers,
                top_topics=[
                    TopicShareOut(
                        topic_id=t.topic_id,
                        name=t.name,
                        share=t.share,
                        paper_count=t.paper_count,
                    )
                    for t in y.top_topics
                ],
            )
            for y in report.per_year
        ],
        drift_events=[
            DriftEventOut(
                from_year=e.from_year,
                to_year=e.to_year,
                cosine_similarity=e.cosine_similarity,
                new_topics=e.new_topics,
                faded_topics=e.faded_topics,
            )
            for e in report.drift_events
        ],
        drift_threshold=report.drift_threshold,
        audit=report.audit,
    )


# ---------------------------------------------------------------------------
# Cross-SDL knowledge transfer
# ---------------------------------------------------------------------------


@router.get("/transfer/flows", response_model=TransferFlowsOut)
def transfer_flows(
    year_from: int | None = Query(default=None),
    year_to: int | None = Query(default=None),
    session: Session = Depends(get_session),
) -> TransferFlowsOut:
    """Lab×lab citation-flow matrix (self-flows reported separately)."""
    return TransferFlowsOut(
        **lab_flow_matrix(session, year_from=year_from, year_to=year_to)
    )


@router.get("/transfer/adoption", response_model=list[AdoptionLagOut])
def transfer_adoption(
    entity_type: str | None = Query(default=None),
    min_labs: int = Query(default=2, ge=2),
    session: Session = Depends(get_session),
) -> list[AdoptionLagOut]:
    """Entity adoption lags: origin lab + years until other labs picked it up."""
    return [
        AdoptionLagOut(**entry)
        for entry in adoption_lags(session, entity_type=entity_type, min_labs=min_labs)
    ]


@router.get("/transfer/summary", response_model=TransferSummaryOut)
def transfer_summary_endpoint(
    session: Session = Depends(get_session),
) -> TransferSummaryOut:
    """Headline knowledge-transfer numbers."""
    return TransferSummaryOut(**transfer_summary(session))


@router.get("/missed-papers", response_model=list[MissedPaperGroupOut])
def missed_papers(
    status: str = Query(default="queued"),
    limit_per_group: int = Query(default=25, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[MissedPaperGroupOut]:
    groups = build_missed_paper_groups(
        session, status=status, limit_per_group=limit_per_group
    )
    return [
        MissedPaperGroupOut(
            key=g.key,
            label=g.label,
            description=g.description,
            candidate_ids=g.candidate_ids,
        )
        for g in groups
    ]


@router.get("/report-metric", response_model=ReportMetricEvidenceOut)
def report_metric(
    metric_key: str = Query(min_length=1),
    report_evidence_mode: str | None = Query(default=None),
    report_evidence_confidence_threshold: float | None = Query(default=None, ge=0.0, le=1.0),
    report_evidence_sdl_judgements: list[str] = Query(default_factory=list),
    report_evidence_include_model_only: bool = Query(default=False),
    report_evidence_allow_needs_fulltext: bool = Query(default=False),
    report_evidence_allow_abstract_only: bool = Query(default=False),
    report_evidence_exclude_unreviewed_broad: bool = Query(default=True),
    report_entity: str | None = Query(default=None),
    filt: PaperFilter = Depends(paper_filter_query),
    session: Session = Depends(get_session),
) -> ReportMetricEvidenceOut:
    policy = ReportEvidencePolicy(
        mode=report_evidence_mode or "human_plus_probable",
        confidence_threshold=(
            report_evidence_confidence_threshold
            if report_evidence_confidence_threshold is not None
            else DEFAULT_CONFIDENCE_THRESHOLD
        ),
        sdl_judgements=report_evidence_sdl_judgements,
        include_model_only_separately=report_evidence_include_model_only,
        allow_needs_fulltext=report_evidence_allow_needs_fulltext,
        allow_abstract_only=report_evidence_allow_abstract_only,
        exclude_unreviewed_broad_retrieval=report_evidence_exclude_unreviewed_broad,
    )
    result = build_report(
        session,
        filt,
        backend="template",
        evidence_policy=policy,
        report_entity=report_entity,
    )
    metric = next(
        (
            candidate
            for section in result.sections
            for candidate in section.metrics
            if candidate.key == metric_key
        ),
        None,
    )
    if metric is None:
        raise HTTPException(status_code=404, detail="Report metric is unavailable")
    effective_filt = apply_report_evidence_policy(filt, policy)
    audit = build_report_evidence_audit(
        session, filt, effective_filt, policy
    )
    if report_entity and report_entity != "none":
        audit["report_entity"] = report_entity
    audit["projection"] = {"metric_key": metric_key}
    audit["algorithm"] = "report_metric_evidence.v1"
    audit["metric_definitions"] = {
        "metric_value": "Exact deterministic metric value used by the generated report prose.",
        "included_papers": "Distinct persisted papers matching the user filter after applying the report evidence policy.",
    }
    if metric_key.startswith("emerging."):
        audit["dependencies"] = {
            "emerging_history": build_emerging_history_audit(
                session, effective_filt
            )
        }
    return ReportMetricEvidenceOut(
        metric=MetricTripleOut(
            key=metric.key,
            label=metric.label,
            value=metric.value,
            source_link=metric.source_link,
        ),
        audit=audit,
    )


@router.post("/report", response_model=ReportOut)
def report(
    payload: ReportRequest = ReportRequest(),
    filt: PaperFilter = Depends(paper_filter_query),
    session: Session = Depends(get_session),
) -> ReportOut:
    policy = ReportEvidencePolicy(
        mode=payload.report_evidence_mode or "human_plus_probable",
        confidence_threshold=(
            payload.report_evidence_confidence_threshold
            if payload.report_evidence_confidence_threshold is not None
            else DEFAULT_CONFIDENCE_THRESHOLD
        ),
        sdl_judgements=payload.report_evidence_sdl_judgements,
        include_model_only_separately=payload.report_evidence_include_model_only,
        allow_needs_fulltext=payload.report_evidence_allow_needs_fulltext,
        allow_abstract_only=payload.report_evidence_allow_abstract_only,
        exclude_unreviewed_broad_retrieval=(
            payload.report_evidence_exclude_unreviewed_broad
        ),
    )
    result = build_report(
        session,
        filt,
        sections=payload.sections,
        backend=payload.backend,
        evidence_policy=policy,
        report_entity=payload.report_entity,
    )
    return ReportOut(
        period_label=result.period_label,
        sections=[
            ReportSectionOut(
                key=s.key,
                title=s.title,
                prose=s.prose,
                metrics=[
                    MetricTripleOut(
                        key=m.key,
                        label=m.label,
                        value=m.value,
                        source_link=m.source_link,
                    )
                    for m in s.metrics
                ],
            )
            for s in result.sections
        ],
        generated_at=result.generated_at,
        backend=result.backend,
    )
