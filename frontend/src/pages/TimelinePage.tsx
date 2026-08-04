import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { AnalysisScopePanel } from "@/components/AnalysisScopePanel";
import { EChart } from "@/components/EChart";
import { FilterBar } from "@/components/FilterBar";
import { getTimeline } from "@/lib/api";
import {
  isLatestRequest,
  resultForScope,
  type ScopedResult,
} from "@/lib/scopedResult";
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
      stack: payload.by === "label" ? "total" : undefined,
      areaStyle: { opacity: payload.by === "label" ? 0.45 : 0.08 },
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
      name: payload.by === "label" ? "papers" : "distinct papers / series",
      axisLabel: { color: "#9aa3b2" },
      axisLine: { lineStyle: { color: "#2a2f3a" } },
      splitLine: { lineStyle: { color: "#1f232c" } },
    },
    series,
  };
}

export default function TimelinePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const searchKey = searchParams.toString();
  const rawBy = searchParams.get("timeline_by");
  const by = (["topic", "label", "institution", "country", "field"] as const)
    .includes(rawBy as "topic" | "label" | "institution" | "country" | "field")
    ? rawBy as "topic" | "label" | "institution" | "country" | "field"
    : "label";
  const parsedTopN = Number(searchParams.get("timeline_top_n"));
  const topN = Number.isFinite(parsedTopN) && parsedTopN >= 1
    ? Math.min(100, Math.floor(parsedTopN))
    : 10;
  const scopeKey = JSON.stringify([searchKey, by, topN]);
  const [payloadResult, setPayloadResult] = useState<
    ScopedResult<TimelinePayload> | null
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
    getTimeline(by, new URLSearchParams(searchKey), topN)
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
  }, [by, scopeKey, searchKey, topN]);

  const setProjection = (key: "timeline_by" | "timeline_top_n", value: string) => {
    const next = new URLSearchParams(searchParams);
    next.set(key, value);
    setSearchParams(next);
  };

  return (
    <div>
      <FilterBar />
      <div className="page-heading-compact">
        <div><h1>Evidence Timeline</h1><p>Distinct filtered papers by publication year.</p></div>
      </div>
      <div className="filters" style={{ marginTop: "0.5rem" }}>
        <label>
          Group by:&nbsp;
          <select value={by} onChange={(e) => setProjection("timeline_by", e.target.value)}>
            <option value="label">Classification label</option>
            <option value="topic">Core topic</option>
            <option value="institution">Institution</option>
            <option value="country">Country</option>
            <option value="field">Research field</option>
          </select>
        </label>
        <label>
          Top series:&nbsp;
          <input
            type="number"
            min={1}
            max={100}
            value={topN}
            onChange={(event) => setProjection(
              "timeline_top_n",
              String(Math.min(100, Math.max(1, Number(event.target.value) || 1))),
            )}
            style={{ width: 72 }}
          />
        </label>
      </div>
      {error && <div style={{ color: "var(--uncertain)" }}>Backend error: {error}</div>}
      {loading && !payload && <div className="empty">Loading timeline…</div>}
      {payload && payload.years.length === 0 && (
        <div className="empty">No papers match the current filter.</div>
      )}
      {payload && payload.years.length > 0 && (
        <>
          {payload.by !== "label" && (
            <p className="metric-note">
              Showing the top {payload.top_n} series by distinct-paper support. Series are not stacked
              because one paper may belong to multiple {payload.by} values.
            </p>
          )}
          <EChart option={buildOption(payload)} />
          <AnalysisScopePanel audit={payload.audit} title="Timeline evidence scope" />
        </>
      )}
    </div>
  );
}
