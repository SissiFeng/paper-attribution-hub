import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { AnalysisScopePanel } from "@/components/AnalysisScopePanel";
import { EChart } from "@/components/EChart";
import { FilterBar } from "@/components/FilterBar";
import { getInstitutionNetwork } from "@/lib/api";
import { escapeHtml } from "@/lib/html";
import {
  isLatestRequest,
  resultForScope,
  type ScopedResult,
} from "@/lib/scopedResult";
import type { InstitutionNetworkPayload } from "@/types";

function buildOption(payload: InstitutionNetworkPayload) {
  const nodes = payload.nodes.map((n) => ({
    id: n.id,
    name: n.label,
    symbolSize: Math.max(12, Math.min(46, 12 + n.paper_count * 4)),
    itemStyle: {
      color: n.is_partner ? "#34d399" : "#7aa2f7",
      borderColor: "#0f1115",
      borderWidth: 1.5,
    },
    label: { show: true, color: "#e7eaf0", fontSize: 11, position: "right" },
    value: n.paper_count,
    category: n.is_partner ? 0 : 1,
  }));
  const edges = payload.edges.map((e) => ({
    source: e.source,
    target: e.target,
    value: e.weight,
    lineStyle: {
      width: Math.min(1 + (e.normalized_weight ?? 0) * 3, 4.5),
      color: e.involves_partner
        ? "rgba(52, 211, 153, 0.7)"
        : "rgba(154, 163, 178, 0.35)",
    },
  }));
  return {
    tooltip: {
      formatter: (p: any) => {
        if (p.dataType === "node") {
          const node = payload.nodes.find((n) => n.id === p.data.id);
          return node
            ? `<b>${escapeHtml(node.label)}</b><br/>${escapeHtml(node.country ?? "—")}<br/>${node.paper_count} distinct papers`
            : escapeHtml(p.name);
        }
        const src = payload.nodes.find((n) => n.id === p.data.source)?.label;
        const tgt = payload.nodes.find((n) => n.id === p.data.target)?.label;
        const edge = payload.edges.find(
          (e) => e.source === p.data.source && e.target === p.data.target
        );
        const norm = edge ? ` (strength ${(edge.normalized_weight * 100).toFixed(0)}%)` : "";
        return `${escapeHtml(src ?? "—")} ↔ ${escapeHtml(tgt ?? "—")}<br/>${p.data.value} joint papers${norm}`;
      },
    },
    legend: {
      data: [
        { name: "AC partner", icon: "circle", itemStyle: { color: "#34d399" } },
        { name: "External", icon: "circle", itemStyle: { color: "#7aa2f7" } },
      ],
      top: 0,
      textStyle: { color: "#9aa3b2" },
    },
    series: [
      {
        type: "graph",
        layout: "force",
        roam: true,
        draggable: true,
        force: { repulsion: 220, edgeLength: [80, 200], gravity: 0.08 },
        categories: [{ name: "AC partner" }, { name: "External" }],
        edges,
        data: nodes,
        emphasis: { focus: "adjacency" },
        label: { show: true },
      },
    ],
  };
}

export default function NetworkPage() {
  const [searchParams] = useSearchParams();
  const [minPapers, setMinPapers] = useState(1);
  const [topN, setTopN] = useState(50);
  const searchKey = searchParams.toString();
  const scopeKey = JSON.stringify([searchKey, minPapers, topN]);
  const [payloadResult, setPayloadResult] = useState<
    ScopedResult<InstitutionNetworkPayload> | null
  >(null);
  const payload = resultForScope(payloadResult, scopeKey);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestGeneration = useRef(0);

  useEffect(() => {
    let cancelled = false;
    const generation = ++requestGeneration.current;
    setLoading(true);
    setError(null);
    getInstitutionNetwork(minPapers, new URLSearchParams(searchKey), topN)
      .then((nextPayload) => {
        if (!cancelled && isLatestRequest(generation, requestGeneration.current)) {
          setPayloadResult({ scopeKey, payload: nextPayload });
        }
      })
      .catch((err) => {
        if (!cancelled && isLatestRequest(generation, requestGeneration.current)) {
          setError(err instanceof Error ? err.message : String(err));
          setPayloadResult(null);
        }
      })
      .finally(() => {
        if (!cancelled && isLatestRequest(generation, requestGeneration.current)) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [minPapers, scopeKey, searchKey, topN]);

  return (
    <div>
      <FilterBar />
      <div className="page-heading-compact">
        <div><h1>Institutional Collaboration</h1><p>Edges count distinct filtered papers jointly affiliated with both institutions.</p></div>
      </div>
      <div className="filters" style={{ marginTop: "0.5rem" }}>
        <label>
          Min papers per institution:&nbsp;
          <input
            type="number"
            min={1}
            max={20}
            value={minPapers}
            onChange={(e) => setMinPapers(Math.max(1, Number(e.target.value)))}
            style={{ width: 70 }}
          />
        </label>
        <label>
          Top institutions:&nbsp;
          <input type="number" min={5} max={200} value={topN} onChange={(e) => setTopN(Math.max(5, Number(e.target.value)))} style={{ width: 70 }} />
        </label>
      </div>
      {error && <div style={{ color: "var(--uncertain)" }}>Backend error: {error}</div>}
      {loading && !payload && <div className="empty">Loading network…</div>}
      {payload && payload.nodes.length === 0 && (
        <div className="empty">No institutions match the current filter.</div>
      )}
      {payload && payload.nodes.length > 0 && (
        <>
          <EChart option={buildOption(payload)} />
          <div className="network-legend">
            <span>
              <span className="dot ac" /> AC partner institution
            </span>
            <span>
              <span className="dot other" /> External institution
            </span>
            <span style={{ marginLeft: "auto" }}>
              {payload.nodes.length} institutions · {payload.edges.length} collaborations
            </span>
          </div>
          <AnalysisScopePanel audit={payload.audit} title="Collaboration evidence scope" />
        </>
      )}
    </div>
  );
}
