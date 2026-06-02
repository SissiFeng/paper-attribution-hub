/**
 * Standalone full-viewport graph — opened as a new browser tab.
 * No sidebar, no navigation. Reads the same URL params as MultiGraphPage.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { EChart } from "@/components/EChart";
import { getMultiGraph } from "@/lib/api";
import type { MultiGraphPayload } from "@/types";

const TYPE_COLOR: Record<string, string> = {
  author: "#6594B1", institution: "#213C51", paper: "#DDAED3",
  topic: "#22c55e", method: "#f59e0b", funder: "#a78bfa", ac_core: "#ec4899",
};
const EDGE_COLOR: Record<string, string> = {
  authored: "rgba(101,148,177,0.55)", affiliated_with: "rgba(33,60,81,0.40)",
  belongs_to_topic: "rgba(34,197,94,0.45)", coauthored: "rgba(101,148,177,0.55)",
};
const DEFAULT_NODE_TYPES = ["author", "institution", "paper", "topic"];
const DEFAULT_EDGE_TYPES = ["authored", "affiliated_with", "belongs_to_topic"];
const AC_ATTRIBUTED_LABELS = ["CORE_RELEVANT", "RELATED_RELEVANT"];

export default function MultiGraphEmbed() {
  const [searchParams] = useSearchParams();
  const [payload, setPayload] = useState<MultiGraphPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeNodeTypes, setActiveNodeTypes] = useState<string[]>(DEFAULT_NODE_TYPES);
  const [activeEdgeTypes, setActiveEdgeTypes] = useState<string[]>(DEFAULT_EDGE_TYPES);
  const layoutKey = useRef(0);

  const yearFrom = Number(searchParams.get("year_from")) || 2021;
  const yearTo   = Number(searchParams.get("year_to"))   || 2025;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getMultiGraph({
        node_types: activeNodeTypes,
        edge_types: activeEdgeTypes,
        labels: AC_ATTRIBUTED_LABELS,
        group_by: "by_institution",
        hop_limit: 2,
        min_edge_weight: 0.3,
        year_from: yearFrom,
        year_to: yearTo,
      });
      setPayload(data);
      layoutKey.current += 1;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [activeNodeTypes, activeEdgeTypes, yearFrom, yearTo]);

  useEffect(() => { void load(); }, [load]);

  const option = useMemo(() => {
    if (!payload) return null;
    const paperInRange = new Set(
      payload.nodes
        .filter(n => n.type === "paper" &&
          (n.metadata.year as number) >= yearFrom &&
          (n.metadata.year as number) <= yearTo)
        .map(n => n.id)
    );
    const reachable = new Set(paperInRange);
    for (const e of payload.edges) {
      if (e.type === "authored" && paperInRange.has(e.target)) reachable.add(e.source);
      if (e.type === "belongs_to_topic" && paperInRange.has(e.source)) reachable.add(e.target);
    }
    for (const e of payload.edges) {
      if (e.type === "affiliated_with" && reachable.has(e.source)) reachable.add(e.target);
    }
    const visibleNodes = payload.nodes.filter(n => activeNodeTypes.includes(n.type) && reachable.has(n.id));
    const visibleIds = new Set(visibleNodes.map(n => n.id));
    const visibleEdges = payload.edges.filter(e =>
      activeEdgeTypes.includes(e.type) && visibleIds.has(e.source) && visibleIds.has(e.target)
    );
    const data = visibleNodes.map(n => ({
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
    const links = visibleEdges.map(e => ({
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
  }, [payload, activeNodeTypes, activeEdgeTypes, yearFrom, yearTo]);

  const toggle = (kind: "node" | "edge", t: string) => {
    if (kind === "node")
      setActiveNodeTypes(p => p.includes(t) ? p.filter(x => x !== t) : [...p, t]);
    else
      setActiveEdgeTypes(p => p.includes(t) ? p.filter(x => x !== t) : [...p, t]);
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

      {/* Full-height chart */}
      <div style={{ flex: 1, overflow: "hidden" }}>
        {error ? (
          <div style={{ padding: 24, color: "#f97316" }}>Error: {error}</div>
        ) : option ? (
          <EChart key={layoutKey.current} option={option} style={{ height: "100%", width: "100%" }} />
        ) : loading ? (
          <div style={{ padding: 24, color: "#9aa3b2" }}>Building graph…</div>
        ) : null}
      </div>
    </div>
  );
}
