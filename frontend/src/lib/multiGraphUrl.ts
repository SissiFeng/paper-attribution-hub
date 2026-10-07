export interface MultiGraphProjectionState {
  nodeTypes: string[];
  edgeTypes: string[];
  groupBy: string;
  centerId: string | null;
  hopLimit: number;
  similarityMin: number;
  similarityTopK: number;
  minEdgeWeight: number;
  minPapers: number;
  minDegree: number;
  topN: number;
  excludedNodeIds: string[];
}

export const DEFAULT_MULTI_GRAPH_PROJECTION: MultiGraphProjectionState = {
  nodeTypes: [
    "author",
    "paper",
    "institution",
    "topic",
    "method",
    "material",
    "instrument",
    "software",
  ],
  edgeTypes: [
    "authored",
    "published_by",
    "belongs_to_topic",
    "uses_method",
    "mentions_material",
    "mentions_instrument",
    "mentions_software",
  ],
  groupBy: "by_entity_type",
  centerId: null,
  hopLimit: 2,
  similarityMin: 0.7,
  similarityTopK: 5,
  minEdgeWeight: 0.3,
  minPapers: 1,
  minDegree: 0,
  topN: 100,
  excludedNodeIds: [],
};

function numberParam(
  params: URLSearchParams,
  key: string,
  fallback: number,
  min: number,
  max?: number,
): number {
  const raw = params.get(key);
  if (raw === null || raw.trim() === "") return fallback;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max ?? parsed, Math.max(min, parsed));
}

export function multiGraphProjectionFromSearchParams(
  params: URLSearchParams,
): MultiGraphProjectionState {
  const nodeTypes = params.getAll("node_types");
  const edgeTypes = params.getAll("edge_types");
  return {
    nodeTypes: nodeTypes.length > 0
      ? [...new Set(nodeTypes)]
      : [...DEFAULT_MULTI_GRAPH_PROJECTION.nodeTypes],
    edgeTypes: edgeTypes.length > 0
      ? [...new Set(edgeTypes)]
      : [...DEFAULT_MULTI_GRAPH_PROJECTION.edgeTypes],
    groupBy: params.get("group_by") || DEFAULT_MULTI_GRAPH_PROJECTION.groupBy,
    centerId: params.get("center_id") || params.get("center"),
    hopLimit: numberParam(params, "hop_limit", 2, 1, 4),
    similarityMin: numberParam(params, "similarity_min", 0.7, 0, 1),
    similarityTopK: numberParam(params, "similarity_top_k", 5, 1, 50),
    minEdgeWeight: numberParam(params, "min_edge_weight", 0.3, 0),
    minPapers: numberParam(params, "min_papers", 1, 1),
    minDegree: numberParam(params, "min_degree", 0, 0),
    topN: numberParam(params, "top_n", 100, 1, 500),
    excludedNodeIds: [...new Set(params.getAll("excluded_node_ids"))],
  };
}

export function multiGraphProjectionToSearchParams(
  base: URLSearchParams,
  projection: MultiGraphProjectionState,
): URLSearchParams {
  const params = new URLSearchParams(base);
  for (const key of [
    "node_types",
    "edge_types",
    "group_by",
    "center",
    "center_id",
    "hop_limit",
    "similarity_min",
    "similarity_top_k",
    "min_edge_weight",
    "min_papers",
    "min_degree",
    "top_n",
    "excluded_node_ids",
  ]) {
    params.delete(key);
  }
  projection.nodeTypes.forEach((value) => params.append("node_types", value));
  projection.edgeTypes.forEach((value) => params.append("edge_types", value));
  params.set("group_by", projection.groupBy);
  if (projection.centerId) params.set("center_id", projection.centerId);
  params.set("hop_limit", String(projection.hopLimit));
  params.set("similarity_min", String(projection.similarityMin));
  params.set("similarity_top_k", String(projection.similarityTopK));
  params.set("min_edge_weight", String(projection.minEdgeWeight));
  params.set("min_papers", String(projection.minPapers));
  params.set("min_degree", String(projection.minDegree));
  params.set("top_n", String(projection.topN));
  projection.excludedNodeIds.forEach((value) => {
    params.append("excluded_node_ids", value);
  });
  return params;
}
