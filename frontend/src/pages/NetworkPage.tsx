import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { EChart } from "@/components/EChart";
import { FilterBar } from "@/components/FilterBar";
import { getInstitutionNetwork } from "@/lib/api";
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
      width: Math.min(1 + e.weight * 0.8, 4.5),
      color: "rgba(154, 163, 178, 0.5)",
    },
  }));
  return {
    tooltip: {
      formatter: (p: any) => {
        if (p.dataType === "node") {
          const node = payload.nodes.find((n) => n.id === p.data.id);
          return node
            ? `<b>${node.label}</b><br/>${node.country ?? "—"}<br/>${node.paper_count} joint papers`
            : p.name;
        }
        const src = payload.nodes.find((n) => n.id === p.data.source)?.label;
        const tgt = payload.nodes.find((n) => n.id === p.data.target)?.label;
        return `${src} ↔ ${tgt}<br/>${p.data.value} joint papers`;
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
  const [payload, setPayload] = useState<InstitutionNetworkPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getInstitutionNetwork(minPapers, searchParams)
      .then((p) => !cancelled && setPayload(p))
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : String(err)));
    return () => {
      cancelled = true;
    };
  }, [minPapers, searchParams.toString()]);

  return (
    <div>
      <FilterBar />
      <div className="filters" style={{ marginTop: "0.5rem" }}>
        <label>
          Min joint papers:&nbsp;
          <input
            type="number"
            min={1}
            max={20}
            value={minPapers}
            onChange={(e) => setMinPapers(Math.max(1, Number(e.target.value)))}
            style={{ width: 70 }}
          />
        </label>
      </div>
      {error && <div style={{ color: "var(--uncertain)" }}>Backend error: {error}</div>}
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
        </>
      )}
    </div>
  );
}
