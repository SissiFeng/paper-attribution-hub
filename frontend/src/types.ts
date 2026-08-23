export type RelevanceLabel =
  | "CORE_RELEVANT"
  | "RELATED_RELEVANT"
  | "SDL_FIELD_RELEVANT"
  | "ADJACENT"
  | "UNCERTAIN"
  | "EXCLUDE";

export interface MatchedPerson {
  person_id?: string;
  name: string;
  match_type: string;
  score: number;
  institution?: string | null;
}

export interface MatchedInstitution {
  institution_id?: string;
  canonical_name: string;
  is_partner: boolean;
  score: number;
  matched_text?: string | null;
}

export interface MatchedTopic {
  topic_id: string;
  name: string;
  is_core: boolean;
  score: number;
  hits: string[];
}

export interface FulltextEvidence {
  id: string;
  chunk_id: string | null;
  evidence_type: string;
  evidence_source: string;
  evidence_text: string;
  score: number;
}

export interface SecondDegreePath {
  via_author_id: string;
  via_author_name: string;
  ac_author_id: string;
  ac_author_name: string;
  shared_papers: string[];
  strength: number;
}

export interface CitationSignal {
  cited_ac_core_id: string;
  cited_ac_core_title: string;
  cited_doi: string | null;
}

export interface GraphSignals {
  network_score: number;
  citation_score: number;
  bridge_score?: number;
  cross_sdl_diversity?: number;
  second_degree_paths: SecondDegreePath[];
  citation_signals: CitationSignal[];
  cites_corpus: string[];
}

export interface Classification {
  label: RelevanceLabel;
  confidence: number;
  author_score: number;
  institution_score: number;
  topic_score: number;
  network_score: number;
  fulltext_evidence_score: number;
  citation_score: number;
  matched_people: MatchedPerson[];
  matched_institutions: MatchedInstitution[];
  matched_topics: MatchedTopic[];
  reasons: string[];
  model_version: string;
  created_at: string;
  fulltext_evidence: FulltextEvidence[];
  graph_signals: GraphSignals | null;
  funding_signal?: number;
  acknowledgement_signal?: number;
  retrieval_signal?: number;
  architecture_signal?: number;
  sdl_relevance_label?: string | null;
  ac_attribution_label?: string | null;
  model_agreement_status?: string | null;
  disagreement_type?: string | null;
  classification_dimensions?: Record<string, string>;
  future_rule_update?: string | null;
  screening_stage?: ScreeningStage | null;
  screening_route?: ScreeningRoute | null;
  screening_reason?: string | null;
}

export interface HumanReview {
  paper_id: string;
  human_label: string | null;
  sdl_judgement?: SdlJudgement | null;
  ac_relevance_judgement?: AcRelevanceJudgement | null;
  ai_for_science_judgement?: AiForScienceJudgement | null;
  review_status?: ReviewStatus | null;
  evidence_level?: EvidenceLevel | null;
  judgement_basis?: JudgementBasis | null;
  corrected_topics?: string[] | null;
  corrected_people?: string[] | null;
  reviewer?: string | null;
  notes?: string | null;
  disagreement_type?: string | null;
  rationale?: string | null;
  evidence?: Record<string, unknown>[] | null;
  future_rule_update?: string | null;
  created_at: string;
}

export interface PaperAuthor {
  name: string;
  order: number;
  affiliation?: string | null;
}

export interface RagStatus {
  status: string;
  ready: boolean;
  full_text_available: boolean;
  chunk_count: number;
  embedded_chunk_count: number;
  evidence_count: number;
  attribution_evidence_count: number;
  needs_action?: string | null;
  action_hint?: string | null;
}

export interface Paper {
  id: string;
  title: string;
  abstract?: string | null;
  year?: number | null;
  venue?: string | null;
  doi?: string | null;
  keywords?: string[] | null;
  full_text_available: boolean;
  rag_status?: RagStatus | null;
  provenance: string;
  source?: string;
  corpus_sources?: string[];
  authors: PaperAuthor[];
  classification?: Classification | null;
  review?: HumanReview | null;
}

export interface DiscoveryTrigger {
  strategy: string;
  source: string;
  detail: string;
  weight: number;
}

export interface DiscoveryCandidate {
  id: string;
  external_id: string;
  doi?: string | null;
  title: string;
  abstract?: string | null;
  year?: number | null;
  venue?: string | null;
  authors: { name: string }[];
  affiliations: string[];
  source: string;
  triggers: DiscoveryTrigger[];
  confidence: number;
  auto_eligible: boolean;
  status: "queued" | "approved" | "rejected" | "auto_ingested";
  reviewer?: string | null;
  review_notes?: string | null;
  resulting_paper_id?: string | null;
  created_at: string;
  reviewed_at?: string | null;
}

export interface DiscoveryRunResult {
  candidates_seen: number;
  auto_ingested: number;
  queued: number;
  skipped_already_in_corpus: number;
  by_strategy: Record<string, number>;
}

// --- v0.6 research intelligence ---

export interface YearMetric {
  year: number;
  value: number;
}

export interface GrowthSeries {
  name: string;
  points: YearMetric[];
}

export interface EmergingEntity {
  entity_type: "institution" | "author";
  id: string;
  label: string;
  first_year: number;
  paper_count: number;
  is_partner?: boolean | null;
}

export interface ThemeGrowth {
  topic_id: string;
  name: string;
  value_now: number;
  value_then: number;
  delta_pct: number | "new";
}

export interface InstitutionCitationIndex {
  institution_id: string;
  institution_name: string;
  paper_count: number;
  normalized_index: number;
}

export interface NormalizedCitationImpact {
  metric_name: string;
  normalized_index?: number | null;
  covered_papers: number;
  total_papers: number;
  coverage: number;
  snapshot_oldest_at?: string | null;
  snapshot_newest_at?: string | null;
  source_breakdown: Record<string, number>;
  by_institution: InstitutionCitationIndex[];
}

export interface ImpactReport {
  yoy_attributed: GrowthSeries;
  yoy_by_label: GrowthSeries[];
  citation_impact: GrowthSeries;
  normalized_citation_impact: NormalizedCitationImpact;
  emerging_institutions: EmergingEntity[];
  emerging_authors: EmergingEntity[];
  top_growing_themes: ThemeGrowth[];
  window_from?: number | null;
  window_to?: number | null;
  audit: AnalysisAudit;
}

export interface TopicShare {
  topic_id: string;
  name: string;
  share: number;
  paper_count: number;
}

export interface YearTopics {
  year: number;
  total_papers: number;
  top_topics: TopicShare[];
}

export interface DriftEvent {
  from_year: number;
  to_year: number;
  cosine_similarity: number;
  new_topics: string[];
  faded_topics: string[];
}

export interface DriftReport {
  per_year: YearTopics[];
  drift_events: DriftEvent[];
  drift_threshold: number;
  audit: AnalysisAudit;
}

export interface MissedPaperGroup {
  key: string;
  label: string;
  description: string;
  candidate_ids: string[];
}

export interface MetricTriple {
  key: string;
  label: string;
  value: string | number;
  source_link: string;
}

export interface ReportSection {
  key: string;
  title: string;
  prose: string;
  metrics: MetricTriple[];
}

export interface ReportEvidencePolicy {
  mode: string;
  confidence_threshold: number;
  sdl_judgements: string[];
  include_model_only_separately: boolean;
  allow_needs_fulltext: boolean;
  allow_abstract_only: boolean;
  exclude_unreviewed_broad_retrieval: boolean;
}

export interface ReportResult {
  period_label: string;
  sections: ReportSection[];
  generated_at: string;
  backend: string;
  evidence_policy?: ReportEvidencePolicy;
}

export type ReportEvidenceMode =
  | "human_only"
  | "human_high_confidence"
  | "human_plus_probable"
  | "all_threshold";

export interface EvalMetric {
  label: string;
  precision: number;
  recall: number;
  f1: number;
  support: number;
}

export interface EvalReport {
  per_label: EvalMetric[];
  macro_precision: number;
  macro_recall: number;
  macro_f1: number;
  accuracy: number;
  confusion: Record<string, Record<string, number>>;
  evidence_recall_at_k: number | null;
  k: number;
  n_evaluated: number;
  dataset_role?: "frozen_holdout" | "diagnostic";
  dataset_id?: string;
  dataset_hash?: string | null;
  includes_silver?: boolean;
  label_scope?: string;
  annotation_sources?: string[];
  evidence_levels?: string[];
  allowed_claim?: string;
}

export interface SankeyNode {
  id: string;
  name: string;
  layer: "institution" | "topic" | "label";
}

export interface SankeyLink {
  source: string;
  target: string;
  value: number;
}

export interface SankeyPayload {
  nodes: SankeyNode[];
  links: SankeyLink[];
  audit: AnalysisAudit;
}

export interface TimelineSeries {
  name: string;
  data: [number, number][];
}

export interface TimelinePayload {
  by: "topic" | "label" | "institution" | "country" | "field";
  top_n: number;
  years: number[];
  series: TimelineSeries[];
  audit: AnalysisAudit;
}

export interface InstitutionNode {
  id: string;
  label: string;
  is_partner: boolean;
  country: string | null;
  paper_count: number;
}

export interface InstitutionEdge {
  source: string;
  target: string;
  weight: number;
  papers: string[];
  normalized_weight: number;
  involves_partner: boolean;
}

export interface InstitutionNetworkPayload {
  nodes: InstitutionNode[];
  edges: InstitutionEdge[];
  audit: AnalysisAudit;
}

export interface AnalyticsOverview {
  total_papers: number;
  label_breakdown: Record<string, number>;
  years: number[];
}

export interface GraphExplanation {
  paper_id: string;
  summary: string;
  direct_ac_authors: string[];
  second_degree_paths: SecondDegreePath[];
  citation_signals: CitationSignal[];
  cites_corpus: string[];
  cited_by_corpus: string[];
}

export type AttributionCentrality =
  | "core_contribution"
  | "supporting_method"
  | "background_only"
  | "incidental_mention"
  | "unrelated";

export type AttributionPolarity = "positive" | "negative";

export type AttributionMetadataStatus =
  | "versioned_validated"
  | "legacy_validated"
  | "legacy_fallback"
  | "invalid_fallback"
  | "not_applicable";

export interface AttributionTreeNode {
  node_id: string;
  parent_node_id: string | null;
  node_type: "root" | "section" | "source";
  path: string[];
  section_type: string | null;
  title: string;
  summary: string | null;
  page_start: number | null;
  page_end: number | null;
  source_section_id: string | null;
  source_chunk_ids: string[];
}

export interface AttributionEvidencePath {
  generation_id: string;
  path_id: string;
  rank: number;
  node_id: string;
  path: string[];
  evidence_type: string;
  polarity: AttributionPolarity;
  centrality: AttributionCentrality;
  quote: string;
  page_start: number | null;
  page_end: number | null;
  source_chunk_ids: string[];
  raw_score: number;
  weight: number;
  confidence: number | null;
  detector_type: string;
  metadata_status: AttributionMetadataStatus;
}

export interface AttributionEvidenceTree {
  paper_id: string;
  tree_version: string;
  generation_mode: "derived_ephemeral";
  generation_id: string;
  metadata_contract_version: string;
  nodes: AttributionTreeNode[];
  evidence_paths: AttributionEvidencePath[];
  evidence_review_recommended: boolean;
  evidence_review_reasons: string[];
}

export interface PaperFilterState {
  yearFrom?: number;
  yearTo?: number;
  labels: RelevanceLabel[];
  institutionIds: string[];
  topicIds: string[];
  fields: string[];
  countries: string[];
  corpusSources: string[];
  sdlJudgements: string[];
  acRelevanceJudgements: string[];
  aiForScienceJudgements: string[];
  reviewStatuses: string[];
  partnerOnly: boolean;
  acAuthorOnly: boolean;
  hasFulltext?: boolean;
  hasReview?: boolean;
  minConfidence?: number;
  maxConfidence?: number;
  search?: string;
}

// Default shows AC-relevant papers only. Users can remove labels to see all.
export const DEFAULT_FILTER: PaperFilterState = {
  labels: ["CORE_RELEVANT", "RELATED_RELEVANT"],
  institutionIds: [],
  topicIds: [],
  fields: [],
  countries: [],
  corpusSources: [],
  sdlJudgements: [],
  acRelevanceJudgements: [],
  aiForScienceJudgements: [],
  reviewStatuses: [],
  partnerOnly: false,
  acAuthorOnly: false,
};

// Truly empty — used by "Show all" toggle
export const EMPTY_FILTER: PaperFilterState = {
  labels: [],
  institutionIds: [],
  topicIds: [],
  fields: [],
  countries: [],
  corpusSources: [],
  sdlJudgements: [],
  acRelevanceJudgements: [],
  aiForScienceJudgements: [],
  reviewStatuses: [],
  partnerOnly: false,
  acAuthorOnly: false,
};

export interface NetworkNode {
  id: string;
  label: string;
  is_ac_member: boolean;
  institution?: string | null;
  institution_id?: string | null;
  paper_count: number;
  corpus_paper_count?: number;
  ac_core_citing_paper_count?: number;
  citation_affinity?: number;
  reference_evidence_paper_count?: number;
  citation_reference_coverage?: number;
  active_years?: number[];
  ppr_score: number;
  c_norm: number;
  cross_sdl_diversity?: number;
  bridge_score?: number;
  importance_score?: number;
  importance_profile?: string;
  importance_components?: Record<string, ImportanceComponent>;
  importance_radar_axes?: ImportanceRadarAxis[];
  importance_explanation?: string;
  importance_weights?: Record<string, number>;
  importance_rank?: number;
}

export interface ImportanceComponent {
  value: number;
  weight: number;
  contribution: number;
}

export interface ImportanceRadarAxis {
  key: string;
  label: string;
  value: number;
  weight: number;
}

export interface NetworkEdge {
  source: string;
  target: string;
  weight: number;
  papers: string[];
  normalized_weight: number;
  involves_ac: boolean;
  is_ac_ac: boolean;
}

export interface NetworkPayload {
  nodes: NetworkNode[];
  edges: NetworkEdge[];
  audit?: AnalysisAudit;
}

// --- v0.7 review loop / pipeline status ---

export type SdlJudgement =
  | "CONFIRMED_SDL"
  | "PROBABLE_SDL"
  | "SDL_ADJACENT"
  | "NOT_SDL"
  | "INSUFFICIENT_EVIDENCE";

export type AcRelevanceJudgement =
  | "AC_RELEVANT"
  | "NOT_AC_RELEVANT"
  | "INSUFFICIENT_EVIDENCE";

export type AiForScienceJudgement =
  | "AI_FOR_SCIENCE"
  | "NOT_AI_FOR_SCIENCE"
  | "INSUFFICIENT_EVIDENCE";

export type ReviewStatus = "PENDING" | "PARTIAL" | "COMPLETED" | "NEEDS_FULLTEXT";
export type EvidenceLevel =
  | "TITLE_ONLY"
  | "ABSTRACT"
  | "FULLTEXT"
  | "SUPPORTING_INFORMATION"
  | "UNKNOWN";
export type JudgementBasis = "DUAL_REVIEW" | "AC_REPORTING" | "STRICT_SDL" | "OTHER";
export type ScreeningStage =
  | "SEED_REFERENCE"
  | "BROAD_SCORED"
  | "HUMAN_REVIEW"
  | "HUMAN_RESOLVED";
export type ScreeningRoute =
  | "SEED"
  | "POSITIVE_REVIEW"
  | "UNCERTAIN_REVIEW"
  | "FULLTEXT_REVIEW"
  | "SCREENED_OUT"
  | "RESOLVED";

export interface QueueItem {
  paper_id: string;
  title: string;
  abstract?: string | null;
  year?: number | null;
  venue?: string | null;
  doi?: string | null;
  authors?: string[];
  institutions?: string[];
  label: RelevanceLabel;
  confidence: number;
  priority: number;
  reasons: string[];
  last_classified_at: string | null;
  source?: string | null;
  provenance: string | null;
  corpus_sources?: string[];
  full_text_url?: string | null;
  has_human_review: boolean;
  sdl_judgement?: SdlJudgement | null;
  ac_relevance_judgement?: AcRelevanceJudgement | null;
  ai_for_science_judgement?: AiForScienceJudgement | null;
  review_status?: ReviewStatus | null;
  evidence_level?: EvidenceLevel | null;
  judgement_basis?: JudgementBasis | null;
  screening_stage?: ScreeningStage | null;
  screening_route?: ScreeningRoute | null;
  screening_reason?: string | null;
  review_assignee?: string | null;
  review_assigned_at?: string | null;
  review_assigned_by?: string | null;
  rag_status?: RagStatus | null;
}

export interface PipelineStepLog {
  name: string;
  status?: string;
  started_at?: string;
  error?: string;
  [key: string]: unknown;
}

export interface PipelineRun {
  run_id: string;
  status: "success" | "failed";
  duration_seconds: number;
  started_at: string;
  finished_at: string;
  discovered_candidates: number;
  auto_ingested: number;
  queued_for_review: number;
  classified_new: number;
  reclassified_stale: number;
  enqueued_for_review: number;
  error_message: string | null;
  steps: PipelineStepLog[] | null;
  triggered_by: string;
}

export interface PipelineRunInput {
  do_discovery?: boolean | null;
  do_fulltext?: boolean | null;
  use_learned?: boolean | null;
  use_judge?: boolean | null;
  triggered_by?: string;
}

export interface ModelMetricSummary {
  n_evaluated?: number;
  accuracy?: number;
  macro_precision?: number;
  macro_recall?: number;
  macro_f1?: number;
  per_label?: Record<
    string,
    { precision: number; recall: number; f1: number; support: number }
  >;
  confusion?: Record<string, Record<string, number>>;
}

export interface ModelTrainingRun {
  run_id: string;
  status: "RUNNING" | "PROMOTED" | "REJECTED" | "INVALIDATED" | "FAILED";
  trigger_review_count: number;
  trigger_event_ids: string[];
  trigger_paper_ids: string[];
  lease_generation: number;
  training_example_count: number;
  validation_example_count: number;
  backend: string;
  model_version: string | null;
  evaluation_scope: string | null;
  candidate_metrics: ModelMetricSummary | null;
  incumbent_metrics: ModelMetricSummary | null;
  validation_candidate_metrics: ModelMetricSummary | null;
  validation_incumbent_metrics: ModelMetricSummary | null;
  promotion_reason: string | null;
  promotion_gate_config: Record<string, unknown> | null;
  runtime_versions: Record<string, unknown> | null;
  cache_sync_status: string | null;
  training_dataset_hash: string | null;
  validation_dataset_hash: string | null;
  label_boundary_hashes: Record<string, string> | null;
  candidate_model_sha256: string | null;
  incumbent_model_sha256: string | null;
  error_message: string | null;
  started_at: string;
  finished_at: string | null;
  promoted_at: string | null;
  heartbeat_at: string | null;
}

export interface ModelEvolutionStatus {
  batch_size: number;
  pending_reviews: number;
  reviews_until_retrain: number;
  progress: number;
  current_model_version: string | null;
  production_authority: {
    production_run_id: string | null;
    status: "VERIFIED" | "UNHEALTHY" | "LEGACY_CACHE" | "RULES_ONLY";
    model_version: string | null;
    artifact_sha256: string | null;
    cache_sync_status: string | null;
    cache_present: boolean;
    cache_sha256: string | null;
    cache_matches_authority: boolean | null;
    error: string | null;
  };
  validation_gate: {
    ready: boolean;
    required_examples: number;
    observed_examples: number;
    required_labels: number;
    observed_labels: string[];
    reason: string;
  };
  active_run: ModelTrainingRun | null;
  latest_run: ModelTrainingRun | null;
}

export interface EvidenceGapEntry {
  paper_id: string;
  title: string;
  label: RelevanceLabel;
  confidence: number;
  missing_types: string[];
  present_types: string[];
  reason: string;
}

export interface EvidenceGapBucket {
  bucket: string;
  label: string;
  description: string;
  count: number;
  entries: EvidenceGapEntry[];
}

export interface EvidenceGapReport {
  total_papers_scanned: number;
  buckets: EvidenceGapBucket[];
}

export interface LintEntry {
  paper_id: string;
  title: string;
  label: RelevanceLabel | null;
  severity: "blocker" | "warning";
  reason: string;
}

export interface LintBucket {
  bucket: string;
  label: string;
  description: string;
  severity: "blocker" | "warning";
  count: number;
  entries: LintEntry[];
}

export interface LintReport {
  total_papers_scanned: number;
  website_blockers: number;
  reporting_warnings: number;
  buckets: LintBucket[];
}

export interface DuplicateCandidate {
  paper_id: string;
  title: string;
  doi: string | null;
  year: number | null;
  provenance: string;
  label: RelevanceLabel | null;
  is_preprint: boolean;
  score: number;
}

// ── Retrieval (graph-enhanced) ──────────────────────────────────────────────

export interface ChunkOut {
  chunk_id: string;
  paper_id: string;
  section_type: string;
  section_title: string | null;
  text: string;
  token_count: number;
  score: number | null;
  bm25_score: number | null;
  cosine_score: number | null;
  graph_score: number | null;
}

export interface SourceOut extends ChunkOut {
  graph_context: string | null;
}

export interface PropositionHit {
  paper_id: string;
  predicate: string;
  object_value: string;
  claim_text: string;
  confidence: number;
  source_section: string | null;
  score: number;
}

export interface RagModuleStep {
  module: string;
  [key: string]: unknown;
}

export interface AnswerOut {
  answer: string;
  sources: SourceOut[];
  model: string;
  chunks_retrieved: number;
  proposition_hints: PropositionHit[];
  query_type: string;
  evidence_score: number;
  source_precision: number;
  missing_evidence: string[];
  should_retry: boolean;
  retrieval_query: string;
  conversation_turns_used: number;
  page_context: string | null;
  // Present in the backend payload; surfaced by the agent UI.
  module_trace?: RagModuleStep[];
  execution_mode?: string;
}

export interface SqlChatOut {
  answer: string;
  model: "deterministic-text-to-sql";
  intent: string;
  planner: string;
  resolved_query: string;
  sql: string;
  parameters: Record<string, unknown>;
  rows: Array<Record<string, unknown>>;
  audit: {
    planner: string;
    answer_renderer: string;
    read_only: boolean;
    llm_used: boolean;
    allowed_intents: string[];
    allowed_tables: string[];
    intent: string;
    group_by?: string | null;
    limit: number;
    query_constraints: Record<string, unknown>;
    page_filter: Record<string, unknown>;
    page_filter_fingerprint: string;
    scope_paper_count: number;
    scope_paper_set_sha256: string;
    scope_paper_set_encoding: string;
    statement_sha256: string;
    parameter_binding: string;
    statement_type?: "SELECT";
    row_count: number;
  };
  conversation_turns_used: number;
  page_context: string | null;
}

export interface ConversationTurn {
  role: "user" | "assistant";
  content: string;
}

export interface RagFeedbackIn {
  query: string;
  rating: number;
  failure_type?: string | null;
  note?: string | null;
  answer_model?: string | null;
  source_chunk_ids: string[];
  source_paper_ids: string[];
}

// ────────────────────────────────────────────────────────────────────────────

export interface DuplicateGroup {
  key: string;
  title: string;
  group_type: string;
  severity: "blocker" | "warning";
  canonical_paper_id: string;
  reason: string;
  candidates: DuplicateCandidate[];
}

export interface DuplicateReport {
  group_count: number;
  paper_count: number;
  blocker_groups: number;
  warning_groups: number;
  groups: DuplicateGroup[];
}

// --- v0.7 multi-entity graph, geographic, people-grid ---

export interface MultiGraphNode {
  id: string;
  type: "author" | "institution" | "country" | "paper" | "topic" | "method" | "funder" | "ac_core";
  label: string;
  group: string | null;
  metadata: Record<string, unknown>;
}

export interface MultiGraphEdge {
  source: string;
  target: string;
  type: string;
  weight: number;
  metadata: Record<string, unknown>;
}

export interface MultiGraphGroup {
  id: string;
  label: string;
  color: string;
  node_count: number;
}

export interface MultiGraphPayload {
  nodes: MultiGraphNode[];
  edges: MultiGraphEdge[];
  groups: MultiGraphGroup[];
  available_node_types: string[];
  available_edge_types: string[];
  available_group_keys: string[];
  audit: AnalysisAudit;
}

export interface AnalysisAudit {
  filter: Record<string, unknown>;
  filter_fingerprint: string;
  paper_set_sha256: string;
  paper_set_encoding?: string;
  included_papers: number;
  classified_papers: number;
  reviewed_papers: number;
  fulltext_papers: number;
  corpus_source_breakdown: Record<string, number>;
  algorithm: string;
  metric_definitions: Record<string, string>;
  filter_semantics?: Record<string, string>;
  generated_at: string;
  graph_filter?: Record<string, unknown>;
  projection?: Record<string, unknown>;
  projection_fingerprint?: string;
  purpose?: string;
  dependencies?: Record<string, AnalysisAudit>;
  evidence_subsets?: Record<string, {
    count: number;
    paper_set_sha256: string;
    paper_set_encoding?: string;
    purpose?: string;
  }>;
}

export interface FilterOptions {
  years: number[];
  countries: string[];
  institutions: Array<{
    id: string;
    name: string;
    country: string | null;
    is_partner: boolean;
  }>;
  topics: Array<{ id: string; name: string }>;
  fields: string[];
  corpus_sources: string[];
}

export interface GeoCountry {
  country: string;
  paper_count: number;
  institution_count: number;
  is_partner: boolean;
}
export interface GeoArc {
  from: string;
  to: string;
  weight: number;
}
export interface GeoInstitution {
  id: string;
  institution_id?: string;
  name: string;
  country: string;
  is_partner: boolean;
  paper_count: number;
}
export interface GeographicCenter {
  type: "country" | "institution";
  id: string;
  name: string;
  country?: string | null;
  paper_count: number;
  collaboration_paper_count: number;
  partner_count: number;
  first_year?: number | null;
  last_year?: number | null;
  missing_year_paper_count: number;
}
export interface GeographicGrowthPoint {
  year: number;
  center_papers: number;
  collaboration_papers: number;
  active_partners: number;
  cumulative_partners: number;
  cumulative_collaboration_papers: number;
}
export interface GeographicPartner {
  id: string;
  name: string;
  country?: string | null;
  paper_count: number;
  first_year?: number | null;
  last_year?: number | null;
  yearly: Array<{ year: number; paper_count: number }>;
}
export interface GeographicReport {
  countries: GeoCountry[];
  arcs: GeoArc[];
  institutions: GeoInstitution[];
  total_papers: number;
  center_country?: string | null;
  center?: GeographicCenter | null;
  growth: GeographicGrowthPoint[];
  partners: GeographicPartner[];
  audit: AnalysisAudit;
}

export interface PeoplePaper {
  id: string;
  title: string;
  year: number | null;
  label: string | null;
}
export interface PeopleElement {
  person_id: string;
  symbol: string;
  name: string;
  atomic_number: number;
  category: string;
  category_label: string;
  institution: string | null;
  country: string | null;
  orcid: string | null;
  core_count: number;
  related_count: number;
  papers: PeoplePaper[];
}
export interface PeopleCategory {
  id: string;
  label: string;
  paper_count: number;
}
export interface PeopleGrid {
  elements: PeopleElement[];
  categories: PeopleCategory[];
  max_papers: number;
  total_people: number;
}

// ── Research Network Growth ──────────────────────────────────────────────────

export interface GrowthPoint {
  year: number;
  papers: number;
  authors: number;
  institutions: number;
  countries: number;
  collaborations: number;
}

export interface NetworkGrowthPayload {
  yearly: GrowthPoint[];
  cumulative: GrowthPoint[];
}

export interface InstitutionAuthorshipRun {
  id: string;
  agent_version: string;
  status: string;
  input_sha256: string;
  summary: Record<string, unknown>;
  started_at: string;
  completed_at: string | null;
}

export interface InstitutionAuthorshipOptions {
  corpus: { id: "tier1" | "tier1_tier2"; label: string };
  corpora: Array<{ id: "tier1" | "tier1_tier2"; label: string }>;
  focus: { name: string; ror: string; openalex_id: string };
  years: number[];
  credit_schemes: Array<{
    value: string;
    label: string;
    description: string;
  }>;
  author_roles: Array<{ value: string; label: string; description: string }>;
  affiliation_allocations: Array<{ value: string; label: string }>;
  focus_scopes: Array<{ value: string; label: string }>;
  latest_enrichment_run: InstitutionAuthorshipRun | null;
}

export interface InstitutionAuthorshipRow {
  rank: number;
  id: string | null;
  name: string;
  ror: string | null;
  openalex_id: string | null;
  country_code: string | null;
  weighted_credit: number;
  share_of_resolved_credit: number;
  share_of_country_credit?: number;
  paper_count: number;
  authorship_count: number;
  first_author_credit: number;
  last_author_credit: number;
  corresponding_author_credit: number;
  sources: Record<string, number>;
  contributes_to_focus: boolean;
}

export interface InstitutionCollaborationNode {
  id: string;
  institution_id: string | null;
  name: string;
  ror: string | null;
  openalex_id: string | null;
  country_code: string | null;
  is_focus: boolean;
  paper_count: number;
  collaborator_count: number;
  collaboration_paper_count: number;
  connection_weight: number;
  rank: number;
}

export interface InstitutionCollaborationNetwork {
  available: boolean;
  scope: {
    complete_papers: number;
    papers_with_connections: number;
    institution_count: number;
    connection_count: number;
    displayed_node_count: number;
    displayed_connection_count: number;
    node_limit: number;
  };
  focus: (InstitutionCollaborationNode & {
    institutions_with_fewer_collaborators: number;
    fraction_of_institutions_with_fewer_collaborators: number;
  }) | null;
  nodes: InstitutionCollaborationNode[];
  edges: Array<{ source: string; target: string; paper_count: number }>;
  ranking: InstitutionCollaborationNode[];
  method: {
    paper_scope: string;
    connection_rule: string;
    collaborator_count_rule: string;
    edge_weight_rule: string;
    focus_identity_rule: string;
  };
}

export interface InstitutionAuthorshipReport {
  available: boolean;
  scope: {
    corpus_papers: number;
    papers_with_authorship_metadata: number;
    papers_with_complete_institution_membership: number;
    papers_with_incomplete_institution_membership: number;
    papers_without_authorship_metadata: number;
    paper_institution_membership_coverage: number;
    authorship_metadata_rows: number;
    selected_authorships: number;
    authorships_with_resolved_affiliations: number;
    selected_author_credit: number;
    resolved_author_credit: number;
    affiliation_credit_coverage: number;
    unresolved_affiliation_assertions: number;
    below_threshold_affiliation_assertions: number;
    institution_count: number;
  };
  focus: {
    name: string;
    ror: string;
    openalex_id: string;
    weighted_credit: number;
    paper_count: number;
    share_of_corpus_papers: number;
    share_of_resolved_credit: number;
    rank: number | null;
  };
  comparison: {
    other_institutions_weighted_credit: number;
    other_institutions_paper_count: number;
    focus_to_other_credit_ratio: number | null;
  };
  institutions: InstitutionAuthorshipRow[];
  yearly: Array<{
    year: number;
    corpus_papers: number;
    focus_papers: number;
    focus_paper_share_of_corpus: number;
    other_institution_papers: number;
    focus_weighted_credit: number;
    other_weighted_credit: number;
  }>;
  network: InstitutionCollaborationNetwork;
  configuration: {
    corpus: "tier1" | "tier1_tier2";
    credit_scheme: string;
    author_role: string;
    affiliation_allocation: string;
    focus_scope: string;
    focus_ror: string;
    focus_openalex_id: string;
    paper_count_rule: string;
    min_affiliation_confidence: number;
    credit_scheme_label: string;
    credit_scheme_description: string;
    author_role_label: string;
    author_role_description: string;
  };
  audit: {
    filter: Record<string, unknown>;
    filter_fingerprint: string;
    paper_set_sha256: string;
    paper_set_encoding: string;
    included_papers: number;
    algorithm: string;
    metric_definitions: Record<string, string>;
    filter_semantics: Record<string, string>;
    data_boundary: {
      mode: "metadata_only_s3_snapshot";
      included: string[];
      excluded: string[];
    };
    snapshot: {
      bucket: string | null;
      manifest_key: string;
      manifest_sha256: string;
      snapshot_id: string | null;
      raw_prefix: string | null;
      fulltext_prefix: string | null;
      separation_verified: boolean;
    };
    projection: Record<string, unknown>;
    projection_fingerprint: string;
    source_breakdown: Record<string, number>;
    generated_at: string;
  };
}

/** ECharts themeRiver format: [year_string, count, topic_name] */
export type TopicStreamRow = [string, number, string];

export interface TopicStreamPayload {
  data: TopicStreamRow[];
  topics: string[];
}

export interface InstTopicCell {
  institution: string;
  topic: string;
  count: number;
}

export interface InstTopicHeatmapPayload {
  institutions: string[];
  topics: string[];
  cells: InstTopicCell[];
  year: number | null;
}

export interface HubYearPoint {
  year: number;
  degree_centrality: number;
  betweenness_centrality: number;
  partner_count: number;
  intl_collab_count: number;
  hub_score: number;
}

export interface HubScorePayload {
  institution: string;
  data: HubYearPoint[];
}

// ─── Cross-SDL knowledge transfer ─────────────────────────────────────────────

export interface TransferLab {
  id: string;
  name: string;
}

export interface TransferFlows {
  labs: TransferLab[];
  matrix: number[][];
  intra_lab: Record<string, number>;
  total_cross_flows: number;
}

export interface Adoption {
  lab: string;
  first_year: number;
  lag_years: number;
}

export interface AdoptionLag {
  entity: string;
  entity_type: string;
  origin_lab: string;
  origin_year: number;
  adoptions: Adoption[];
}

export interface FastSpreadingEntity {
  entity: string;
  entity_type: string;
  adopter_count: number;
  avg_lag_years: number;
}

export interface TransferSummary {
  labs: number;
  linked_papers: number;
  entities_tracked: number;
  cross_lab_entities: number;
  median_adoption_lag_years: number | null;
  fastest_spreading: FastSpreadingEntity[];
}

// ─── Cross-SDL knowledge base ─────────────────────────────────────────────────

export interface KbSummary {
  labs: number;
  linked_papers: number;
  entities_by_type: Record<string, number>;
  cross_lab_entities: number;
}

export interface KbEntityIndexItem {
  entity_type: string;
  name: string;
  paper_count: number;
  lab_count: number;
  first_year: number | null;
  last_year: number | null;
}

export interface KbEntityLab {
  lab_id: string;
  lab_name: string;
  first_year: number | null;
  paper_count: number;
}

export interface KbEntityPaper {
  id: string;
  title: string;
  year: number | null;
  labs: string[];
  confidence: number;
}

export interface KbYearCount {
  year: number;
  paper_count: number;
}

export interface KbEvidenceSnippet {
  paper_id: string;
  paper_title: string;
  text: string;
}

export interface KbEntityPage {
  entity: string;
  entity_type: string;
  labs: KbEntityLab[];
  papers: KbEntityPaper[];
  timeline: KbYearCount[];
  evidence: KbEvidenceSnippet[];
  adoption: AdoptionLag | null;
}

export interface KbTopEntity {
  name: string;
  paper_count: number;
}

export interface KbTagCount {
  tag: string;
  count: number;
}

export interface KbCollaboration {
  lab_id: string;
  name: string;
  shared_papers: number;
}

export interface KbLabProfile {
  id: string;
  name: string;
  institution: string;
  pi_names: string[];
  domain_focus: string;
  platform_stack: string[] | null;
  automation_level: string | null;
  paper_count: number;
  first_year: number | null;
  last_year: number | null;
  sdl_tag_histogram: KbTagCount[];
  top_entities: Record<string, KbTopEntity[]>;
  collaborations: KbCollaboration[];
  entities_unique_to_lab: number;
}

// ─── Cross-SDL transfer studio ────────────────────────────────────────────────

export interface TransferTarget {
  id: string;
  name: string;
  description: string;
  typical_signature: Record<string, unknown>;
  typical_constraints: string[];
  keywords: string[];
}

export interface TransferTku {
  id: string;
  paper_id: string;
  paper_title: string;
  paper_year: number | null;
  source_domain: string;
  problem_signature: Record<string, unknown>;
  method_core: Record<string, unknown>;
}

export interface TransferMatch {
  paper_id: string;
  title: string;
  year: number | null;
  source_domain: string;
  score: number;
  score_breakdown: Record<string, unknown>;
  key_lesson: string | null;
}

export interface TransferDesign {
  target: Record<string, unknown>;
  markdown: string;
  mode: "template" | "llm";
  matches: TransferMatch[];
}

// ─── Wiki / Knowledge Digest ──────────────────────────────────────────────────

export type WikiEntityType = "paper" | "author" | "institution" | "topic";

export interface WikiChip {
  label: string;
  kind: "author" | "institution" | "topic" | "paper" | "label" | "year";
}

export interface WikiSection {
  key: string;
  heading: string;
  body: string;
  chips?: WikiChip[];
}

export interface WikiPage {
  id: string;
  entity_type: WikiEntityType;
  entity_id: string;
  title: string;
  sections: WikiSection[];
  generated_at: string;
  model_version: string;
  prompt_version: string;
  is_stale: boolean;
}
