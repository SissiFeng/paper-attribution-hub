import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { EChart } from "@/components/EChart";
import { FilterBar } from "@/components/FilterBar";
import { getImpactReport } from "@/lib/api";
import type { GrowthSeries, ImpactReport } from "@/types";

function lineOption(series: GrowthSeries, color: string) {
  const data = series.points.map((p) => [String(p.year), p.value]);
  return {
    tooltip: { trigger: "axis" },
    grid: { left: 36, right: 12, bottom: 28, top: 18 },
    xAxis: {
      type: "category",
      data: series.points.map((p) => String(p.year)),
      axisLabel: { color: "#9aa3b2" },
      axisLine: { lineStyle: { color: "#2a2f3a" } },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: "#9aa3b2" },
      axisLine: { lineStyle: { color: "#2a2f3a" } },
      splitLine: { lineStyle: { color: "#1f232c" } },
    },
    series: [
      {
        type: "line",
        smooth: true,
        symbol: "circle",
        symbolSize: 7,
        data,
        itemStyle: { color },
        lineStyle: { color, width: 2 },
        areaStyle: { color, opacity: 0.18 },
      },
    ],
  };
}

export default function ImpactPage() {
  const [searchParams] = useSearchParams();
  const [report, setReport] = useState<ImpactReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getImpactReport(searchParams)
      .then((r) => !cancelled && setReport(r))
      .catch(
        (err) => !cancelled && setError(err instanceof Error ? err.message : String(err))
      );
    return () => {
      cancelled = true;
    };
  }, [searchParams.toString()]);

  if (error) {
    return (
      <div>
        <FilterBar />
        <div style={{ color: "var(--uncertain)" }}>Backend error: {error}</div>
      </div>
    );
  }
  if (!report) {
    return (
      <div>
        <FilterBar />
        <div className="empty">Loading…</div>
      </div>
    );
  }

  const total = report.yoy_attributed.points.reduce((s, p) => s + p.value, 0);
  const totalCitations = report.citation_impact.points.reduce(
    (s, p) => s + p.value,
    0
  );

  return (
    <div>
      <FilterBar />
      <div className="eval-headline" style={{ marginTop: "0.4rem" }}>
        <div className="cell">
          <div className="label">AC-attributed papers</div>
          <div className="value">{total}</div>
        </div>
        <div className="cell">
          <div className="label">Citation edges (corpus)</div>
          <div className="value">{totalCitations}</div>
        </div>
        <div className="cell">
          <div className="label">Window</div>
          <div className="value">
            {report.window_from ?? "all"}–{report.window_to ?? "all"}
          </div>
        </div>
        <div className="cell">
          <div className="label">Emerging institutions</div>
          <div className="value">{report.emerging_institutions.length}</div>
        </div>
      </div>

      <div className="impact-grid">
        <div className="impact-card">
          <h3>AC-attributed papers (YoY)</h3>
          <EChart
            option={lineOption(report.yoy_attributed, "#34d399")}
            style={{ height: 220 }}
          />
        </div>
        <div className="impact-card">
          <h3>Citation edges (YoY)</h3>
          <EChart
            option={lineOption(report.citation_impact, "#7aa2f7")}
            style={{ height: 220 }}
          />
        </div>
        <div className="impact-card">
          <h3>Top growing themes</h3>
          {report.top_growing_themes.length === 0 ? (
            <div className="empty">No themes in window.</div>
          ) : (
            <ul className="impact-list">
              {report.top_growing_themes.slice(0, 6).map((t) => (
                <li key={t.topic_id}>
                  <span>{t.name}</span>
                  <span
                    className="delta"
                    style={{
                      color:
                        t.delta_pct === "new"
                          ? "var(--core)"
                          : typeof t.delta_pct === "number" && t.delta_pct >= 0
                          ? "var(--core)"
                          : "var(--uncertain)",
                    }}
                  >
                    {t.delta_pct === "new" ? "NEW" : `${t.delta_pct}%`}
                    <span
                      style={{
                        color: "var(--muted)",
                        marginLeft: "0.4rem",
                        fontSize: "0.8rem",
                      }}
                    >
                      ({t.value_then}→{t.value_now})
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="impact-card">
          <h3>Emerging institutional collaborators</h3>
          {report.emerging_institutions.length === 0 ? (
            <div className="empty">No new institutions in window.</div>
          ) : (
            <ul className="impact-list">
              {report.emerging_institutions.slice(0, 6).map((e) => (
                <li key={e.id}>
                  <span>
                    {e.label}{" "}
                    {e.is_partner && (
                      <span className="provenance-badge discovered_approved">
                        partner
                      </span>
                    )}
                  </span>
                  <span style={{ color: "var(--muted)" }}>
                    {e.paper_count} paper(s) · since {e.first_year}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
