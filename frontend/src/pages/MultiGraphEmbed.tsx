/**
 * Standalone full-viewport graph — opened as a new browser tab.
 * No sidebar, no navigation. Reads the same URL params as MultiGraphPage.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { AnalysisScopePanel } from "@/components/AnalysisScopePanel";
import { EChart } from "@/components/EChart";
import { getMultiGraph } from "@/lib/api";
import { filterFromSearchParams } from "@/lib/filter";
import {
  multiGraphProjectionFromSearchParams,
  multiGraphProjectionToSearchParams,
} from "@/lib/multiGraphUrl";
import {
  isLatestRequest,
  resultForScope,
  type ScopedResult,
} from "@/lib/scopedResult";
import type { MultiGraphPayload } from "@/types";

const TYPE_COLOR: Record<string, string> = {
  author: "#6594B1", institution: "#213C51", country: "#8b5cf6", paper: "#DDAED3",
  topic: "#22c55e", method: "#f59e0b", material: "#f0712c", instrument: "#5e4e96",
  software: "#0f766e", funder: "#a78bfa", ac_core: "#ec4899",
};
const EDGE_COLOR: Record<string, string> = {
  authored: "rgba(101,148,177,0.55)", affiliated_with: "rgba(33,60,81,0.40)",
  belongs_to_topic: "rgba(34,197,94,0.45)", coauthored: "rgba(101,148,177,0.55)",
  institution_collaboration: "rgba(167,139,250,0.45)",
  country_collaboration: "rgba(139,92,246,0.5)",
  published_by: "rgba(33,60,81,0.45)",
  cites: "rgba(221,174,211,0.55)",
  cites_ac_core: "rgba(236,72,153,0.65)",
  uses_method: "rgba(245,158,11,0.45)",
  mentions_material: "rgba(240,113,44,0.45)",
  mentions_instrument: "rgba(94,78,150,0.45)",
  mentions_software: "rgba(15,118,110,0.45)",
  covers_topic: "rgba(34,197,94,0.45)",
};
const DEFAULT_NODE_TYPES = [
  "author", "paper", "institution", "topic", "method", "material", "instrument", "software",
];
const DEFAULT_EDGE_TYPES = [
  "authored", "published_by", "belongs_to_topic", "uses_method",
  "mentions_material", "mentions_instrument", "mentions_software",
];

export default function MultiGraphEmbed() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [payloadResult, setPayloadResult] = useState<
    ScopedResult<MultiGraphPayload> | null
  >(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const layoutKey = useRef(0);
  const requestGeneration = useRef(0);

  const yearFrom = Number(searchParams.get("year_from")) || 2013;
  const yearTo   = Number(searchParams.get("year_to"))   || 2026;
  const searchKey = searchParams.toString();
  const payload = resultForScope(payloadResult, searchKey);
  const filter = useMemo(
    () => filterFromSearchParams(new URLSearchParams(searchKey)),
    [searchKey],
  );
  const currentProjection = useMemo(
    () => multiGraphProjectionFromSearchParams(
      new URLSearchParams(searchKey),
    ),
    [searchKey],
  );
  const {
    nodeTypes: activeNodeTypes,
    edgeTypes: activeEdgeTypes,
  } = currentProjection;

  const load = useCallback(async () => {
    const generation = ++requestGeneration.current;
    setLoading(true);
    setError(null);
    try {
      const data = await getMultiGraph({
        search: new URLSearchParams(searchKey),
        node_types: activeNodeTypes,
        edge_types: activeEdgeTypes,
        labels: filter.labels,
        group_by: currentProjection.groupBy,
        center_id: currentProjection.centerId || undefined,
        hop_limit: currentProjection.hopLimit,
        similarity_min: currentProjection.similarityMin,
        similarity_top_k: currentProjection.similarityTopK,
        min_edge_weight: currentProjection.minEdgeWeight,
        min_papers: currentProjection.minPapers,
        min_degree: currentProjection.minDegree,
        top_n: currentProjection.topN,
        excluded_node_ids: currentProjection.excludedNodeIds,
        year_from: yearFrom,
        year_to: yearTo,
      });
      if (isLatestRequest(generation, requestGeneration.current)) {
        setPayloadResult({ scopeKey: searchKey, payload: data });
        layoutKey.current += 1;
      }
    } catch (e) {
      if (isLatestRequest(generation, requestGeneration.current)) {
        setError(e instanceof Error ? e.message : String(e));
        setPayloadResult(null);
      }
    } finally {
      if (isLatestRequest(generation, requestGeneration.current)) setLoading(false);
    }
  }, [currentProjection, filter.labels, searchKey, yearFrom, yearTo]);

  useEffect(() => { void load(); }, [load]);

  const option = useMemo(() => {
    if (!payload || payload.nodes.length === 0) return null;
    const data = payload.nodes.map(n => ({
      id: n.id, name: n.label,
      symbolSize: n.type === "institution" ? 22 + Math.log1p((n.metadata?.paper_count as number) ?? 1) * 8 : 12,
      itemStyle: { color: TYPE_COLOR[n.type] ?? "#9ab1c4" },
      label: {
        show: ["institution", "topic"].includes(n.type),
        fontSize: 10, color: "#213C51",
        formatter: n.label.length > 22 ? n.label.slice(0, 20) + "…" : n.label,
      },
      node_id: n.id,
    }));
    const links = payload.edges.map(e => ({
      source: e.source, target: e.target,
      lineStyle: { color: EDGE_COLOR[e.type] ?? "rgba(101,148,177,0.3)", width: 0.8 + Math.log1p(e.weight) * 0.8 },
    }));
    return {
      backgroundColor: "#F8FAFC",
      tooltip: { trigger: "item" },
      series: [{
        type: "graph", layout: "force", data, links, roam: true, draggable: true,
        force: { repulsion: 320, edgeLength: [80, 260], gravity: 0.03, friction: 0.15 },
        emphasis: { focus: "adjacency", lineStyle: { width: 3, opacity: 1 }, scale: 1.3 },
        blur: { itemStyle: { opacity: 0.2 }, lineStyle: { opacity: 0.08 } },
      }],
    };
  }, [payload]);

  const toggle = (kind: "node" | "edge", t: string) => {
    const nodeTypes = kind === "node"
      ? (activeNodeTypes.includes(t)
        ? activeNodeTypes.filter((value) => value !== t)
        : [...activeNodeTypes, t])
      : activeNodeTypes;
    const edgeTypes = kind === "edge"
      ? (activeEdgeTypes.includes(t)
        ? activeEdgeTypes.filter((value) => value !== t)
        : [...activeEdgeTypes, t])
      : activeEdgeTypes;
    if (nodeTypes.length === 0 || edgeTypes.length === 0) return;
    setSearchParams(
      multiGraphProjectionToSearchParams(new URLSearchParams(searchKey), {
        ...currentProjection,
        nodeTypes,
        edgeTypes,
      }),
      { replace: false },
    );
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", background: "#F8FAFC" }}>
      {/* Compact toolbar */}
      <div style={{
        display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
        padding: "8px 14px", borderBottom: "1px solid #d1dce8", background: "#fff",
        fontSize: "0.75rem", flexShrink: 0,
      }}>
        <span style={{ fontWeight: 700, color: "#213C51", fontFamily: "'JetBrains Mono',monospace", marginRight: 6 }}>
          Multi-Entity Network {yearFrom}–{yearTo}
        </span>
        <span style={{ color: "#9ab1c4", marginRight: 8 }}>
          {payload ? `${payload.nodes.length} nodes · ${payload.edges.length} edges` : loading ? "Loading…" : ""}
        </span>
        <span style={{ color: "#657487", marginRight: 8 }}>
          {filter.labels.length === 0
            ? "all classifications"
            : filter.labels.map((label) => label.replace(/_/g, " ")).join(" + ")}
        </span>

        {/* Node toggles */}
        {(payload?.available_node_types ?? DEFAULT_NODE_TYPES).map(t => {
          const on = activeNodeTypes.includes(t);
          return (
            <button key={`n-${t}`} onClick={() => toggle("node", t)} style={{
              padding: "2px 9px", borderRadius: 14, fontSize: "0.72rem",
              fontFamily: "'JetBrains Mono',monospace", cursor: "pointer",
              border: `1.5px solid ${on ? TYPE_COLOR[t] : "#cdd5e0"}`,
              background: on ? `${TYPE_COLOR[t]}18` : "transparent",
              color: on ? TYPE_COLOR[t] : "#9aa3b2",
            }}>
              {t}
            </button>
          );
        })}

        <span style={{ color: "#cdd5e0" }}>|</span>

        {/* Edge toggles */}
        {(payload?.available_edge_types ?? DEFAULT_EDGE_TYPES).map(t => {
          const on = activeEdgeTypes.includes(t);
          return (
            <button key={`e-${t}`} onClick={() => toggle("edge", t)} style={{
              padding: "2px 9px", borderRadius: 14, fontSize: "0.72rem",
              fontFamily: "'JetBrains Mono',monospace", cursor: "pointer",
              border: `1.5px solid ${on ? "#6594B1" : "#cdd5e0"}`,
              background: on ? "rgba(101,148,177,0.10)" : "transparent",
              color: on ? "#213C51" : "#9aa3b2",
            }}>
              {t.replace(/_/g, " ")}
            </button>
          );
        })}

        <button onClick={() => void load()} disabled={loading} style={{
          marginLeft: "auto", padding: "2px 10px", borderRadius: 6,
          border: "1px solid #d1dce8", background: "#f8fafc", cursor: "pointer", fontSize: "0.72rem",
        }}>
          ↻ Refresh
        </button>
      </div>

      <div
        className={payload ? "multi-graph-embed-body with-audit" : "multi-graph-embed-body"}
      >
        {/* Full-height chart */}
        <div style={{ overflow: "hidden", position: "relative" }}>
          {loading && (
            <div style={{
              position: "absolute", inset: 0, display: "flex", alignItems: "center",
              justifyContent: "center", background: "#F8FAFC", zIndex: 10,
              color: "#6594B1", fontSize: 14, fontFamily: "'JetBrains Mono',monospace",
            }}>
              ↻ Building graph…
            </div>
          )}
          {error && (
            <div style={{
              position: "absolute", inset: 0, display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center", background: "#F8FAFC", zIndex: 10, gap: 12,
            }}>
              <div style={{ color: "#f97316", fontSize: 14, fontFamily: "'JetBrains Mono',monospace" }}>
                Failed to load graph: {error}
              </div>
              <button onClick={() => void load()} style={{
                padding: "6px 18px", borderRadius: 6, border: "1px solid #d1dce8",
                background: "#fff", cursor: "pointer", fontSize: 13,
              }}>
                ↻ Retry
              </button>
            </div>
          )}
          {option ? (
            <EChart key={layoutKey.current} option={option} style={{ height: "100%", width: "100%" }} />
          ) : !loading && !error ? (
            <div style={{
              position: "absolute", inset: 0, display: "flex", alignItems: "center",
              justifyContent: "center", color: "#9aa3b2", fontSize: 13,
              fontFamily: "'JetBrains Mono',monospace",
            }}>
              No data for the selected filters. Try adjusting node/edge types.
            </div>
          ) : null}
        </div>
        {payload && (
          <aside className="multi-graph-embed-audit">
            <AnalysisScopePanel audit={payload.audit} title="Graph evidence scope" />
          </aside>
        )}
      </div>
    </div>
  );
}
