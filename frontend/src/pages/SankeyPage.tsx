import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { AnalysisScopePanel } from "@/components/AnalysisScopePanel";
import { EChart } from "@/components/EChart";
import { FilterBar } from "@/components/FilterBar";
import { getSankey } from "@/lib/api";
import { escapeHtml } from "@/lib/html";
import {
  isLatestRequest,
  resultForScope,
  type ScopedResult,
} from "@/lib/scopedResult";
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
    label: { formatter: () => n.name, color: "#213C51" },
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
          return node
            ? `${escapeHtml(node.layer)}: <b>${escapeHtml(node.name)}</b>`
            : escapeHtml(p.name);
        }
        const src = payload.nodes.find((n) => n.id === p.data.source)?.name;
        const tgt = payload.nodes.find((n) => n.id === p.data.target)?.name;
        return `${escapeHtml(src ?? "—")} → ${escapeHtml(tgt ?? "—")}: <b>${p.value}</b> papers`;
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
        label: { color: "#213C51", fontSize: 11, overflow: "truncate", width: 220 },
        layoutIterations: 64,
      },
    ],
  };
}

export default function SankeyPage() {
  const [searchParams] = useSearchParams();
  const searchKey = searchParams.toString();
  const [payloadResult, setPayloadResult] = useState<
    ScopedResult<SankeyPayload> | null
  >(null);
  const payload = resultForScope(payloadResult, searchKey);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestGeneration = useRef(0);

  useEffect(() => {
    let cancelled = false;
    const generation = ++requestGeneration.current;
    setLoading(true);
    setError(null);
    getSankey(new URLSearchParams(searchKey))
      .then((nextPayload) => {
        if (!cancelled && isLatestRequest(generation, requestGeneration.current)) {
          setPayloadResult({ scopeKey: searchKey, payload: nextPayload });
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
  }, [searchKey]);

  return (
    <div>
      <FilterBar />
      <h3 style={{ marginTop: "0.5rem" }}>Institution → Topic → Classification flow</h3>
      <p style={{ color: "var(--muted)", marginTop: 0, marginBottom: "0.8rem" }}>
        Each link counts distinct filtered papers for that relationship; a paper
        with multiple affiliations is counted once on each institution link and
        once on its topic-to-label link.
      </p>
      {error && <div style={{ color: "var(--uncertain)" }}>Backend error: {error}</div>}
      {loading && !payload && <div className="empty">Loading flow…</div>}
      {payload && payload.nodes.length === 0 && (
        <div className="empty">No flow matches the current filter.</div>
      )}
      {payload && payload.nodes.length > 0 && (
        <>
          <EChart
            option={buildOption(payload)}
            style={{ height: Math.max(620, payload.nodes.length * 18) }}
          />
          <AnalysisScopePanel audit={payload.audit} title="Sankey evidence scope" />
        </>
      )}
    </div>
  );
}
