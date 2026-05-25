import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { EChart } from "@/components/EChart";
import { TimeSlider } from "@/components/TimeSlider";
import { getMultiGraph } from "@/lib/api";
import type { MultiGraphPayload } from "@/types";

const TYPE_COLOR: Record<string, string> = {
  author:      "#6594B1",
  institution: "#213C51",
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
  paper:       "diamond",
  topic:       "triangle",
  method:      "pin",
  funder:      "rect",
  ac_core:     "diamond",
};

const TYPE_LABEL: Record<string, string> = {
  author:      "Authors",
  institution: "Institutions",
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
  institution_collab:"rgba(167,139,250,0.45)",
  covers_topic:      "rgba(34,197,94,0.45)",
};

const DEFAULT_NODE_TYPES = ["author", "institution", "paper", "topic"];
const DEFAULT_EDGE_TYPES = ["authored", "affiliated_with", "covers_topic", "cites"];

function colorForNode(node: MultiGraphPayload["nodes"][number]): string {
  if (node.type === "author" && node.metadata?.is_ac) return AC_AUTHOR_COLOR;
  if (node.type === "institution" && node.metadata?.is_partner) return PARTNER_INST_COLOR;
  return TYPE_COLOR[node.type] ?? "#9ab1c4";
}

function sizeForNode(node: MultiGraphPayload["nodes"][number]): number {
  const p = (node.metadata?.paper_count as number) ?? 1;
  if (node.type === "institution") return 22 + Math.log1p(p) * 8;
  if (node.type === "topic")       return 18 + Math.log1p(p) * 6;
  if (node.type === "author")      return 14 + Math.log1p(p) * 7;
  if (node.type === "paper")       return 12 + Math.log1p(p) * 4;
  return 12;
}

export default function MultiGraphPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [payload, setPayload] = useState<MultiGraphPayload | null>(null);
  const [loading, setLoading] = useState(false);

  const [activeNodeTypes, setActiveNodeTypes] = useState<string[]>(DEFAULT_NODE_TYPES);
  const [activeEdgeTypes, setActiveEdgeTypes] = useState<string[]>(DEFAULT_EDGE_TYPES);
  const [centerId, setCenterId] = useState<string | null>(searchParams.get("center"));
  const [hopLimit, setHopLimit] = useState(2);
  const [yearFrom, setYearFrom] = useState(Number(searchParams.get("year_from")) || 2021);
  const [yearTo,   setYearTo]   = useState(Number(searchParams.get("year_to"))   || 2025);

  useEffect(() => {
    const sp = new URLSearchParams(searchParams);
    sp.set("year_from", String(yearFrom));
    sp.set("year_to",   String(yearTo));
    if (centerId) sp.set("center", centerId);
    else sp.delete("center");
    setSearchParams(sp, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [yearFrom, yearTo, centerId]);

  // Fetch the full year range once per structural change; year filtering is done client-side
  // so the force layout doesn't restart when the TimeSlider moves.
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getMultiGraph({
        node_types: activeNodeTypes,
        edge_types: activeEdgeTypes,
        group_by: "institution",
        center_id: centerId || undefined,
        hop_limit: hopLimit,
        year_from: 2021,
        year_to: 2026,
      });
      setPayload(data);
    } finally {
      setLoading(false);
    }
  }, [activeNodeTypes, activeEdgeTypes, centerId, hopLimit]); // yearFrom/yearTo intentionally excluded

  useEffect(() => { void load(); }, [load]);

  // A stable key that changes only on structural param changes — causes EChart to remount
  // (fresh layout) for those, while year-only changes just merge into the live chart.
  const layoutKey = useRef(0);
  const prevStructural = useRef({ activeNodeTypes, activeEdgeTypes, centerId, hopLimit });
  const prev = prevStructural.current;
  if (
    prev.centerId !== centerId ||
    prev.hopLimit !== hopLimit ||
    prev.activeNodeTypes.join() !== activeNodeTypes.join() ||
    prev.activeEdgeTypes.join() !== activeEdgeTypes.join()
  ) {
    layoutKey.current += 1;
    prevStructural.current = { activeNodeTypes, activeEdgeTypes, centerId, hopLimit };
  }

  // ── Client-side filter: year + type ──────────────────────────────────────
  const option = useMemo(() => {
    if (!payload) return null;

    // Temporal reachability: start from papers in the year window, then derive
    // authors/institutions/topics/methods that connect to those papers.
    const paperInRange = new Set(
      payload.nodes
        .filter(n => n.type === "paper" &&
          (n.metadata.year as number) >= yearFrom &&
          (n.metadata.year as number) <= yearTo)
        .map(n => n.id)
    );

    const yearReachable: Set<string> = new Set(paperInRange);
    for (const e of payload.edges) {
      if (e.type === "authored"      && paperInRange.has(e.target)) yearReachable.add(e.source);
      if (e.type === "covers_topic"  && paperInRange.has(e.source)) yearReachable.add(e.target);
      if (e.type === "uses_method"   && paperInRange.has(e.source)) yearReachable.add(e.target);
    }
    // Institutions reachable from visible authors
    for (const e of payload.edges) {
      if (e.type === "affiliated_with" && yearReachable.has(e.source)) yearReachable.add(e.target);
    }

    // Filter nodes: active type AND temporally reachable
    const visibleNodes = payload.nodes.filter(n =>
      activeNodeTypes.includes(n.type) && yearReachable.has(n.id)
    );
    const visibleIds = new Set(visibleNodes.map(n => n.id));

    // Filter edges: type must be active AND both endpoints visible
    const visibleEdges = payload.edges.filter(e =>
      activeEdgeTypes.includes(e.type) &&
      visibleIds.has(e.source) &&
      visibleIds.has(e.target)
    );

    const data = visibleNodes.map(n => {
      const color = colorForNode(n);
      const size  = sizeForNode(n);
      const meta  = n.metadata as Record<string, unknown>;
      const isAC  = Boolean(meta?.is_ac);
      const isPrt = Boolean(meta?.is_partner);
      const tooltip = [
        `<b style="color:#213C51">${n.label}</b>`,
        `<span style="color:#6594B1">${n.type}</span>`,
        isAC  ? "AC member"        : null,
        isPrt ? "Partner institution" : null,
        meta?.paper_count ? `${meta.paper_count} papers` : null,
        meta?.country ? String(meta.country) : null,
        meta?.label   ? String(meta.label)   : null,
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
          show: ["institution", "topic"].includes(n.type) || isAC,
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
  }, [payload, activeNodeTypes, activeEdgeTypes, yearFrom, yearTo]);

  const onChartEvent = useMemo(() => ({
    click: (params: unknown) => {
      const id = (params as { data?: { node_id?: string } })?.data?.node_id;
      if (id) setCenterId(id);
    },
  }), []);

  const toggle = (kind: "node" | "edge", t: string) => {
    if (kind === "node") {
      setActiveNodeTypes(prev => prev.includes(t) ? prev.filter(x => x !== t) : [...prev, t]);
    } else {
      setActiveEdgeTypes(prev => prev.includes(t) ? prev.filter(x => x !== t) : [...prev, t]);
    }
  };

  const visibleNodeCount = useMemo(() =>
    payload?.nodes.filter(n => activeNodeTypes.includes(n.type)).length ?? 0,
  [payload, activeNodeTypes]);

  const visibleEdgeCount = useMemo(() => {
    if (!payload) return 0;
    const ids = new Set(payload.nodes.filter(n => activeNodeTypes.includes(n.type)).map(n => n.id));
    return payload.edges.filter(e =>
      activeEdgeTypes.includes(e.type) && ids.has(e.source) && ids.has(e.target)
    ).length;
  }, [payload, activeNodeTypes, activeEdgeTypes]);

  return (
    <div className="v7-page">
      <div className="v7-hero">
        <div>
          <h1>Multi-Entity Network</h1>
          <p>
            Authors · institutions · papers · topics in one force-directed graph.
            Toggle layers below, click any node to focus its ego network.
          </p>
        </div>
        <div className="v7-hero-actions">
          {centerId && (
            <button className="v7-btn" onClick={() => setCenterId(null)}>
              ✕ Clear focus
            </button>
          )}
          <button className="v7-btn" onClick={() => void load()} disabled={loading}>
            ↻ Refresh
          </button>
        </div>
      </div>

      <TimeSlider
        minYear={2021} maxYear={2026}
        yearFrom={yearFrom} yearTo={yearTo}
        onChange={(yf, yt) => { setYearFrom(yf); setYearTo(yt); }}
      />

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
              onChange={e => setHopLimit(Number(e.target.value))}
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
          <div className="delta">{activeNodeTypes.length} type{activeNodeTypes.length !== 1 ? "s" : ""} shown</div>
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

      <div className="v7-chart-frame tall" style={{ background: "#F8FAFC", borderRadius: 14, border: "1px solid var(--border)", overflow: "hidden" }}>
        {loading && !payload ? (
          <div style={{ padding: 16 }}>
            <div className="v7-skel card" style={{ height: 560 }} />
          </div>
        ) : option ? (
          <EChart
            key={layoutKey.current}
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

      {/* Legend */}
      <div className="v7-card" style={{ display: "flex", flexWrap: "wrap", gap: "1rem", padding: "12px 16px", fontSize: "0.78rem", color: "var(--muted)" }}>
        <span style={{ fontWeight: 600, color: "var(--text)", marginRight: 4 }}>Legend:</span>
        {Object.entries(TYPE_LABEL).map(([type, label]) => (
          <span key={type} style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
            <span style={{ width: 10, height: 10, borderRadius: type === "institution" ? 2 : "50%", background: TYPE_COLOR[type] }} />
            {label}
          </span>
        ))}
        <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
          <span style={{ width: 10, height: 10, borderRadius: "50%", background: AC_AUTHOR_COLOR, boxShadow: "0 0 0 2px rgba(255,255,255,0.8)" }} />
          AC member (border)
        </span>
      </div>
    </div>
  );
}
