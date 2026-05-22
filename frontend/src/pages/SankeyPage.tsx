import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { EChart } from "@/components/EChart";
import { FilterBar } from "@/components/FilterBar";
import { getSankey } from "@/lib/api";
import type { SankeyPayload } from "@/types";

const LAYER_COLOR: Record<string, string> = {
  institution: "#7aa2f7",
  topic: "#34d399",
  label: "#fbbf24",
};

const LABEL_COLOR: Record<string, string> = {
  CORE_RELEVANT: "#34d399",
  RELATED_RELEVANT: "#60a5fa",
  ADJACENT: "#fbbf24",
  UNCERTAIN: "#f97316",
  EXCLUDE: "#6b7280",
};

function buildOption(payload: SankeyPayload) {
  const data = payload.nodes.map((n) => ({
    name: n.id,
    label: { formatter: () => n.name, color: "#e7eaf0" },
    itemStyle: {
      color:
        n.layer === "label" && LABEL_COLOR[n.name.replace(/ /g, "_").toUpperCase()]
          ? LABEL_COLOR[n.name.replace(/ /g, "_").toUpperCase()]
          : LAYER_COLOR[n.layer] ?? "#7aa2f7",
    },
  }));
  return {
    tooltip: {
      trigger: "item",
      triggerOn: "mousemove",
      formatter: (p: any) => {
        if (p.dataType === "node") {
          const node = payload.nodes.find((n) => n.id === p.name);
          return node ? `${node.layer}: <b>${node.name}</b>` : p.name;
        }
        const src = payload.nodes.find((n) => n.id === p.data.source)?.name;
        const tgt = payload.nodes.find((n) => n.id === p.data.target)?.name;
        return `${src} → ${tgt}: <b>${p.value}</b> papers`;
      },
    },
    series: [
      {
        type: "sankey",
        data,
        links: payload.links.map((l) => ({
          source: l.source,
          target: l.target,
          value: l.value,
        })),
        emphasis: { focus: "adjacency" },
        nodeAlign: "left",
        nodeGap: 12,
        nodeWidth: 14,
        lineStyle: { color: "gradient", curveness: 0.5, opacity: 0.4 },
        label: { color: "#e7eaf0", fontSize: 12 },
        layoutIterations: 32,
      },
    ],
  };
}

export default function SankeyPage() {
  const [searchParams] = useSearchParams();
  const [payload, setPayload] = useState<SankeyPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSankey(searchParams)
      .then((p) => !cancelled && setPayload(p))
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : String(err)));
    return () => {
      cancelled = true;
    };
  }, [searchParams.toString()]);

  return (
    <div>
      <FilterBar />
      <h3 style={{ marginTop: "0.5rem" }}>Institution → Topic → Classification flow</h3>
      <p style={{ color: "var(--muted)", marginTop: 0, marginBottom: "0.8rem" }}>
        Counts are paper × (institution, core-topic, label) combinations. Click
        a node in the table or visit the network page to see specific papers.
      </p>
      {error && <div style={{ color: "var(--uncertain)" }}>Backend error: {error}</div>}
      {payload && payload.nodes.length === 0 && (
        <div className="empty">No flow matches the current filter.</div>
      )}
      {payload && payload.nodes.length > 0 && <EChart option={buildOption(payload)} />}
    </div>
  );
}
