import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { EChart } from "@/components/EChart";
import { FilterBar } from "@/components/FilterBar";
import { getTimeline } from "@/lib/api";
import type { TimelinePayload } from "@/types";

const LABEL_COLOR: Record<string, string> = {
  CORE_RELEVANT: "#34d399",
  RELATED_RELEVANT: "#60a5fa",
  ADJACENT: "#fbbf24",
  UNCERTAIN: "#f97316",
  EXCLUDE: "#6b7280",
};

function buildOption(payload: TimelinePayload) {
  const years = payload.years;

  // For each series, expand sparse year → count tuples into a dense list aligned with `years`.
  const series = payload.series.map((s) => {
    const lookup = new Map(s.data);
    return {
      name: s.name,
      type: "line" as const,
      stack: "total",
      areaStyle: { opacity: 0.5 },
      smooth: true,
      symbol: "circle",
      symbolSize: 6,
      data: years.map((y) => lookup.get(y) ?? 0),
      lineStyle: { width: 1.5 },
      itemStyle: payload.by === "label" && LABEL_COLOR[s.name]
        ? { color: LABEL_COLOR[s.name] }
        : undefined,
    };
  });

  return {
    tooltip: { trigger: "axis" },
    legend: { top: 0 },
    grid: { left: 50, right: 30, bottom: 40, top: 50 },
    xAxis: {
      type: "category",
      data: years.map(String),
      boundaryGap: false,
      axisLabel: { color: "#9aa3b2" },
      axisLine: { lineStyle: { color: "#2a2f3a" } },
    },
    yAxis: {
      type: "value",
      name: "papers",
      axisLabel: { color: "#9aa3b2" },
      axisLine: { lineStyle: { color: "#2a2f3a" } },
      splitLine: { lineStyle: { color: "#1f232c" } },
    },
    series,
  };
}

export default function TimelinePage() {
  const [searchParams] = useSearchParams();
  const [by, setBy] = useState<"topic" | "label">("label");
  const [payload, setPayload] = useState<TimelinePayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getTimeline(by, searchParams)
      .then((p) => !cancelled && setPayload(p))
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : String(err)));
    return () => {
      cancelled = true;
    };
  }, [by, searchParams.toString()]);

  return (
    <div>
      <FilterBar />
      <div className="filters" style={{ marginTop: "0.5rem" }}>
        <label>
          Group by:&nbsp;
          <select value={by} onChange={(e) => setBy(e.target.value as "topic" | "label")}>
            <option value="label">Classification label</option>
            <option value="topic">Core topic</option>
          </select>
        </label>
      </div>
      {error && <div style={{ color: "var(--uncertain)" }}>Backend error: {error}</div>}
      {payload && payload.years.length === 0 && (
        <div className="empty">No papers match the current filter.</div>
      )}
      {payload && payload.years.length > 0 && <EChart option={buildOption(payload)} />}
    </div>
  );
}
