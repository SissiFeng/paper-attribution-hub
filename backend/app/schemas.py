"""Pydantic schemas exposed by the REST API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.attribution_evidence_contract import (
    AttributionCentrality,
    AttributionMetadataStatus,
    AttributionPolarity,
)


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


class PaperEntityOut(BaseModel):
    id: str
    entity_type: str
    name: str
    normalized_name: str
    evidence_chunk_id: str | None = None
    section: str | None = None
    confidence: float
    extractor: str
    stage: str | None = None
    usage_snippet: str | None = None


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
    bridge_score: float = 0.0
    cross_sdl_diversity: float = 0.0
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
    funding_signal: float = 0.0
    acknowledgement_signal: float = 0.0
    retrieval_signal: float = 0.0
    architecture_signal: float = 0.0
    sdl_relevance_label: str | None = None
    ac_attribution_label: str | None = None
    model_agreement_status: str | None = None
    disagreement_type: str | None = None
    classification_dimensions: dict[str, str] = Field(default_factory=dict)
    future_rule_update: str | None = None


class HumanReviewIn(BaseModel):
    human_label: str
    corrected_topics: list[str] | None = None
    corrected_people: list[str] | None = None
    reviewer: str | None = None
    notes: str | None = None
    disagreement_type: str | None = None
    rationale: str | None = None
    evidence: list[dict[str, Any]] | None = None
    future_rule_update: str | None = None


class HumanReviewOut(HumanReviewIn):
    paper_id: str
    created_at: datetime


class PaperAuthorOut(BaseModel):
    name: str
    order: int
    affiliation: str | None = None


class RagStatusOut(BaseModel):
    status: str
    ready: bool
    full_text_available: bool
    chunk_count: int = 0
    embedded_chunk_count: int = 0
    evidence_count: int = 0
    attribution_evidence_count: int = 0
    needs_action: str | None = None
    action_hint: str | None = None


class PaperOut(BaseModel):
    id: str
    title: str
    abstract: str | None = None
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    keywords: list[str] | None = None
    full_text_available: bool = False
    rag_status: RagStatusOut | None = None
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
    graph_score: float | None = None   # composite graph centrality boost applied


class PropositionHit(BaseModel):
    paper_id: str
    predicate: str
    object_value: str
    claim_text: str
    confidence: float
    source_section: str | None = None
    score: float


class RagEvidenceAssessment(BaseModel):
    query_type: str
    evidence_score: float
    source_precision: float
    missing_evidence: list[str] = Field(default_factory=list)
    should_retry: bool = False


class RagFeedbackIn(BaseModel):
    query: str
    rating: int = Field(ge=1, le=5)
    failure_type: str | None = None
    note: str | None = None
    answer_model: str | None = None
    source_chunk_ids: list[str] = Field(default_factory=list)
    source_paper_ids: list[str] = Field(default_factory=list)


class RagFeedbackOut(RagFeedbackIn):
    id: str
    created_at: datetime


class RagFeedbackReport(BaseModel):
    total_feedback: int
    average_rating: float | None = None
    low_rating_count: int = 0
    by_failure_type: dict[str, int] = Field(default_factory=dict)
    recent: list[RagFeedbackOut] = Field(default_factory=list)


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


class TransferLabOut(BaseModel):
    id: str
    name: str


class TransferFlowsOut(BaseModel):
    labs: list[TransferLabOut] = Field(default_factory=list)
    matrix: list[list[int]] = Field(default_factory=list)
    intra_lab: dict[str, int] = Field(default_factory=dict)
    total_cross_flows: int = 0


class AdoptionOut(BaseModel):
    lab: str
    first_year: int
    lag_years: int


class AdoptionLagOut(BaseModel):
    entity: str
    entity_type: str
    origin_lab: str
    origin_year: int
    adoptions: list[AdoptionOut] = Field(default_factory=list)


class FastSpreadingEntityOut(BaseModel):
    entity: str
    entity_type: str
    adopter_count: int
    avg_lag_years: float


class TransferSummaryOut(BaseModel):
    labs: int
    linked_papers: int
    entities_tracked: int
    cross_lab_entities: int
    median_adoption_lag_years: float | None = None
    fastest_spreading: list[FastSpreadingEntityOut] = Field(default_factory=list)


class KbEntityIndexOut(BaseModel):
    entity_type: str
    name: str
    paper_count: int
    lab_count: int
    first_year: int | None = None
    last_year: int | None = None


class KbEntityLabOut(BaseModel):
    lab_id: str
    lab_name: str
    first_year: int | None = None
    paper_count: int


class KbEntityPaperOut(BaseModel):
    id: str
    title: str
    year: int | None = None
    labs: list[str] = Field(default_factory=list)
    confidence: float
    stage: str | None = None
    usage_snippet: str | None = None


class KbYearCountOut(BaseModel):
    year: int
    paper_count: int


class KbEvidenceOut(BaseModel):
    paper_id: str
    paper_title: str
    text: str
    stage: str | None = None
    usage_snippet: str | None = None


class KbRelatedEntityOut(BaseModel):
    entity_type: str
    name: str


class KbSagEventOut(BaseModel):
    id: str
    event_type: str
    paper_id: str
    paper_title: str
    year: int | None = None
    labs: list[str] = Field(default_factory=list)
    entity_type: str
    entity: str
    stage: str | None = None
    source_chunk_id: str | None = None
    snippet: str
    related_entities: list[KbRelatedEntityOut] = Field(default_factory=list)


class KbEntityPageOut(BaseModel):
    entity: str
    entity_type: str
    labs: list[KbEntityLabOut] = Field(default_factory=list)
    papers: list[KbEntityPaperOut] = Field(default_factory=list)
    timeline: list[KbYearCountOut] = Field(default_factory=list)
    evidence: list[KbEvidenceOut] = Field(default_factory=list)
    adoption: AdoptionLagOut | None = None
    stages: dict[str, int] = Field(default_factory=dict)
    events: list[KbSagEventOut] = Field(default_factory=list)


class KbTopEntityOut(BaseModel):
    name: str
    paper_count: int


class KbTagCountOut(BaseModel):
    tag: str
    count: int


class KbCollaborationOut(BaseModel):
    lab_id: str
    name: str
    shared_papers: int


class KbLabProfileOut(BaseModel):
    id: str
    name: str
    institution: str
    pi_names: list[str] = Field(default_factory=list)
    domain_focus: str
    platform_stack: list[str] | None = None
    automation_level: str | None = None
    paper_count: int
    first_year: int | None = None
    last_year: int | None = None
    sdl_tag_histogram: list[KbTagCountOut] = Field(default_factory=list)
    top_entities: dict[str, list[KbTopEntityOut]] = Field(default_factory=dict)
    collaborations: list[KbCollaborationOut] = Field(default_factory=list)
    entities_unique_to_lab: int = 0


class KbSummaryOut(BaseModel):
    labs: int
    linked_papers: int
    entities_by_type: dict[str, int] = Field(default_factory=dict)
    cross_lab_entities: int


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


class AttributionTreeNodeOut(BaseModel):
    node_id: str
    parent_node_id: str | None = None
    node_type: Literal["root", "section", "source"]
    path: list[str]
    section_type: str | None = None
    title: str
    summary: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    source_section_id: str | None = None
    source_chunk_ids: list[str] = Field(default_factory=list)


class AttributionEvidencePathOut(BaseModel):
    generation_id: str
    path_id: str
    rank: int = Field(ge=1)
    node_id: str
    path: list[str]
    evidence_type: str
    polarity: AttributionPolarity
    centrality: AttributionCentrality
    quote: str
    page_start: int | None = None
    page_end: int | None = None
    source_chunk_ids: list[str] = Field(default_factory=list)
    raw_score: float
    weight: float
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    detector_type: str
    metadata_status: AttributionMetadataStatus


class AttributionEvidenceTreeOut(BaseModel):
    paper_id: str
    tree_version: str
    generation_mode: Literal["derived_ephemeral"]
    generation_id: str
    metadata_contract_version: str
    nodes: list[AttributionTreeNodeOut] = Field(default_factory=list)
    evidence_paths: list[AttributionEvidencePathOut] = Field(default_factory=list)
    evidence_review_recommended: bool = False
    evidence_review_reasons: list[str] = Field(default_factory=list)


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
    ppr_score: float = 0.0
    c_norm: float = 1.0
    cross_sdl_diversity: float = 0.0
    bridge_score: float = 0.0
    importance_score: float = 0.0
    importance_profile: str = "bridge_builders"
    importance_components: dict[str, dict[str, float]] = Field(default_factory=dict)
    importance_radar_axes: list[dict] = Field(default_factory=list)
    importance_explanation: str = ""
    importance_weights: dict[str, float] = Field(default_factory=dict)


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


# ─── Cross-SDL transfer studio ────────────────────────────────────────────────


class TransferTargetOut(BaseModel):
    id: str
    name: str
    description: str
    typical_signature: dict[str, Any] = Field(default_factory=dict)
    typical_constraints: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class TransferTkuOut(BaseModel):
    id: str
    paper_id: str
    paper_title: str
    paper_year: int | None = None
    source_domain: str
    problem_signature: dict[str, Any] = Field(default_factory=dict)
    method_core: dict[str, Any] = Field(default_factory=dict)


class TransferMatchOut(BaseModel):
    paper_id: str
    title: str
    year: int | None = None
    source_domain: str
    score: int
    score_breakdown: dict[str, Any] = Field(default_factory=dict)
    key_lesson: str | None = None


class TransferDesignRequest(BaseModel):
    target_id: str
    source_domain: str | None = None
    top_k: int = 6
    use_llm: bool = False


class TransferDesignOut(BaseModel):
    target: dict[str, Any]
    markdown: str
    mode: str  # "template" | "llm"
    matches: list[TransferMatchOut] = Field(default_factory=list)


class EvolutionaryTransferRequest(BaseModel):
    target_id: str
    source_domain: str | None = None
    source_pool: int = 24
    population_size: int = 12
    generations: int = 6
    genome_size: int = 3
    mutation_rate: float = 0.35
    seed: int = 7
    include_knowledge_json: bool = True


class EvolutionaryTransferOut(BaseModel):
    target: dict[str, Any]
    config: dict[str, Any]
    source_count: int
    accepted: bool
    best: dict[str, Any] | None = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class PipelineStats(BaseModel):
    papers: int
    authors: int
    institutions: int
    topics: int
    classifications: dict[str, int]
    last_run_at: datetime | None = None
