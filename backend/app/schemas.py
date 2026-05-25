"""Pydantic schemas exposed by the REST API."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MatchedPerson(BaseModel):
    person_id: str | None = None
    name: str
    match_type: str
    score: float
    institution: str | None = None


class MatchedInstitution(BaseModel):
    institution_id: str | None = None
    canonical_name: str
    is_partner: bool
    score: float
    matched_text: str | None = None


class MatchedTopic(BaseModel):
    topic_id: str
    name: str
    is_core: bool
    score: float
    hits: list[str] = Field(default_factory=list)


class FulltextEvidenceOut(BaseModel):
    id: str
    chunk_id: str | None = None
    evidence_type: str
    evidence_source: str
    evidence_text: str
    score: float


class SecondDegreePathOut(BaseModel):
    via_author_id: str
    via_author_name: str
    ac_author_id: str
    ac_author_name: str
    shared_papers: list[str] = Field(default_factory=list)
    strength: float


class CitationSignalOut(BaseModel):
    cited_ac_core_id: str
    cited_ac_core_title: str
    cited_doi: str | None = None


class GraphSignalsOut(BaseModel):
    network_score: float = 0.0
    citation_score: float = 0.0
    second_degree_paths: list[SecondDegreePathOut] = Field(default_factory=list)
    citation_signals: list[CitationSignalOut] = Field(default_factory=list)
    cites_corpus: list[str] = Field(default_factory=list)


class ClassificationOut(BaseModel):
    label: str
    confidence: float
    author_score: float
    institution_score: float
    topic_score: float
    network_score: float
    fulltext_evidence_score: float = 0.0
    citation_score: float = 0.0
    matched_people: list[MatchedPerson] = Field(default_factory=list)
    matched_institutions: list[MatchedInstitution] = Field(default_factory=list)
    matched_topics: list[MatchedTopic] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    model_version: str
    created_at: datetime
    fulltext_evidence: list[FulltextEvidenceOut] = Field(default_factory=list)
    graph_signals: GraphSignalsOut | None = None


class HumanReviewIn(BaseModel):
    human_label: str
    corrected_topics: list[str] | None = None
    corrected_people: list[str] | None = None
    reviewer: str | None = None
    notes: str | None = None


class HumanReviewOut(HumanReviewIn):
    paper_id: str
    created_at: datetime


class PaperAuthorOut(BaseModel):
    name: str
    order: int
    affiliation: str | None = None


class PaperOut(BaseModel):
    id: str
    title: str
    abstract: str | None = None
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    keywords: list[str] | None = None
    full_text_available: bool = False
    provenance: str = "csv"
    authors: list[PaperAuthorOut] = Field(default_factory=list)
    classification: ClassificationOut | None = None
    review: HumanReviewOut | None = None


class ChunkOut(BaseModel):
    chunk_id: str
    paper_id: str
    section_type: str
    section_title: str | None = None
    text: str
    token_count: int
    score: float | None = None
    bm25_score: float | None = None
    cosine_score: float | None = None


class RetrieveRequest(BaseModel):
    query: str
    top_k: int = 10
    alpha: float = 0.5
    paper_ids: list[str] | None = None
    section_types: list[str] | None = None
    year_from: int | None = None
    year_to: int | None = None


class PropositionOut(BaseModel):
    id: str
    paper_id: str
    predicate: str
    object_value: str
    object_key: str | None = None
    claim_text: str
    confidence: float
    source_section: str | None = None
    source_chunk_id: str | None = None
    extra: dict | None = None


class ParseBackendStatusOut(BaseModel):
    grobid_url: str
    grobid_reachable: bool
    pymupdf_available: bool
    contextual_chunking: bool
    embedding_backend: str
    reranker_backend: str


class DiscoveryTriggerOut(BaseModel):
    strategy: str
    source: str
    detail: str
    weight: float


class DiscoveryCandidateOut(BaseModel):
    id: str
    external_id: str
    doi: str | None = None
    title: str
    abstract: str | None = None
    year: int | None = None
    venue: str | None = None
    authors: list[dict] = Field(default_factory=list)
    affiliations: list[str] = Field(default_factory=list)
    source: str
    triggers: list[DiscoveryTriggerOut] = Field(default_factory=list)
    confidence: float
    auto_eligible: bool
    status: str
    reviewer: str | None = None
    review_notes: str | None = None
    resulting_paper_id: str | None = None
    created_at: datetime
    reviewed_at: datetime | None = None


class DiscoveryRunRequest(BaseModel):
    strategies: list[str] | None = None
    max_candidates: int | None = None


class DiscoveryRunResult(BaseModel):
    candidates_seen: int
    auto_ingested: int
    queued: int
    skipped_already_in_corpus: int
    by_strategy: dict[str, int]


class DiscoveryReviewIn(BaseModel):
    reviewer: str | None = None
    notes: str | None = None


# v0.6 — research intelligence


class YearMetricOut(BaseModel):
    year: int
    value: int


class GrowthSeriesOut(BaseModel):
    name: str
    points: list[YearMetricOut] = Field(default_factory=list)


class EmergingEntityOut(BaseModel):
    entity_type: str
    id: str
    label: str
    first_year: int
    paper_count: int
    is_partner: bool | None = None


class ThemeGrowthOut(BaseModel):
    topic_id: str
    name: str
    value_now: int
    value_then: int
    delta_pct: float | str  # "inf" -> "new"


class ImpactReportOut(BaseModel):
    yoy_attributed: GrowthSeriesOut
    yoy_by_label: list[GrowthSeriesOut] = Field(default_factory=list)
    citation_impact: GrowthSeriesOut
    emerging_institutions: list[EmergingEntityOut] = Field(default_factory=list)
    emerging_authors: list[EmergingEntityOut] = Field(default_factory=list)
    top_growing_themes: list[ThemeGrowthOut] = Field(default_factory=list)
    window_from: int | None = None
    window_to: int | None = None


class TopicShareOut(BaseModel):
    topic_id: str
    name: str
    share: float
    paper_count: int


class YearTopicsOut(BaseModel):
    year: int
    total_papers: int
    top_topics: list[TopicShareOut] = Field(default_factory=list)


class DriftEventOut(BaseModel):
    from_year: int
    to_year: int
    cosine_similarity: float
    new_topics: list[str] = Field(default_factory=list)
    faded_topics: list[str] = Field(default_factory=list)


class DriftReportOut(BaseModel):
    per_year: list[YearTopicsOut] = Field(default_factory=list)
    drift_events: list[DriftEventOut] = Field(default_factory=list)
    drift_threshold: float


class MissedPaperGroupOut(BaseModel):
    key: str
    label: str
    description: str
    candidate_ids: list[str] = Field(default_factory=list)


class MetricTripleOut(BaseModel):
    key: str
    label: str
    value: Any
    source_link: str


class ReportSectionOut(BaseModel):
    key: str
    title: str
    prose: str
    metrics: list[MetricTripleOut] = Field(default_factory=list)


class ReportOut(BaseModel):
    period_label: str
    sections: list[ReportSectionOut] = Field(default_factory=list)
    generated_at: datetime
    backend: str


class ReportRequest(BaseModel):
    sections: list[str] | None = None
    backend: str | None = None  # "template" | "anthropic"


# v0.7 — multi-graph explorer


class GraphNodeOut(BaseModel):
    id: str
    type: str
    label: str
    group: str | None = None
    metadata: dict = Field(default_factory=dict)


class GraphEdgeOut(BaseModel):
    source: str
    target: str
    type: str
    weight: float = 1.0
    metadata: dict = Field(default_factory=dict)


class GraphGroupOut(BaseModel):
    id: str
    label: str
    color: str
    node_count: int


class MultiGraphPayloadOut(BaseModel):
    nodes: list[GraphNodeOut] = Field(default_factory=list)
    edges: list[GraphEdgeOut] = Field(default_factory=list)
    groups: list[GraphGroupOut] = Field(default_factory=list)
    available_node_types: list[str] = Field(default_factory=list)
    available_edge_types: list[str] = Field(default_factory=list)
    available_group_keys: list[str] = Field(default_factory=list)


class SankeyNodeOut(BaseModel):
    id: str
    name: str
    layer: str


class SankeyLinkOut(BaseModel):
    source: str
    target: str
    value: int


class SankeyOut(BaseModel):
    nodes: list[SankeyNodeOut] = Field(default_factory=list)
    links: list[SankeyLinkOut] = Field(default_factory=list)


class TimelineSeriesOut(BaseModel):
    name: str
    data: list[tuple[int, int]]  # (year, count)


class TimelineOut(BaseModel):
    by: str
    years: list[int]
    series: list[TimelineSeriesOut]


class InstitutionNodeOut(BaseModel):
    id: str
    label: str
    is_partner: bool
    country: str | None = None
    paper_count: int


class InstitutionEdgeOut(BaseModel):
    source: str
    target: str
    weight: int
    papers: list[str]
    normalized_weight: float = 0.0
    involves_partner: bool = False


class InstitutionNetworkOut(BaseModel):
    nodes: list[InstitutionNodeOut] = Field(default_factory=list)
    edges: list[InstitutionEdgeOut] = Field(default_factory=list)


class AnalyticsOverviewOut(BaseModel):
    total_papers: int
    label_breakdown: dict[str, int]
    years: list[int]


class GraphExplanationOut(BaseModel):
    paper_id: str
    summary: str
    direct_ac_authors: list[str] = Field(default_factory=list)
    second_degree_paths: list["SecondDegreePathOut"] = Field(default_factory=list)
    citation_signals: list["CitationSignalOut"] = Field(default_factory=list)
    cites_corpus: list[str] = Field(default_factory=list)
    cited_by_corpus: list[str] = Field(default_factory=list)


class EvalMetric(BaseModel):
    label: str
    precision: float
    recall: float
    f1: float
    support: int


class EvalReport(BaseModel):
    per_label: list[EvalMetric]
    macro_precision: float
    macro_recall: float
    macro_f1: float
    accuracy: float
    confusion: dict[str, dict[str, int]]
    evidence_recall_at_k: float | None = None
    k: int = 5
    n_evaluated: int


class NetworkNode(BaseModel):
    id: str
    label: str
    is_ac_member: bool
    institution: str | None = None
    paper_count: int


class NetworkEdge(BaseModel):
    source: str
    target: str
    weight: int
    papers: list[str]
    normalized_weight: float = 0.0
    involves_ac: bool = False
    is_ac_ac: bool = False


class NetworkOut(BaseModel):
    nodes: list[NetworkNode]
    edges: list[NetworkEdge]


class PipelineStats(BaseModel):
    papers: int
    authors: int
    institutions: int
    topics: int
    classifications: dict[str, int]
    last_run_at: datetime | None = None
