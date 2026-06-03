import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { EChart } from "@/components/EChart";
import { NetworkGraph } from "@/components/NetworkGraph";
import { getCoauthorNetwork, getInstitutionNetwork } from "@/lib/api";
import type {
  ImportanceRadarAxis,
  InstitutionNetworkPayload,
  NetworkNode,
  NetworkPayload,
} from "@/types";

const IMPORTANCE_DIMENSIONS = [
  { key: "ac_proximity", label: "AC proximity" },
  { key: "relationship_strength", label: "Relationship strength" },
  { key: "excess_centrality", label: "Excess centrality" },
  { key: "cross_sdl_diversity", label: "Cross-SDL diversity" },
  { key: "citation_affinity", label: "Citation affinity" },
  { key: "recency", label: "Recency" },
] as const;

const IMPORTANCE_PROFILES: Record<string, { label: string; purpose: string; weights: Record<string, number> }> = {
  ac_attribution: {
    label: "AC attribution",
    purpose: "Prioritize authors structurally close to AC and directly attributable to AC work.",
    weights: { ac_proximity: 0.55, relationship_strength: 0.20, citation_affinity: 0.15, recency: 0.10 },
  },
  bridge_builders: {
    label: "Bridge builders",
    purpose: "Surface authors who connect AC-adjacent communities across SDL contexts.",
    weights: { ac_proximity: 0.35, excess_centrality: 0.30, cross_sdl_diversity: 0.25, relationship_strength: 0.10 },
  },
  institution_hubs: {
    label: "Institution hubs",
    purpose: "Emphasize durable collaboration strength and institution-spanning centrality.",
    weights: { relationship_strength: 0.30, excess_centrality: 0.25, cross_sdl_diversity: 0.20, ac_proximity: 0.15, citation_affinity: 0.10 },
  },
  emerging_connectors: {
    label: "Emerging connectors",
    purpose: "Find newer authors with recent activity and early bridge potential.",
    weights: { recency: 0.30, excess_centrality: 0.25, cross_sdl_diversity: 0.20, ac_proximity: 0.15, relationship_strength: 0.10 },
  },
  topic_diffusion: {
    label: "Topic diffusion",
    purpose: "Highlight cross-SDL spread and collaborations that move methods between areas.",
    weights: { cross_sdl_diversity: 0.35, relationship_strength: 0.20, excess_centrality: 0.20, ac_proximity: 0.15, recency: 0.10 },
  },
};

function weightsForProfile(profile: string): Record<string, number> {
  const base = IMPORTANCE_PROFILES[profile]?.weights ?? IMPORTANCE_PROFILES.bridge_builders.weights;
  return Object.fromEntries(IMPORTANCE_DIMENSIONS.map((d) => [d.key, base[d.key] ?? 0]));
}

function normalizeWeights(weights: Record<string, number>): Record<string, number> {
  const clean = Object.fromEntries(
    IMPORTANCE_DIMENSIONS.map((d) => [d.key, Math.max(0, weights[d.key] ?? 0)])
  );
  const total = Object.values(clean).reduce((sum, value) => sum + value, 0);
  if (total <= 0) return weightsForProfile("bridge_builders");
  return Object.fromEntries(Object.entries(clean).map(([key, value]) => [key, value / total]));
}

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

function ImportanceWeightEditor({
  profile,
  weights,
  onProfileChange,
  onWeightsChange,
}: {
  profile: string;
  weights: Record<string, number>;
  onProfileChange: (profile: string) => void;
  onWeightsChange: (weights: Record<string, number>) => void;
}) {
  const normalized = normalizeWeights(weights);
  const activeProfile = IMPORTANCE_PROFILES[profile] ?? IMPORTANCE_PROFILES.bridge_builders;
  const total = Object.values(weights).reduce((sum, value) => sum + value, 0);

  return (
    <section className="importance-editor" aria-label="Node importance weight editor">
      <div className="importance-editor-head">
        <div>
          <div className="section-kicker">Node importance profile</div>
          <h2>Weight editor</h2>
          <p>{activeProfile.purpose}</p>
        </div>
        <button
          type="button"
          className="ghost-button"
          onClick={() => onWeightsChange(weightsForProfile(profile))}
          title="Reset weights to the selected profile"
        >
          Reset
        </button>
      </div>

      <div className="profile-grid" role="list">
        {Object.entries(IMPORTANCE_PROFILES).map(([key, item]) => (
          <button
            type="button"
            key={key}
            className={key === profile ? "profile-chip active" : "profile-chip"}
            onClick={() => onProfileChange(key)}
            title={item.purpose}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="weight-grid">
        {IMPORTANCE_DIMENSIONS.map((dimension) => {
          const value = normalized[dimension.key] ?? 0;
          return (
            <label key={dimension.key} className="weight-row">
              <span>
                <strong>{dimension.label}</strong>
                <small>{(value * 100).toFixed(0)}%</small>
              </span>
              <input
                type="range"
                min={0}
                max={100}
                step={1}
                value={Math.round(value * 100)}
                onChange={(event) => {
                  const next = {
                    ...normalized,
                    [dimension.key]: Number(event.target.value) / 100,
                  };
                  onWeightsChange(normalizeWeights(next));
                }}
              />
            </label>
          );
        })}
      </div>

      <div className="weight-footer">
        <span>Normalized total {(total > 0 ? 1 : 0).toFixed(0)}. Scores recompute server-side.</span>
        <span>{IMPORTANCE_DIMENSIONS.length} dimensions</span>
      </div>
    </section>
  );
}

function ImportanceRadar({ axes }: { axes?: ImportanceRadarAxis[] }) {
  const radarAxes = axes?.length ? axes : IMPORTANCE_DIMENSIONS.map((d) => ({
    key: d.key,
    label: d.label,
    value: 0,
    weight: 0,
  }));
  const size = 176;
  const center = size / 2;
  const radius = 58;
  const points = radarAxes.map((axis, i) => {
    const angle = -Math.PI / 2 + (i / radarAxes.length) * Math.PI * 2;
    const valueRadius = radius * Math.max(0, Math.min(1, axis.value ?? 0));
    return {
      ...axis,
      x: center + Math.cos(angle) * valueRadius,
      y: center + Math.sin(angle) * valueRadius,
      lx: center + Math.cos(angle) * (radius + 22),
      ly: center + Math.sin(angle) * (radius + 22),
      gx: center + Math.cos(angle) * radius,
      gy: center + Math.sin(angle) * radius,
    };
  });
  const polygon = points.map((p) => `${p.x},${p.y}`).join(" ");

  return (
    <svg className="importance-radar" width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {[0.33, 0.66, 1].map((level) => {
        const ring = radarAxes.map((_axis, i) => {
          const angle = -Math.PI / 2 + (i / radarAxes.length) * Math.PI * 2;
          return `${center + Math.cos(angle) * radius * level},${center + Math.sin(angle) * radius * level}`;
        }).join(" ");
        return <polygon key={level} points={ring} fill="none" stroke="rgba(33,60,81,0.10)" />;
      })}
      {points.map((p) => (
        <line key={p.key} x1={center} y1={center} x2={p.gx} y2={p.gy} stroke="rgba(33,60,81,0.10)" />
      ))}
      <polygon points={polygon} fill="rgba(101,148,177,0.22)" stroke="var(--accent)" strokeWidth={2} />
      {points.map((p) => (
        <g key={p.key}>
          <circle cx={p.x} cy={p.y} r={3} fill="var(--color-navy)" />
          <text x={p.lx} y={p.ly} textAnchor={p.lx < center - 4 ? "end" : p.lx > center + 4 ? "start" : "middle"}>
            {p.label.replace(" ", "\n")}
          </text>
        </g>
      ))}
    </svg>
  );
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
  const importanceScore = node.importance_score ?? node.ppr_score ?? 0;
  const components = node.importance_components ?? {};

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

      <div className="importance-panel">
        <div className="importance-panel-title">
          <span>Importance</span>
          <strong>{(importanceScore * 100).toFixed(1)}%</strong>
        </div>
        <p>{node.importance_explanation ?? "No importance explanation available."}</p>
        <ImportanceRadar axes={node.importance_radar_axes} />
        <div className="component-list">
          {IMPORTANCE_DIMENSIONS.map((dimension) => {
            const item = components[dimension.key];
            const contribution = item?.contribution ?? 0;
            const weight = item?.weight ?? 0;
            const value = item?.value ?? 0;
            return (
              <div key={dimension.key} className="component-row">
                <span>{dimension.label}</span>
                <div>
                  <strong>{(contribution * 100).toFixed(1)}</strong>
                  <small>v {(value * 100).toFixed(0)} · w {(weight * 100).toFixed(0)}</small>
                </div>
              </div>
            );
          })}
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

// ── Importance ranking strip ─────────────────────────────────────────────────
function ImportanceRanking({
  nodes,
  onSelect,
}: {
  nodes: NetworkNode[];
  onSelect: (id: string) => void;
}) {
  const top = [...nodes]
    .filter((n) => !n.is_ac_member)
    .sort((a, b) => (b.importance_score ?? b.ppr_score) - (a.importance_score ?? a.ppr_score))
    .slice(0, 8);

  if (top.length === 0) return null;

  return (
    <div style={{ marginTop: 20, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: "14px 16px" }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: "var(--muted)", marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.05em" }}>
        Top External Collaborators by Selected Importance
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
              <div style={{ height: "100%", width: `${(n.importance_score ?? n.ppr_score) * 100}%`, background: "#7aa2f7", borderRadius: 2 }} />
            </div>
            <div style={{ fontSize: 11, color: "var(--muted)" }}>
              Score {((n.importance_score ?? n.ppr_score) * 100).toFixed(1)}% · {n.paper_count} papers
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
  const [importanceProfile, setImportanceProfile] = useState("bridge_builders");
  const [importanceWeights, setImportanceWeights] = useState<Record<string, number>>(
    () => weightsForProfile("bridge_builders")
  );
  const [payload, setPayload] = useState<NetworkPayload | null>(null);
  const [instPayload, setInstPayload] = useState<InstitutionNetworkPayload | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const normalizedWeights = useMemo(
    () => normalizeWeights(importanceWeights),
    [importanceWeights]
  );

  function handleProfileChange(profile: string) {
    setImportanceProfile(profile);
    setImportanceWeights(weightsForProfile(profile));
    setSelectedId(null);
  }

  // Fetch author network
  useEffect(() => {
    let cancelled = false;
    setError(null);
    getCoauthorNetwork(onlyRelevant, {
      importanceProfile,
      importanceWeights: normalizedWeights,
    })
      .then((p) => { if (!cancelled) setPayload(p); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); });
    return () => { cancelled = true; };
  }, [onlyRelevant, importanceProfile, normalizedWeights]);

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

      {view === "authors" && (
        <ImportanceWeightEditor
          profile={importanceProfile}
          weights={normalizedWeights}
          onProfileChange={handleProfileChange}
          onWeightsChange={(next) => {
            setImportanceWeights(next);
            setSelectedId(null);
          }}
        />
      )}

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

      {/* Importance ranking (authors view only) */}
      {view === "authors" && payload && (
        <ImportanceRanking nodes={payload.nodes} onSelect={(id) => setSelectedId(id)} />
      )}
    </div>
  );
}
