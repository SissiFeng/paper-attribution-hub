import type {
  AttributionEvidencePath,
  AttributionEvidenceTree,
  AttributionTreeNode,
} from "@/types";

export type EvidenceStarItem =
  | {
      id: string;
      kind: "tree";
      label: string;
      treeNode: AttributionTreeNode;
    }
  | {
      id: string;
      kind: "evidence";
      label: string;
      evidencePath: AttributionEvidencePath;
    };

interface EvidenceChartNode {
  id: string;
  name: string;
  x: number;
  y: number;
  value: number;
  symbol: "circle" | "diamond" | "roundRect";
  symbolSize: number;
  category: number;
  selected?: boolean;
  itemStyle: {
    color: string;
    borderColor: string;
    borderWidth: number;
    shadowBlur: number;
    shadowColor: string;
  };
  label: {
    show: boolean;
    color: string;
    fontFamily: string;
    fontSize: number;
    formatter: string;
    position: "right" | "bottom";
  };
  starKind: EvidenceStarItem["kind"];
  subtitle: string;
}

interface EvidenceChartLink {
  source: string;
  target: string;
  value: string;
  lineStyle: {
    color: string;
    width: number;
    opacity: number;
    curveness: number;
    type?: "dashed";
  };
}

export interface EvidenceStarModel {
  items: EvidenceStarItem[];
  byId: Map<string, EvidenceStarItem>;
  option: object;
}

const ROOT_COLOR = "#f3d8ed";
const SECTION_COLOR = "#8dc6e6";
const SOURCE_COLOR = "#c9b6e4";
const POSITIVE_COLOR = "#77ddb2";
const NEGATIVE_COLOR = "#ff9b7c";
const MAP_FONT = "'JetBrains Mono', ui-monospace, monospace";

export function formatEvidenceType(value: string): string {
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function formatPageRange(
  pageStart: number | null,
  pageEnd: number | null
): string | null {
  if (pageStart == null) return null;
  return pageEnd != null && pageEnd !== pageStart
    ? `Pages ${pageStart}–${pageEnd}`
    : `Page ${pageStart}`;
}

function truncate(value: string, limit: number): string {
  return value.length <= limit ? value : `${value.slice(0, limit - 1)}…`;
}

function anglePosition(index: number, total: number, radius: number) {
  const angle = -Math.PI / 2 + (index / Math.max(total, 1)) * Math.PI * 2;
  return { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius };
}

function treeStructureKey(node: AttributionTreeNode): string {
  return [
    node.node_type,
    node.source_section_id ?? "",
    node.section_type ?? "",
    node.path.join(">"),
  ].join("|");
}

function evidenceStructureKey(
  path: AttributionEvidencePath,
  nodesById: Map<string, AttributionTreeNode>
): string {
  const parent = nodesById.get(path.node_id);
  return [
    parent ? treeStructureKey(parent) : path.node_id,
    path.evidence_type,
    path.source_chunk_ids.join(","),
    path.quote,
  ].join("|");
}

function treeDepth(
  node: AttributionTreeNode,
  nodesById: Map<string, AttributionTreeNode>
): number {
  let depth = 0;
  let cursor: AttributionTreeNode | undefined = node;
  const visited = new Set<string>();

  while (cursor.parent_node_id) {
    if (visited.has(cursor.node_id)) return 1;
    visited.add(cursor.node_id);
    cursor = nodesById.get(cursor.parent_node_id);
    depth += 1;
    if (!cursor) break;
  }
  return depth;
}

function treeNodeStyle(node: AttributionTreeNode) {
  if (node.node_type === "root") {
    return {
      symbol: "diamond" as const,
      size: 34,
      color: ROOT_COLOR,
      glow: "rgba(221,174,211,0.85)",
      labelColor: "#f8eef6",
    };
  }
  if (node.node_type === "source") {
    return {
      symbol: "roundRect" as const,
      size: 20,
      color: SOURCE_COLOR,
      glow: "rgba(201,182,228,0.55)",
      labelColor: "#e5dcf2",
    };
  }
  return {
    symbol: "circle" as const,
    size: 20,
    color: SECTION_COLOR,
    glow: "rgba(141,198,230,0.55)",
    labelColor: "#d5edfb",
  };
}

function evidenceNodeStyle(path: AttributionEvidencePath) {
  const positive = path.polarity === "positive";
  const color = positive ? POSITIVE_COLOR : NEGATIVE_COLOR;
  return {
    color,
    glow: positive ? "rgba(119,221,178,0.65)" : "rgba(255,155,124,0.7)",
    size: Math.max(12, Math.min(24, 13 + Math.abs(path.weight) * 10)),
  };
}

export function buildEvidenceStarModel(
  tree: AttributionEvidenceTree,
  selectedId: string | null,
  source: "server_aet" | "paper_payload"
): EvidenceStarModel {
  const reduceMotion =
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const nodesById = new Map(tree.nodes.map((node) => [node.node_id, node]));
  const treeNodesByDepth = new Map<number, AttributionTreeNode[]>();
  for (const node of tree.nodes) {
    const depth = treeDepth(node, nodesById);
    const bucket = treeNodesByDepth.get(depth) ?? [];
    bucket.push(node);
    treeNodesByDepth.set(depth, bucket);
  }

  const coordinates = new Map<string, { x: number; y: number }>();
  let nextTreeRadius = 230;
  const orderedDepths = [...treeNodesByDepth.entries()].sort(
    ([depthA], [depthB]) => depthA - depthB
  );
  for (const [depth, nodes] of orderedDepths) {
    const ordered = [...nodes].sort((a, b) =>
      treeStructureKey(a).localeCompare(treeStructureKey(b))
    );
    if (depth === 0) {
      for (const node of ordered) coordinates.set(node.node_id, { x: 0, y: 0 });
      continue;
    }
    let nodeCursor = 0;
    let radius = nextTreeRadius;
    while (nodeCursor < ordered.length) {
      const ringCapacity = Math.max(
        8,
        Math.floor((Math.PI * 2 * radius) / 90)
      );
      const ringCount = Math.min(ringCapacity, ordered.length - nodeCursor);
      for (let slot = 0; slot < ringCount; slot += 1) {
        const node = ordered[nodeCursor + slot];
        coordinates.set(node.node_id, anglePosition(slot, ringCount, radius));
      }
      nodeCursor += ringCount;
      radius += 120;
    }
    nextTreeRadius = radius;
  }

  const orderedPaths = [...tree.evidence_paths].sort(
    (a, b) =>
      evidenceStructureKey(a, nodesById).localeCompare(
        evidenceStructureKey(b, nodesById)
      )
  );
  let pathCursor = 0;
  let pathRadius = Math.max(490, nextTreeRadius + 140);
  while (pathCursor < orderedPaths.length) {
    // Capacity grows with circumference, keeping adjacent stars roughly 62
    // world units apart. Dense papers gain more orbits instead of collapsing
    // every evidence path onto one fixed-capacity ring.
    const ringCapacity = Math.max(12, Math.floor((Math.PI * 2 * pathRadius) / 62));
    const ringCount = Math.min(ringCapacity, orderedPaths.length - pathCursor);
    for (let slot = 0; slot < ringCount; slot += 1) {
      const path = orderedPaths[pathCursor + slot];
      coordinates.set(path.path_id, anglePosition(slot, ringCount, pathRadius));
    }
    pathCursor += ringCount;
    pathRadius += 135;
  }

  const items: EvidenceStarItem[] = [
    ...tree.nodes.map(
      (treeNode): EvidenceStarItem => ({
        id: treeNode.node_id,
        kind: "tree",
        label: treeNode.title,
        treeNode,
      })
    ),
    ...orderedPaths.map(
      (evidencePath): EvidenceStarItem => ({
        id: evidencePath.path_id,
        kind: "evidence",
        label: formatEvidenceType(evidencePath.evidence_type),
        evidencePath,
      })
    ),
  ];
  const byId = new Map(items.map((item) => [item.id, item]));

  const data: EvidenceChartNode[] = [];
  for (const node of tree.nodes) {
    const point = coordinates.get(node.node_id) ?? { x: 0, y: 0 };
    const style = treeNodeStyle(node);
    data.push({
      id: node.node_id,
      name: node.title,
      x: point.x,
      y: point.y,
      value: node.source_chunk_ids.length,
      symbol: style.symbol,
      symbolSize: style.size,
      category: node.node_type === "root" ? 0 : node.node_type === "section" ? 1 : 2,
      selected: selectedId === node.node_id,
      itemStyle: {
        color: style.color,
        borderColor: selectedId === node.node_id ? "#ffffff" : "rgba(255,255,255,0.7)",
        borderWidth: selectedId === node.node_id ? 3 : 1,
        shadowBlur: selectedId === node.node_id ? 34 : 20,
        shadowColor: style.glow,
      },
      label: {
        show: true,
        color: style.labelColor,
        fontFamily: MAP_FONT,
        fontSize: node.node_type === "root" ? 12 : 10,
        formatter: truncate(node.title, node.node_type === "root" ? 34 : 22),
        position: node.node_type === "root" ? "bottom" : "right",
      },
      starKind: "tree",
      subtitle:
        node.node_type === "root"
          ? "Paper root"
          : source === "paper_payload"
            ? "Live classification signal group"
          : `${formatEvidenceType(node.node_type)} · ${
              formatPageRange(node.page_start, node.page_end) ?? "No page"
            }`,
    });
  }

  for (const path of orderedPaths) {
    const point = coordinates.get(path.path_id) ?? { x: 0, y: 0 };
    const style = evidenceNodeStyle(path);
    data.push({
      id: path.path_id,
      name: formatEvidenceType(path.evidence_type),
      x: point.x,
      y: point.y,
      value: path.weight,
      symbol: "circle",
      symbolSize: style.size,
      category: path.polarity === "positive" ? 3 : 4,
      selected: selectedId === path.path_id,
      itemStyle: {
        color: style.color,
        borderColor: selectedId === path.path_id ? "#ffffff" : "rgba(255,255,255,0.72)",
        borderWidth: selectedId === path.path_id ? 3 : 1,
        shadowBlur: selectedId === path.path_id ? 38 : 24,
        shadowColor: style.glow,
      },
      label: {
        show: selectedId === path.path_id,
        color: path.polarity === "positive" ? "#c8f5df" : "#ffd8cc",
        fontFamily: MAP_FONT,
        fontSize: 10,
        formatter: truncate(formatEvidenceType(path.evidence_type), 25),
        position: "right",
      },
      starKind: "evidence",
      subtitle: `${formatEvidenceType(path.polarity)} · weight ${path.weight.toFixed(2)}`,
    });
  }

  const links: EvidenceChartLink[] = [];
  for (const node of tree.nodes) {
    if (!node.parent_node_id || !nodesById.has(node.parent_node_id)) continue;
    links.push({
      source: node.parent_node_id,
      target: node.node_id,
      value: "contains",
      lineStyle: {
        color: "rgba(141,198,230,0.34)",
        width: 1.2,
        opacity: 0.72,
        curveness: 0.08,
      },
    });
  }
  for (const path of orderedPaths) {
    if (!nodesById.has(path.node_id)) continue;
    const positive = path.polarity === "positive";
    links.push({
      source: path.node_id,
      target: path.path_id,
      value: path.evidence_type,
      lineStyle: {
        color: positive ? "rgba(119,221,178,0.52)" : "rgba(255,155,124,0.58)",
        width: Math.max(1.1, Math.min(3, 1.2 + Math.abs(path.weight) * 1.8)),
        opacity: 0.88,
        curveness: path.rank % 2 === 0 ? 0.12 : -0.12,
        type: path.metadata_status.includes("fallback") ? "dashed" : undefined,
      },
    });
  }

  const option = {
    backgroundColor: "transparent",
    animation: !reduceMotion,
    animationDuration: 600,
    animationEasing: "cubicOut",
    animationDurationUpdate: 280,
    animationEasingUpdate: "cubicInOut",
    aria: {
      enabled: true,
      label: {
        description:
          source === "paper_payload"
            ? "Interactive live classification signal map. The paper is at the center, signal groups form the inner orbit, and evidence signals form the outer orbit."
            : "Interactive attribution evidence star map. The paper is at the center, sections and sources form the inner orbit, and evidence paths form the outer orbit.",
      },
    },
    tooltip: {
      trigger: "item",
      renderMode: "richText",
      backgroundColor: "rgba(7,19,31,0.96)",
      borderColor: "rgba(141,198,230,0.35)",
      textStyle: { color: "#e7f1f7", fontFamily: MAP_FONT, fontSize: 11 },
      formatter: (params: { dataType?: string; data?: EvidenceChartNode | EvidenceChartLink }) => {
        if (params.dataType === "edge") {
          const edge = params.data as EvidenceChartLink | undefined;
          return edge?.value ?? "Evidence link";
        }
        const node = params.data as EvidenceChartNode | undefined;
        return node ? `${node.name}\n${node.subtitle}` : "";
      },
    },
    legend: { show: false },
    series: [
      {
        type: "graph",
        layout: "none",
        data,
        links,
        roam: true,
        draggable: false,
        selectedMode: "single",
        scaleLimit: { min: 0.42, max: 3.2 },
        edgeSymbol: ["none", "arrow"],
        edgeSymbolSize: [0, 5],
        categories: [
          { name: "Paper root", itemStyle: { color: ROOT_COLOR } },
          { name: "Section", itemStyle: { color: SECTION_COLOR } },
          {
            name: source === "paper_payload" ? "Signal group" : "Unlocated source",
            itemStyle: { color: SOURCE_COLOR },
          },
          { name: "Positive evidence", itemStyle: { color: POSITIVE_COLOR } },
          { name: "Negative evidence", itemStyle: { color: NEGATIVE_COLOR } },
        ],
        label: { show: true },
        select: {
          itemStyle: {
            borderColor: "#ffffff",
            borderWidth: 3,
          },
        },
        emphasis: {
          focus: "adjacency",
          scale: 1.35,
          lineStyle: { opacity: 1, width: 3 },
          label: { show: true },
        },
        blur: {
          itemStyle: { opacity: 0.24 },
          lineStyle: { opacity: 0.08 },
          label: { opacity: 0.2 },
        },
        lineStyle: { opacity: 0.7 },
      },
    ],
  };

  return { items, byId, option };
}
