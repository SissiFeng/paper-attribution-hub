import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { EChart } from "@/components/EChart";
import { NetworkGraph } from "@/components/NetworkGraph";
import { getCoauthorNetwork, getInstitutionNetwork } from "@/lib/api";
import type {
  InstitutionNetworkPayload,
  NetworkNode,
  NetworkPayload,
} from "@/types";

// ── Institution collaboration heatmap (replaces messy force-graph) ───────────
function buildInstHeatmapOption(payload: InstitutionNetworkPayload) {
  // Top-N nodes already capped by backend (top_n=50 default).
  // Sort by paper_count descending, take up to 30 for readability.
  const sorted = [...payload.nodes]
    .sort((a, b) => b.paper_count - a.paper_count)
    .slice(0, 30);

  const idxById: Record<string, number> = {};
  sorted.forEach((n, i) => { idxById[n.id] = i; });
  const labels = sorted.map((n) =>
    n.label.length > 22 ? n.label.slice(0, 20) + "…" : n.label
  );

  // Build edge lookup: (srcId, tgtId) → weight (symmetric)
  const edgeMap: Record<string, number> = {};
  for (const e of payload.edges) {
    const key1 = `${e.source}__${e.target}`;
    const key2 = `${e.target}__${e.source}`;
    edgeMap[key1] = e.weight;
    edgeMap[key2] = e.weight;
  }

  const data: [number, number, number][] = [];
  for (let i = 0; i < sorted.length; i++) {
    for (let j = 0; j < sorted.length; j++) {
      const w = i === j
        ? sorted[i].paper_count
        : (edgeMap[`${sorted[i].id}__${sorted[j].id}`] ?? 0);
      data.push([j, i, w]);  // ECharts heatmap: [col, row, value]
    }
  }

  const maxVal = Math.max(...data.map((d) => d[2]));

  return {
    tooltip: {
      formatter: (p: any) => {
        const row = sorted[p.data[1]];
        const col = sorted[p.data[0]];
        const v = p.data[2];
        if (!row || !col) return "";
        if (row.id === col.id)
          return `<b>${row.label}</b><br/>${v} papers`;
        return `<b>${row.label}</b><br/>↔ ${col.label}<br/><b>${v}</b> joint papers`;
      },
    },
    grid: { left: "26%", right: "4%", bottom: "26%", top: "4%" },
    xAxis: {
      type: "category",
      data: labels,
      splitArea: { show: true },
      axisLabel: {
        rotate: 45,
        color: "#9aa3b2",
        fontSize: 10,
        interval: 0,
      },
    },
    yAxis: {
      type: "category",
      data: labels,
      splitArea: { show: true },
      axisLabel: { color: "#9aa3b2", fontSize: 10 },
    },
    visualMap: {
      min: 0,
      max: maxVal,
      calculable: true,
      orient: "horizontal",
      left: "center",
      bottom: "2%",
      inRange: { color: ["#1e2330", "#3b4a6b", "#7aa2f7", "#34d399"] },
      textStyle: { color: "#9aa3b2" },
    },
    series: [
      {
        name: "Joint Papers",
        type: "heatmap",
        data,
        emphasis: { itemStyle: { shadowBlur: 10, shadowColor: "rgba(0,0,0,0.5)" } },
      },
    ],
  };
}

// ── Author detail panel ───────────────────────────────────────────────────────
function AuthorPanel({
  node,
  payload,
  onClose,
}: {
  node: NetworkNode;
  payload: NetworkPayload;
  onClose: () => void;
}) {
  const connectedEdges = payload.edges
    .filter((e) => e.source === node.id || e.target === node.id)
    .sort((a, b) => b.normalized_weight - a.normalized_weight);

  const neighbors = connectedEdges.map((e) => {
    const otherId = e.source === node.id ? e.target : e.source;
    const other = payload.nodes.find((n) => n.id === otherId);
    return { node: other!, edge: e };
  }).filter((x) => x.node);

  const isBridge = !node.is_ac_member && node.c_norm > 1.25;
  const pprPct = (node.ppr_score * 100).toFixed(1);

  return (
    <div style={{
      width: 272,
      flexShrink: 0,
      background: "var(--surface)",
      border: "1px solid var(--border)",
      borderRadius: 10,
      padding: "16px",
      fontSize: 13,
    }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
        <div>
          <div style={{ fontWeight: 600, fontSize: 14, color: "var(--text)" }}>{node.label}</div>
          <div style={{ color: "var(--muted)", marginTop: 2 }}>{node.institution ?? "—"}</div>
        </div>
        <button
          onClick={onClose}
          style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: 18, padding: 0, lineHeight: 1 }}
        >
          ×
        </button>
      </div>

      {/* Badges */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
        {node.is_ac_member && (
          <span style={{ padding: "2px 8px", borderRadius: 99, background: "rgba(52,211,153,0.15)", color: "#34d399", fontSize: 11, fontWeight: 600 }}>
            AC Member
          </span>
        )}
        {isBridge && (
          <span style={{ padding: "2px 8px", borderRadius: 99, background: "rgba(251,191,36,0.15)", color: "#fbbf24", fontSize: 11, fontWeight: 600 }}>
            ★ Bridge
          </span>
        )}
      </div>

      {/* Metrics */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 16 }}>
        <MetricBox label="Papers" value={String(node.paper_count)} />
        <MetricBox label="Collaborators" value={String(connectedEdges.length)} />
        <div style={{ gridColumn: "span 2" }}>
          <div style={{ color: "var(--muted)", fontSize: 11, marginBottom: 4 }}>
            AC Influence Score (PPR)
          </div>
          <div style={{ height: 6, background: "var(--border)", borderRadius: 3, overflow: "hidden" }}>
            <div style={{
              height: "100%",
              width: `${node.ppr_score * 100}%`,
              background: node.is_ac_member ? "var(--accent)" : "#7aa2f7",
              borderRadius: 3,
              transition: "width 0.4s",
            }} />
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 3, fontSize: 11, color: "var(--muted)" }}>
            <span>{pprPct}%</span>
            <span>c_norm {node.c_norm.toFixed(2)}</span>
          </div>
        </div>
      </div>

      {/* Collaborators list */}
      {neighbors.length > 0 && (
        <>
          <div style={{ color: "var(--muted)", fontSize: 11, marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Connections
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {neighbors.map(({ node: nb, edge }) => (
              <div key={nb.id} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{
                  width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
                  background: nb.is_ac_member ? "var(--accent)" : "var(--muted)",
                }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, color: "var(--text)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {nb.label}
                  </div>
                  <div style={{ height: 3, background: "var(--border)", borderRadius: 2, marginTop: 2, overflow: "hidden" }}>
                    <div style={{ height: "100%", width: `${edge.normalized_weight * 100}%`, background: edge.is_ac_ac ? "#34d399" : edge.involves_ac ? "#fbbf24" : "#7aa2f7", borderRadius: 2 }} />
                  </div>
                </div>
                <span style={{ fontSize: 11, color: "var(--muted)", flexShrink: 0 }}>
                  {(edge.normalized_weight * 100).toFixed(0)}%
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function MetricBox({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ background: "var(--bg)", borderRadius: 8, padding: "8px 10px" }}>
      <div style={{ color: "var(--muted)", fontSize: 11 }}>{label}</div>
      <div style={{ fontWeight: 600, fontSize: 18, color: "var(--text)", marginTop: 2 }}>{value}</div>
    </div>
  );
}

// ── PPR ranking strip ─────────────────────────────────────────────────────────
function PprRanking({
  nodes,
  onSelect,
}: {
  nodes: NetworkNode[];
  onSelect: (id: string) => void;
}) {
  const top = [...nodes]
    .filter((n) => !n.is_ac_member)
    .sort((a, b) => b.ppr_score - a.ppr_score)
    .slice(0, 8);

  if (top.length === 0) return null;

  return (
    <div style={{ marginTop: 20, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: "14px 16px" }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: "var(--muted)", marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.05em" }}>
        Top External Collaborators by AC Influence
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 8 }}>
        {top.map((n, i) => (
          <button
            key={n.id}
            onClick={() => onSelect(n.id)}
            style={{
              textAlign: "left", background: "var(--bg)", border: "1px solid var(--border)",
              borderRadius: 8, padding: "8px 10px", cursor: "pointer",
              display: "flex", flexDirection: "column", gap: 4,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ color: "var(--muted)", fontSize: 11, width: 16 }}>#{i + 1}</span>
              <span style={{ fontWeight: 600, fontSize: 13, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {n.label}
              </span>
              {n.c_norm > 1.25 && <span style={{ fontSize: 10, color: "#fbbf24" }}>★</span>}
            </div>
            <div style={{ height: 4, background: "var(--border)", borderRadius: 2, overflow: "hidden" }}>
              <div style={{ height: "100%", width: `${n.ppr_score * 100}%`, background: "#7aa2f7", borderRadius: 2 }} />
            </div>
            <div style={{ fontSize: 11, color: "var(--muted)" }}>
              PPR {(n.ppr_score * 100).toFixed(1)}% · {n.paper_count} papers
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
type View = "authors" | "institutions";

export default function CoauthorNetworkPage() {
  const [searchParams] = useSearchParams();
  const [view, setView] = useState<View>("authors");
  const [onlyRelevant, setOnlyRelevant] = useState(true);
  const [minPapers, setMinPapers] = useState(1);
  const [payload, setPayload] = useState<NetworkPayload | null>(null);
  const [instPayload, setInstPayload] = useState<InstitutionNetworkPayload | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Fetch author network
  useEffect(() => {
    let cancelled = false;
    setError(null);
    getCoauthorNetwork(onlyRelevant)
      .then((p) => { if (!cancelled) setPayload(p); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); });
    return () => { cancelled = true; };
  }, [onlyRelevant]);

  // Fetch institution network on demand
  useEffect(() => {
    if (view !== "institutions") return;
    let cancelled = false;
    getInstitutionNetwork(minPapers, searchParams)
      .then((p) => { if (!cancelled) setInstPayload(p); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [view, minPapers, searchParams.toString()]);

  const selectedNode = payload?.nodes.find((n) => n.id === selectedId) ?? null;

  return (
    <div>
      {/* View toggle */}
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        {(["authors", "institutions"] as View[]).map((v) => (
          <button
            key={v}
            className={view === v ? "active" : ""}
            onClick={() => { setView(v); setSelectedId(null); }}
            style={{
              padding: "5px 14px", borderRadius: 8, border: "1px solid var(--border)",
              background: view === v ? "var(--accent)" : "var(--surface)",
              color: view === v ? "#000" : "var(--text)",
              cursor: "pointer", fontSize: 13, fontWeight: 500,
            }}
          >
            {v === "authors" ? "👥 Authors" : "🏛 Institutions"}
          </button>
        ))}
      </div>

      {/* Controls row */}
      <div style={{ display: "flex", gap: 16, marginBottom: 12, fontSize: 13, alignItems: "center" }}>
        {view === "authors" && (
          <label style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--muted)" }}>
            <input
              type="checkbox"
              checked={onlyRelevant}
              onChange={(e) => { setOnlyRelevant(e.target.checked); setSelectedId(null); }}
            />
            Relevant papers only
          </label>
        )}
        {view === "institutions" && (
          <label style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--muted)" }}>
            Min joint papers:&nbsp;
            <input
              type="number" min={1} max={20} value={minPapers}
              onChange={(e) => setMinPapers(Math.max(1, Number(e.target.value)))}
              style={{ width: 60 }}
            />
          </label>
        )}
      </div>

      {error && <div style={{ color: "var(--uncertain)", marginBottom: 8 }}>Backend error: {error}</div>}

      {/* Graph + detail panel */}
      <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          {view === "authors" && payload && (
            <NetworkGraph
              payload={payload}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          )}
          {view === "institutions" && instPayload && instPayload.nodes.length > 0 && (
            <div>
              <p style={{ color: "var(--text-muted)", fontSize: 12, marginBottom: 8 }}>
                Top {Math.min(instPayload.nodes.length, 30)} institutions by joint papers.
                Diagonal = solo paper count · off-diagonal = co-authored papers.
              </p>
              <EChart option={buildInstHeatmapOption(instPayload)} style={{ height: 560 }} />
            </div>
          )}
          {view === "institutions" && instPayload && instPayload.nodes.length === 0 && (
            <div className="empty">No institutions match the current filter.</div>
          )}
        </div>

        {view === "authors" && selectedNode && payload && (
          <AuthorPanel
            node={selectedNode}
            payload={payload}
            onClose={() => setSelectedId(null)}
          />
        )}
      </div>

      {/* PPR ranking (authors view only) */}
      {view === "authors" && payload && (
        <PprRanking nodes={payload.nodes} onSelect={(id) => setSelectedId(id)} />
      )}
    </div>
  );
}
