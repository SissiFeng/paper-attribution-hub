import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { AnalysisScopePanel } from "@/components/AnalysisScopePanel";
import { EChart } from "@/components/EChart";
import { FilterBar } from "@/components/FilterBar";
import { TimeSlider } from "@/components/TimeSlider";
import { getMultiGraph } from "@/lib/api";
import { filterFromSearchParams } from "@/lib/filter";
import { escapeHtml } from "@/lib/html";
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
  author:      "#6594B1",
  institution: "#213C51",
  country:     "#8b5cf6",
  paper:       "#DDAED3",
  topic:       "#22c55e",
  method:      "#f59e0b",
  funder:      "#a78bfa",
  ac_core:     "#ec4899",
};

const AC_AUTHOR_COLOR      = "#213C51";
const PARTNER_INST_COLOR   = "#6594B1";

const TYPE_SYMBOL: Record<string, string> = {
  author:      "circle",
  institution: "roundRect",
  country:     "hexagon",
  paper:       "diamond",
  topic:       "triangle",
  method:      "pin",
  funder:      "rect",
  ac_core:     "diamond",
};

const TYPE_LABEL: Record<string, string> = {
  author:      "Authors",
  institution: "Institutions",
  country:     "Countries",
  paper:       "Papers",
  topic:       "Topics",
  method:      "Methods",
  funder:      "Funders",
  ac_core:     "AC core",
};

const EDGE_COLOR: Record<string, string> = {
  authored:          "rgba(101,148,177,0.55)",
  coauthored:        "rgba(101,148,177,0.55)",
  affiliated_with:   "rgba(33,60,81,0.40)",
  belongs_to_topic:  "rgba(34,197,94,0.45)",
  cites:             "rgba(221,174,211,0.55)",
  cites_ac_core:     "rgba(236,72,153,0.65)",
  uses_method:       "rgba(245,158,11,0.45)",
  institution_collaboration: "rgba(167,139,250,0.45)",
  country_collaboration: "rgba(139,92,246,0.5)",
  published_by: "rgba(33,60,81,0.45)",
  covers_topic:      "rgba(34,197,94,0.45)",
};

const DEFAULT_NODE_TYPES = ["author", "paper"];
const DEFAULT_EDGE_TYPES = ["authored"];
const VIEW_PRESETS = [
  { id: "authors", label: "Authors", nodes: ["author"], edges: ["coauthored"] },
  { id: "institutions", label: "Institutions", nodes: ["institution"], edges: ["institution_collaboration"] },
  { id: "countries", label: "Countries", nodes: ["country"], edges: ["country_collaboration"] },
  { id: "author-papers", label: "Authors + papers", nodes: ["author", "paper"], edges: ["authored"] },
  { id: "institution-papers", label: "Institutions + papers", nodes: ["institution", "paper"], edges: ["published_by"] },
  { id: "topic-papers", label: "Topics + papers", nodes: ["topic", "paper"], edges: ["belongs_to_topic"] },
] as const;

function colorForNode(node: MultiGraphPayload["nodes"][number]): string {
  if (node.type === "author" && (node.metadata?.is_ac || node.metadata?.is_ac_member)) return AC_AUTHOR_COLOR;
  if (node.type === "institution" && node.metadata?.is_partner) return PARTNER_INST_COLOR;
  return TYPE_COLOR[node.type] ?? "#9ab1c4";
}

function sizeForNode(node: MultiGraphPayload["nodes"][number]): number {
  const p = (node.metadata?.paper_count as number) ?? 1;
  if (node.type === "institution") return 22 + Math.log1p(p) * 8;
  if (node.type === "country")     return 24 + Math.log1p(p) * 8;
  if (node.type === "topic")       return 18 + Math.log1p(p) * 6;
  if (node.type === "author")      return 14 + Math.log1p(p) * 7;
  if (node.type === "paper")       return 12 + Math.log1p(p) * 4;
  return 12;
}

export default function MultiGraphPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [payloadResult, setPayloadResult] = useState<
    ScopedResult<MultiGraphPayload> | null
  >(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [entitySearch, setEntitySearch] = useState("");
  const requestGeneration = useRef(0);
  const yearFrom = Number(searchParams.get("year_from")) || 2021;
  const yearTo = Number(searchParams.get("year_to")) || 2025;
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
    centerId,
    hopLimit,
    minPapers,
    minDegree,
    topN,
    excludedNodeIds,
  } = currentProjection;

  const updateProjection = useCallback((
    patch: Partial<typeof currentProjection>,
    replace = false,
  ) => {
    setSearchParams(
      multiGraphProjectionToSearchParams(
        new URLSearchParams(searchKey),
        { ...currentProjection, ...patch },
      ),
      { replace },
    );
  }, [currentProjection, searchKey, setSearchParams]);

  const openEmbed = () => {
    const params = multiGraphProjectionToSearchParams(
      new URLSearchParams(searchKey),
      currentProjection,
    );
    params.set("year_from", String(yearFrom));
    params.set("year_to", String(yearTo));
    window.open(`/multi-graph/embed?${params.toString()}`, "_blank");
  };

  const setYearRange = (nextYearFrom: number, nextYearTo: number) => {
    const next = new URLSearchParams(searchParams);
    next.set("year_from", String(nextYearFrom));
    next.set("year_to", String(nextYearTo));
    setSearchParams(next, { replace: true });
  };

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
        center_id: centerId || undefined,
        hop_limit: hopLimit,
        min_edge_weight: currentProjection.minEdgeWeight,
        min_papers: minPapers,
        min_degree: minDegree,
        top_n: topN,
        excluded_node_ids: excludedNodeIds,
        similarity_min: currentProjection.similarityMin,
        similarity_top_k: currentProjection.similarityTopK,
        year_from: yearFrom,
        year_to: yearTo,
      });
      if (isLatestRequest(generation, requestGeneration.current)) {
        setPayloadResult({ scopeKey: searchKey, payload: data });
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
    const visibleNodes = payload.nodes;
    const visibleEdges = payload.edges;

    const data = visibleNodes.map(n => {
      const color = colorForNode(n);
      const size  = sizeForNode(n);
      const meta  = n.metadata as Record<string, unknown>;
      const isAC  = Boolean(meta?.is_ac || meta?.is_ac_member);
      const isPrt = Boolean(meta?.is_partner || meta?.has_partner_institution);
      const tooltip = [
        `<b style="color:#213C51">${escapeHtml(n.label)}</b>`,
        `<span style="color:#6594B1">${escapeHtml(n.type)}</span>`,
        isAC  ? "AC member"        : null,
        isPrt ? "Partner institution" : null,
        meta?.paper_count ? `${meta.paper_count} papers` : null,
        meta?.country ? escapeHtml(meta.country) : null,
        meta?.label   ? escapeHtml(meta.label)   : null,
      ].filter(Boolean).join("<br>");

      return {
        id: n.id,
        name: n.label,
        category: n.type,
        symbolSize: size,
        symbol: TYPE_SYMBOL[n.type] ?? "circle",
        itemStyle: {
          color,
          borderColor: "rgba(255,255,255,0.6)",
          borderWidth: isAC || isPrt ? 2 : 0,
          shadowBlur: isAC || isPrt ? 18 : 6,
          shadowColor: isAC ? "rgba(33,60,81,0.5)" : isPrt ? "rgba(101,148,177,0.5)" : "rgba(0,0,0,0.15)",
        },
        label: {
          show: ["institution", "country", "topic"].includes(n.type) || isAC,
          fontSize: n.type === "institution" ? 12 : 10,
          fontWeight: isAC ? 600 : 400,
          color: "#213C51",
          fontFamily: "'JetBrains Mono', monospace",
          formatter: n.label.length > 22 ? n.label.slice(0, 20) + "…" : n.label,
        },
        tooltip: { formatter: () => `<div style="font-family:'JetBrains Mono',monospace;font-size:12px;padding:4px">${tooltip}</div>` },
        node_id: n.id,
        node_type: n.type,
      };
    });

    const links = visibleEdges.map(e => ({
      source: e.source,
      target: e.target,
      lineStyle: {
        color: EDGE_COLOR[e.type] ?? "rgba(101,148,177,0.3)",
        width: 0.8 + Math.log1p(e.weight) * 1.0,
        curveness: 0.18,
        opacity: 0.75,
      },
      value: e.type,
    }));

    return {
      backgroundColor: "#F8FAFC",
      tooltip: { trigger: "item" },
      animationDurationUpdate: 700,
      animationEasingUpdate: "cubicInOut",
      series: [
        {
          type: "graph",
          layout: "force",
          data,
          links,
          roam: true,
          draggable: true,
          force: {
            repulsion: 280,
            edgeLength: [80, 240],
            gravity: 0.03,
            friction: 0.15,
            layoutAnimation: true,
          },
          emphasis: {
            focus: "adjacency",
            lineStyle: { width: 3, opacity: 1 },
            scale: 1.25,
          },
          blur: { itemStyle: { opacity: 0.25 }, lineStyle: { opacity: 0.1 } },
          lineStyle: { curveness: 0.18 },
          categories: Object.keys(TYPE_COLOR).map(t => ({
            name: t,
            itemStyle: { color: TYPE_COLOR[t] },
          })),
        },
      ],
    };
  }, [payload]);

  const onChartEvent = useMemo(() => ({
    click: (params: unknown) => {
      const id = (params as { data?: { node_id?: string } })?.data?.node_id;
      if (id) updateProjection({ centerId: id });
    },
  }), [updateProjection]);

  const toggle = (kind: "node" | "edge", t: string) => {
    if (kind === "node") {
      const next = activeNodeTypes.includes(t)
        ? activeNodeTypes.filter((value) => value !== t)
        : [...activeNodeTypes, t];
      if (next.length > 0) updateProjection({ nodeTypes: next });
    } else {
      const next = activeEdgeTypes.includes(t)
        ? activeEdgeTypes.filter((value) => value !== t)
        : [...activeEdgeTypes, t];
      if (next.length > 0) updateProjection({ edgeTypes: next });
    }
  };

  const visibleNodeCount = payload?.nodes.length ?? 0;
  const visibleEdgeCount = payload?.edges.length ?? 0;
  const removableNodes = useMemo(() => {
    const needle = entitySearch.trim().toLocaleLowerCase();
    return (payload?.nodes ?? [])
      .filter((node) => node.type === "author" || node.type === "institution")
      .filter((node) => !needle || node.label.toLocaleLowerCase().includes(needle))
      .sort((left, right) => (
        Number(right.metadata?.paper_count ?? 0) - Number(left.metadata?.paper_count ?? 0)
        || left.label.localeCompare(right.label)
        || left.id.localeCompare(right.id)
      ));
  }, [entitySearch, payload]);

  const hideNode = (nodeId: string) => updateProjection({
    excludedNodeIds: [...new Set([...excludedNodeIds, nodeId])],
    centerId: centerId === nodeId ? null : centerId,
  });

  return (
    <div className="v7-page">
      <FilterBar />
      <div className="v7-hero">
        <div>
          <h1>Multi-Entity Network</h1>
          <p>
            Filtered paper evidence linked to the selected entity and relationship
            types, with a replayable scope and projection audit.
          </p>
        </div>
        <div className="v7-hero-actions">
          {centerId && (
            <button className="v7-btn" onClick={() => updateProjection({ centerId: null })}>
              ✕ Clear focus
            </button>
          )}
          <button className="v7-btn" onClick={() => void load()} disabled={loading}>
            ↻ Refresh
          </button>
          <button className="v7-btn" onClick={openEmbed} title="Open graph in new tab (no sidebar)">
            ⧉ New tab
          </button>
        </div>
      </div>

      <TimeSlider
        minYear={2021} maxYear={2026}
        yearFrom={yearFrom} yearTo={yearTo}
        onChange={setYearRange}
      />

      <div className="v7-graph-toolbar" aria-label="Graph view presets">
        <span className="toolbar-label">View</span>
        {VIEW_PRESETS.map((preset) => {
          const selected = preset.nodes.join() === activeNodeTypes.join() && preset.edges.join() === activeEdgeTypes.join();
          return (
            <button
              type="button"
              key={preset.id}
              className={`v7-toggle ${selected ? "on" : ""}`}
              aria-pressed={selected}
              onClick={() => {
                updateProjection({
                  nodeTypes: [...preset.nodes],
                  edgeTypes: [...preset.edges],
                  centerId: null,
                });
              }}
            >
              {preset.label}
            </button>
          );
        })}
      </div>

      <div className="v7-graph-toolbar graph-thresholds" aria-label="Network thresholds">
        <span className="toolbar-label">Thresholds</span>
        <label>Min papers <input type="number" min={1} max={100} value={minPapers} onChange={(event) => updateProjection({ minPapers: Math.max(1, Number(event.target.value)) }, true)} /></label>
        <label>Min degree <input type="number" min={0} max={100} value={minDegree} onChange={(event) => updateProjection({ minDegree: Math.max(0, Number(event.target.value)) }, true)} /></label>
        <label>Top N/type <input type="number" min={1} max={500} value={topN} onChange={(event) => updateProjection({ topN: Math.max(1, Number(event.target.value)) }, true)} /></label>
      </div>

      {error && (
        <div className="v7-card" style={{ borderColor: "rgba(249,115,22,0.4)" }}>
          Backend error: {error}
        </div>
      )}

      {/* Node type toggles */}
      <div className="v7-graph-toolbar">
        <span className="toolbar-label">Nodes</span>
        {(payload?.available_node_types ?? DEFAULT_NODE_TYPES).map(t => {
          const on = activeNodeTypes.includes(t);
          return (
            <button
              key={`n-${t}`}
              onClick={() => toggle("node", t)}
              style={{
                display: "inline-flex", alignItems: "center", gap: 6,
                padding: "4px 10px", borderRadius: 20, fontSize: "0.75rem",
                fontFamily: "'JetBrains Mono', monospace", cursor: "pointer",
                border: `1.5px solid ${on ? TYPE_COLOR[t] : "rgba(33,60,81,0.15)"}`,
                background: on ? `${TYPE_COLOR[t]}18` : "transparent",
                color: on ? TYPE_COLOR[t] : "#9ab1c4",
                fontWeight: on ? 600 : 400,
                transition: "all 120ms",
              }}
            >
              <span style={{
                width: 8, height: 8, borderRadius: "50%",
                background: on ? TYPE_COLOR[t] : "#d1d9e0",
                flexShrink: 0,
              }} />
              {TYPE_LABEL[t] ?? t}
            </button>
          );
        })}
      </div>

      {/* Edge type toggles */}
      <div className="v7-graph-toolbar">
        <span className="toolbar-label">Edges</span>
        {(payload?.available_edge_types ?? DEFAULT_EDGE_TYPES).map(t => {
          const on = activeEdgeTypes.includes(t);
          return (
            <button
              key={`e-${t}`}
              onClick={() => toggle("edge", t)}
              style={{
                display: "inline-flex", alignItems: "center", gap: 6,
                padding: "4px 10px", borderRadius: 20, fontSize: "0.75rem",
                fontFamily: "'JetBrains Mono', monospace", cursor: "pointer",
                border: `1.5px solid ${on ? "#6594B1" : "rgba(33,60,81,0.15)"}`,
                background: on ? "rgba(101,148,177,0.10)" : "transparent",
                color: on ? "#213C51" : "#9ab1c4",
                transition: "all 120ms",
              }}
            >
              {t.replace(/_/g, " ")}
            </button>
          );
        })}
        {centerId && (
          <span style={{ marginLeft: "auto", color: "var(--muted)", fontSize: "0.8rem" }}>
            Ego graph · hops:&nbsp;
            <select
              value={hopLimit}
              onChange={e => updateProjection({ hopLimit: Number(e.target.value) })}
              style={{ fontFamily: "inherit", border: "1px solid var(--border)", borderRadius: 4, padding: "1px 4px" }}
            >
              <option value={1}>1</option>
              <option value={2}>2</option>
              <option value={3}>3</option>
            </select>
          </span>
        )}
      </div>

      <div className="v7-stat-grid">
        <div className="v7-stat">
          <div className="label">Visible nodes</div>
          <div className="value">{visibleNodeCount}</div>
          <div className="delta">
            {filter.labels.length === 0
              ? "All classifications"
              : filter.labels.map((label) => label.replace(/_/g, " ")).join(" + ")}
          </div>
        </div>
        <div className="v7-stat">
          <div className="label">Visible edges</div>
          <div className="value">{visibleEdgeCount}</div>
          <div className="delta">{activeEdgeTypes.length} edge type{activeEdgeTypes.length !== 1 ? "s" : ""} active</div>
        </div>
        <div className="v7-stat">
          <div className="label">Communities</div>
          <div className="value">{payload?.groups.length ?? 0}</div>
          <div className="delta">{payload?.groups[0]?.label ?? "—"}</div>
        </div>
      </div>

      <div className="multi-graph-workspace">
        <aside className="multi-graph-entity-panel" aria-label="Visible author and institution nodes">
          <div className="multi-graph-entity-head">
            <div>
              <span className="review-kicker">Graph cleanup</span>
              <strong>Authors & institutions</strong>
            </div>
            {excludedNodeIds.length > 0 && (
              <button
                type="button"
                className="ghost-button"
                onClick={() => updateProjection({ excludedNodeIds: [] })}
              >
                Restore {excludedNodeIds.length}
              </button>
            )}
          </div>
          <input
            type="search"
            value={entitySearch}
            onChange={(event) => setEntitySearch(event.target.value)}
            placeholder="Search visible names…"
            aria-label="Search visible authors and institutions"
          />
          <p>
            Hide outliers from this projection without changing stored evidence.
            Hidden node IDs are retained in the URL and audit.
          </p>
          <div className="multi-graph-entity-list">
            {removableNodes.map((node) => (
              <div key={node.id}>
                <span>
                  <strong>{node.label}</strong>
                  <small>{TYPE_LABEL[node.type] ?? node.type} · {Number(node.metadata?.paper_count ?? 0)} papers</small>
                </span>
                <button
                  type="button"
                  onClick={() => hideNode(node.id)}
                  aria-label={`Hide ${node.label}`}
                  title={`Hide ${node.label} from this graph projection`}
                >
                  Hide
                </button>
              </div>
            ))}
            {removableNodes.length === 0 && (
              <div className="metric-note">No matching author or institution nodes.</div>
            )}
          </div>
        </aside>
        <div className="v7-chart-frame tall" style={{ background: "#F8FAFC", borderRadius: 14, border: "1px solid var(--border)", overflow: "hidden" }}>
          {loading && !payload ? (
            <div style={{ padding: 16 }}>
              <div className="v7-skel card" style={{ height: 560 }} />
            </div>
          ) : option ? (
            <EChart
              key={`${activeNodeTypes.join("-")}:${activeEdgeTypes.join("-")}:${yearFrom}-${yearTo}:${minPapers}:${minDegree}:${topN}:${centerId ?? "all"}:${excludedNodeIds.join("-")}`}
              option={option}
              notMerge={false}
              style={{ height: "100%", width: "100%" }}
              onEvents={onChartEvent}
            />
          ) : (
            <div className="v7-empty">
              <div>No graph data. Try enabling more node or edge types.</div>
            </div>
          )}
        </div>
      </div>

      {payload && <AnalysisScopePanel audit={payload.audit} title="Graph evidence scope" />}

      {/* Legend */}
      <div className="v7-card" style={{ display: "flex", flexWrap: "wrap", gap: "1rem", padding: "12px 16px", fontSize: "0.78rem", color: "var(--muted)" }}>
        <span style={{ fontWeight: 600, color: "var(--text)", marginRight: 4 }}>Legend:</span>
        {Object.entries(TYPE_LABEL).map(([type, label]) => (
          <span key={type} style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
            <span style={{ width: 10, height: 10, borderRadius: type === "institution" ? 2 : "50%", background: TYPE_COLOR[type] }} />
            {label} · {TYPE_SYMBOL[type] ?? "circle"}
          </span>
        ))}
        <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
          <span style={{ width: 10, height: 10, borderRadius: "50%", background: AC_AUTHOR_COLOR, boxShadow: "0 0 0 2px rgba(255,255,255,0.8)" }} />
          AC member (border)
        </span>
      </div>

      <details className="v7-card graph-explanation">
        <summary>How to read the graph</summary>
        <p>
          Author-only uses co-authorship; institution-only and country-only use
          shared-paper collaboration. Institution + papers uses published-by,
          author + papers uses authored-by, and topic + papers uses topic membership.
        </p>
        <p>
          Node size is distinct-paper support. Min papers removes low-support
          entities, min degree removes weakly connected entities, and Top N keeps
          the strongest entities per type. Clicking a node creates a replayable ego graph.
        </p>
      </details>

    </div>
  );
}
