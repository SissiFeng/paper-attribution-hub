export type RelevanceLabel =
  | "CORE_RELEVANT"
  | "RELATED_RELEVANT"
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
}

export interface HumanReview {
  paper_id: string;
  human_label: string;
  corrected_topics?: string[] | null;
  corrected_people?: string[] | null;
  reviewer?: string | null;
  notes?: string | null;
  created_at: string;
}

export interface PaperAuthor {
  name: string;
  order: number;
  affiliation?: string | null;
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
}

export interface NetworkEdge {
  source: string;
  target: string;
  weight: number;
  papers: string[];
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
