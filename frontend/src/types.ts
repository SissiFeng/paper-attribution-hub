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
}

export interface HumanReview {
  paper_id: string;
  human_label: string;
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

export interface ImpactReport {
  yoy_attributed: GrowthSeries;
  yoy_by_label: GrowthSeries[];
  citation_impact: GrowthSeries;
  emerging_institutions: EmergingEntity[];
  emerging_authors: EmergingEntity[];
  top_growing_themes: ThemeGrowth[];
  window_from?: number | null;
  window_to?: number | null;
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

export interface ReportResult {
  period_label: string;
  sections: ReportSection[];
  generated_at: string;
  backend: string;
}

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
}

export interface TimelineSeries {
  name: string;
  data: [number, number][];
}

export interface TimelinePayload {
  by: "topic" | "label";
  years: number[];
  series: TimelineSeries[];
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

export interface PaperFilterState {
  yearFrom?: number;
  yearTo?: number;
  labels: RelevanceLabel[];
  institutionIds: string[];
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
  partnerOnly: false,
  acAuthorOnly: false,
};

// Truly empty — used by "Show all" toggle
export const EMPTY_FILTER: PaperFilterState = {
  labels: [],
  institutionIds: [],
  partnerOnly: false,
  acAuthorOnly: false,
};

export interface NetworkNode {
  id: string;
  label: string;
  is_ac_member: boolean;
  institution?: string | null;
  paper_count: number;
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
}

// --- v0.7 review loop / pipeline status ---

export interface QueueItem {
  paper_id: string;
  title: string;
  label: RelevanceLabel;
  confidence: number;
  priority: number;
  reasons: string[];
  last_classified_at: string | null;
  provenance: string | null;
  has_human_review: boolean;
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
  // Present in the backend payload; surfaced by the agent UI.
  module_trace?: RagModuleStep[];
  execution_mode?: string;
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
  type: "author" | "institution" | "paper" | "topic" | "method" | "funder" | "ac_core";
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
  name: string;
  country: string;
  is_partner: boolean;
  paper_count: number;
}
export interface GeographicReport {
  countries: GeoCountry[];
  arcs: GeoArc[];
  institutions: GeoInstitution[];
  total_papers: number;
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
  knowledge_state: string;
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
  concept_id: string | null;
  parent_concept_ids: string[];
  children: KbConceptRef[];
  direct_paper_count: number | null;
  direct_lab_count: number | null;
  rolled_up_paper_count: number | null;
  rolled_up_lab_count: number | null;
}

export interface KbConceptRef {
  concept_id: string;
  name: string;
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
  stage: string | null;
  usage_snippet: string | null;
  matched_entities: string[];
}

export interface KbYearCount {
  year: number;
  paper_count: number;
}

export interface KbEvidenceSnippet {
  paper_id: string;
  paper_title: string;
  text: string;
  stage: string | null;
  usage_snippet: string | null;
  matched_entity: string | null;
  knowledge_state: string | null;
}

export interface KbEntityFacet {
  name: string;
  concept_id: string | null;
  paper_count: number;
  knowledge_state: string;
}

export interface KbEntityPage {
  entity: string;
  entity_type: string;
  concept_id: string | null;
  ancestors: KbConceptRef[];
  children: KbConceptRef[];
  direct_paper_count: number;
  direct_lab_count: number;
  rolled_up_paper_count: number;
  rolled_up_lab_count: number;
  labs: KbEntityLab[];
  papers: KbEntityPaper[];
  timeline: KbYearCount[];
  evidence: KbEvidenceSnippet[];
  adoption: AdoptionLag | null;
  reactions: KbEntityFacet[];
  compositions: KbEntityFacet[];
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
