from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Paper
from app.schemas import (
    AnalyticsOverviewOut,
    DriftEventOut,
    DriftReportOut,
    EmergingEntityOut,
    GraphEdgeOut,
    GraphGroupOut,
    GraphNodeOut,
    GrowthSeriesOut,
    ImpactReportOut,
    InstitutionEdgeOut,
    InstitutionNetworkOut,
    InstitutionNodeOut,
    MetricTripleOut,
    MissedPaperGroupOut,
    MultiGraphPayloadOut,
    ReportOut,
    ReportRequest,
    ReportSectionOut,
    SankeyLinkOut,
    SankeyNodeOut,
    SankeyOut,
    ThemeGrowthOut,
    TimelineOut,
    TimelineSeriesOut,
    TopicShareOut,
    YearMetricOut,
    YearTopicsOut,
)
from app.services.analytics_service import (
    build_impact_report,
    institution_network,
    institution_topic_label_sankey,
    label_breakdown,
    topic_over_time,
)
from app.services.drift_service import build_drift_report
from app.services.evidence_gap_service import build_evidence_gap_report
from app.services.filter_spec import PaperFilter, apply_filter, paper_filter_query
from app.services.missed_papers_service import build_missed_paper_groups
from app.services.multi_graph import MultiGraphFilter, build_multi_graph
from app.services.reporting_service import build_report

router = APIRouter(prefix="/analytics", tags=["analytics"])


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
    min_edge_weight: float = Query(default=1.0, ge=0.0),
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
    spec = MultiGraphFilter(
        paper_filter=filt,
        node_types=node_types,
        edge_types=edge_types,
        group_by=group_by,
        min_edge_weight=min_edge_weight,
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
    )


@router.get("/geographic")
def geographic_endpoint(
    filt: PaperFilter = Depends(paper_filter_query),
    session: Session = Depends(get_session),
) -> dict:
    """Country-level collaboration map. Returns:
      * country aggregate: paper count, partner institutions
      * arcs: AC-partner ↔ other-country collaboration weights
    """
    from app.services.geographic_service import build_geographic_payload

    payload = build_geographic_payload(session, filt)
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


@router.get("/overview", response_model=AnalyticsOverviewOut)
def overview(
    filt: PaperFilter = Depends(paper_filter_query),
    session: Session = Depends(get_session),
) -> AnalyticsOverviewOut:
    papers = list(session.execute(apply_filter(select(Paper), filt)).scalars())
    breakdown = label_breakdown(session, filt)
    years = sorted({p.year for p in papers if p.year is not None})
    return AnalyticsOverviewOut(
        total_papers=len(papers),
        label_breakdown=breakdown,
        years=years,
    )


@router.get("/sankey", response_model=SankeyOut)
def sankey(
    filt: PaperFilter = Depends(paper_filter_query),
    session: Session = Depends(get_session),
) -> SankeyOut:
    data = institution_topic_label_sankey(session, filt)
    return SankeyOut(
        nodes=[SankeyNodeOut(id=n.id, name=n.name, layer=n.layer) for n in data.nodes],
        links=[
            SankeyLinkOut(source=l.source, target=l.target, value=l.value)
            for l in data.links
        ],
    )


@router.get("/timeline", response_model=TimelineOut)
def timeline(
    by: str = Query(default="topic", pattern="^(topic|label)$"),
    filt: PaperFilter = Depends(paper_filter_query),
    session: Session = Depends(get_session),
) -> TimelineOut:
    series_data = topic_over_time(session, filt, by=by)
    all_years: set[int] = set()
    for s in series_data:
        for year, _count in s.data:
            all_years.add(year)
    return TimelineOut(
        by=by,
        years=sorted(all_years),
        series=[TimelineSeriesOut(name=s.name, data=s.data) for s in series_data],
    )


@router.get("/institution-network", response_model=InstitutionNetworkOut)
def institution_network_endpoint(
    min_papers: int = Query(default=1, ge=1),
    filt: PaperFilter = Depends(paper_filter_query),
    session: Session = Depends(get_session),
) -> InstitutionNetworkOut:
    nodes, edges = institution_network(session, filt, min_papers=min_papers)
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
                source=e.source, target=e.target, weight=e.weight, papers=e.papers
            )
            for e in edges
        ],
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
    )


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


@router.post("/report", response_model=ReportOut)
def report(
    payload: ReportRequest = ReportRequest(),
    filt: PaperFilter = Depends(paper_filter_query),
    session: Session = Depends(get_session),
) -> ReportOut:
    result = build_report(
        session,
        filt,
        sections=payload.sections,
        backend=payload.backend,
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
