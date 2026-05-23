import type {
  AnalyticsOverview,
  DiscoveryCandidate,
  DiscoveryRunResult,
  DriftReport,
  EvalReport,
  EvidenceGapReport,
  GeographicReport,
  GraphExplanation,
  HubScorePayload,
  ImpactReport,
  InstTopicHeatmapPayload,
  InstitutionNetworkPayload,
  MissedPaperGroup,
  MultiGraphPayload,
  NetworkGrowthPayload,
  NetworkPayload,
  Paper,
  PeopleGrid,
  PipelineRun,
  PipelineRunInput,
  QueueItem,
  ReportResult,
  SankeyPayload,
  TimelinePayload,
  TopicStreamPayload,
} from "@/types";
import * as mock from "@/lib/mock";

const API_BASE = (import.meta.env.VITE_API_BASE ?? "http://localhost:8000").replace(/\/$/, "");
const USE_MOCK = import.meta.env.VITE_USE_MOCK === "true";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (USE_MOCK) throw new Error("mock");
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return (await res.json()) as T;
}

async function withMock<T>(fetcher: () => Promise<T>, fallback: T): Promise<T> {
  try {
    return await fetcher();
  } catch {
    return fallback;
  }
}

export function listPapers(search?: URLSearchParams) {
  const qs = search?.toString();
  return withMock(
    () => request<Paper[]>(`/papers${qs ? `?${qs}` : ""}`),
    mock.MOCK_PAPERS
  );
}

export function getSankey(search?: URLSearchParams) {
  const qs = search?.toString();
  return withMock(
    () => request<SankeyPayload>(`/analytics/sankey${qs ? `?${qs}` : ""}`),
    mock.MOCK_SANKEY
  );
}

export function getTimeline(by: "topic" | "label", search?: URLSearchParams) {
  const params = new URLSearchParams(search);
  params.set("by", by);
  return withMock(
    () => request<TimelinePayload>(`/analytics/timeline?${params.toString()}`),
    by === "label" ? mock.MOCK_TIMELINE_BY_LABEL : mock.MOCK_TIMELINE_BY_TOPIC
  );
}

export function getInstitutionNetwork(minPapers: number, search?: URLSearchParams) {
  const params = new URLSearchParams(search);
  params.set("min_papers", String(minPapers));
  return withMock(
    () => request<InstitutionNetworkPayload>(`/analytics/institution-network?${params.toString()}`),
    mock.MOCK_INSTITUTION_NETWORK
  );
}

export function getOverview(search?: URLSearchParams) {
  const qs = search?.toString();
  return withMock(
    () => request<AnalyticsOverview>(`/analytics/overview${qs ? `?${qs}` : ""}`),
    mock.MOCK_OVERVIEW
  );
}

export function getGraphExplanation(paperId: string) {
  return withMock(
    () => request<GraphExplanation>(`/papers/${paperId}/graph-explanation`),
    mock.getMockGraphExplanation(paperId)
  );
}

export function runDiscovery(payload?: { strategies?: string[]; max_candidates?: number }) {
  return withMock(
    () => request<DiscoveryRunResult>("/discovery/run", {
      method: "POST",
      body: JSON.stringify(payload ?? {}),
    }),
    { candidates_seen: 12, auto_ingested: 2, queued: 3, skipped_already_in_corpus: 7, by_strategy: { citation_expansion: 5, author_following: 4, topic_expansion: 3 } }
  );
}

export function listDiscoveryQueue(status: string = "queued") {
  return withMock(
    () => request<DiscoveryCandidate[]>(`/discovery/queue?status=${status}`),
    mock.MOCK_DISCOVERY.filter((d) => status === "all" || d.status === status)
  );
}

export function approveDiscoveryCandidate(
  id: string,
  payload: { reviewer?: string; notes?: string } = {}
) {
  return withMock(
    () => request<DiscoveryCandidate>(`/discovery/queue/${id}/approve`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
    { ...mock.MOCK_DISCOVERY[0], status: "approved" as const, reviewer: payload.reviewer ?? null }
  );
}

export function rejectDiscoveryCandidate(
  id: string,
  payload: { reviewer?: string; notes?: string } = {}
) {
  return withMock(
    () => request<DiscoveryCandidate>(`/discovery/queue/${id}/reject`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
    { ...mock.MOCK_DISCOVERY[0], status: "rejected" as const, reviewer: payload.reviewer ?? null }
  );
}

// --- v0.6 research intelligence ---

export function getImpactReport(search?: URLSearchParams) {
  const qs = search?.toString();
  return withMock(
    () => request<ImpactReport>(`/analytics/impact${qs ? `?${qs}` : ""}`),
    mock.MOCK_IMPACT
  );
}

export function getDriftReport(search?: URLSearchParams) {
  const qs = search?.toString();
  return withMock(
    () => request<DriftReport>(`/analytics/drift${qs ? `?${qs}` : ""}`),
    mock.MOCK_DRIFT
  );
}

export function getMissedPaperGroups(status: string = "queued") {
  return withMock(
    () => request<MissedPaperGroup[]>(`/analytics/missed-papers?status=${status}`),
    mock.MOCK_MISSED_GROUPS
  );
}

export function generateReport(
  payload: { sections?: string[]; backend?: string } = {},
  search?: URLSearchParams
) {
  const qs = search?.toString();
  return withMock(
    () => request<ReportResult>(`/analytics/report${qs ? `?${qs}` : ""}`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
    mock.MOCK_REPORT
  );
}

export function getCoauthorNetwork(onlyRelevant: boolean) {
  return withMock(
    () => request<NetworkPayload>(`/network/coauthors?only_relevant=${onlyRelevant}`),
    mock.MOCK_COAUTHOR_NETWORK
  );
}

export function submitReview(
  paperId: string,
  payload: { human_label: string; reviewer?: string; notes?: string }
) {
  return withMock(
    () => request(`/reviews/${paperId}`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
    {}
  );
}

export function getEvalReport(k: number = 5) {
  return withMock(
    () => request<EvalReport>(`/eval/metrics?k=${k}`),
    mock.MOCK_EVAL
  );
}

// --- v0.7 review loop / pipeline ---

export function getReviewQueue(params: { limit?: number; offset?: number } = {}) {
  const search = new URLSearchParams();
  if (params.limit != null) search.set("limit", String(params.limit));
  if (params.offset != null) search.set("offset", String(params.offset));
  const qs = search.toString();
  const { limit = 20, offset = 0 } = params;
  return withMock(
    () => request<QueueItem[]>(`/reviews/queue${qs ? `?${qs}` : ""}`),
    mock.MOCK_QUEUE.slice(offset, offset + limit)
  );
}

export function getReviewQueueNext() {
  return withMock(
    () => request<QueueItem | null>("/reviews/queue/next"),
    mock.MOCK_QUEUE[0] ?? null
  );
}

export function getReviewQueueSize() {
  return withMock(
    () => request<{ count: number }>("/reviews/queue/size"),
    { count: mock.MOCK_QUEUE.length }
  );
}

export function confirmClassification(
  paperId: string,
  payload: { reviewer?: string } = {}
) {
  return withMock(
    () => request<QueueItem>(`/reviews/${paperId}/confirm`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
    mock.MOCK_QUEUE.find((q) => q.paper_id === paperId) ?? mock.MOCK_QUEUE[0]
  );
}

export function skipReview(
  paperId: string,
  payload: { cooldown_days?: number } = {}
) {
  return withMock(
    () => request<QueueItem>(`/reviews/${paperId}/skip`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
    mock.MOCK_QUEUE.find((q) => q.paper_id === paperId) ?? mock.MOCK_QUEUE[0]
  );
}

export function listPipelineRuns(limit: number = 20) {
  return withMock(
    () => request<PipelineRun[]>(`/pipeline/runs?limit=${limit}`),
    mock.MOCK_PIPELINE_RUNS.slice(0, limit)
  );
}

export function getLatestPipelineRun() {
  return withMock(
    () => request<PipelineRun | null>("/pipeline/runs/latest"),
    mock.MOCK_PIPELINE_RUNS[0] ?? null
  );
}

export function runPipeline(payload: PipelineRunInput = {}) {
  return withMock(
    () => request<PipelineRun>("/pipeline/run", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
    { ...mock.MOCK_PIPELINE_RUNS[0], run_id: `run-mock-${Date.now()}`, triggered_by: payload.triggered_by ?? "manual" }
  );
}

export function getEvidenceGaps() {
  return withMock(
    () => request<EvidenceGapReport>("/analytics/evidence-gaps"),
    mock.MOCK_EVIDENCE_GAPS
  );
}

export function getPeopleGrid() {
  return withMock(
    () => request<PeopleGrid>("/analytics/people-grid"),
    mock.MOCK_PEOPLE_GRID
  );
}

export interface MultiGraphParams {
  node_types?: string[];
  edge_types?: string[];
  group_by?: string;
  center_id?: string;
  hop_limit?: number;
  year_from?: number;
  year_to?: number;
}

export function getMultiGraph(params: MultiGraphParams = {}) {
  const sp = new URLSearchParams();
  (params.node_types ?? []).forEach((t) => sp.append("node_types", t));
  (params.edge_types ?? []).forEach((t) => sp.append("edge_types", t));
  if (params.group_by) sp.set("group_by", params.group_by);
  if (params.center_id) sp.set("center_id", params.center_id);
  if (params.hop_limit != null) sp.set("hop_limit", String(params.hop_limit));
  if (params.year_from != null) sp.set("year_from", String(params.year_from));
  if (params.year_to != null) sp.set("year_to", String(params.year_to));
  const qs = sp.toString();
  return withMock(
    () => request<MultiGraphPayload>(`/analytics/multi-graph${qs ? `?${qs}` : ""}`),
    mock.MOCK_MULTI_GRAPH
  );
}

export function getGeographic(params: { year_from?: number; year_to?: number } = {}) {
  const sp = new URLSearchParams();
  if (params.year_from != null) sp.set("year_from", String(params.year_from));
  if (params.year_to != null) sp.set("year_to", String(params.year_to));
  const qs = sp.toString();
  return withMock(
    () => request<GeographicReport>(`/analytics/geographic${qs ? `?${qs}` : ""}`),
    mock.MOCK_GEOGRAPHIC
  );
}

export function getNetworkGrowth(params: { year_from?: number; year_to?: number } = {}) {
  const sp = new URLSearchParams();
  if (params.year_from != null) sp.set("year_from", String(params.year_from));
  if (params.year_to != null) sp.set("year_to", String(params.year_to));
  const qs = sp.toString();
  return withMock(
    () => request<NetworkGrowthPayload>(`/analytics/network-growth${qs ? `?${qs}` : ""}`),
    mock.MOCK_NETWORK_GROWTH
  );
}

export function getTopicStream(params: { year_from?: number; year_to?: number } = {}) {
  const sp = new URLSearchParams();
  if (params.year_from != null) sp.set("year_from", String(params.year_from));
  if (params.year_to != null) sp.set("year_to", String(params.year_to));
  const qs = sp.toString();
  return withMock(
    () => request<TopicStreamPayload>(`/analytics/topic-stream${qs ? `?${qs}` : ""}`),
    mock.MOCK_TOPIC_STREAM
  );
}

export function getInstTopicHeatmap(params: { year?: number } = {}) {
  const sp = new URLSearchParams();
  if (params.year != null) sp.set("year", String(params.year));
  const qs = sp.toString();
  return withMock(
    () => request<InstTopicHeatmapPayload>(`/analytics/inst-topic-heatmap${qs ? `?${qs}` : ""}`),
    mock.MOCK_INST_TOPIC_HEATMAP
  );
}

export function getHubScore(institution: string = "uoft") {
  return withMock(
    () => request<HubScorePayload>(`/analytics/hub-score?institution=${institution}`),
    mock.MOCK_HUB_SCORE
  );
}

export { API_BASE };
