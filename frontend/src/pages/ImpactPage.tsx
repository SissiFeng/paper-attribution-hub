import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { AnalysisScopePanel } from "@/components/AnalysisScopePanel";
import { EChart } from "@/components/EChart";
import { FilterBar } from "@/components/FilterBar";
import { getImpactReport } from "@/lib/api";
import {
  isLatestRequest,
  resultForScope,
  type ScopedResult,
} from "@/lib/scopedResult";
import type { GrowthSeries, ImpactReport } from "@/types";

/** Detect if the last year looks like a partial year (< 60% of the prior year). */
function isPartialYear(points: GrowthSeries["points"]): boolean {
  if (points.length < 2) return false;
  const last = points[points.length - 1].value;
  const prev = points[points.length - 2].value;
  return prev > 0 && last < prev * 0.6;
}

function lineOption(series: GrowthSeries, color: string) {
  const partial = isPartialYear(series.points);
  const lastYear = series.points.length > 0
    ? String(series.points[series.points.length - 1].year)
    : null;

  // Split into solid (complete) and dashed (partial) segments
  const solidData = partial
    ? series.points.slice(0, -1).map((p) => [String(p.year), p.value])
    : series.points.map((p) => [String(p.year), p.value]);
  const partialData = partial
    ? series.points.slice(-2).map((p) => [String(p.year), p.value])
    : [];

  return {
    tooltip: {
      trigger: "axis",
      formatter: (params: any[]) => {
        const p = params[0];
        const yr = p.axisValue;
        const suffix = partial && yr === lastYear ? " ⚠ partial year" : "";
        return `${yr}: <b>${p.value}</b>${suffix}`;
      },
    },
    grid: { left: 36, right: 12, bottom: 28, top: partial ? 28 : 18 },
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
    ...(partial ? {
      graphic: [{
        type: "text",
        right: 12, top: 4,
        style: {
          text: `⚠ ${lastYear} data is partial (import cutoff)`,
          fill: "#f59e0b", fontSize: 11, fontFamily: "'JetBrains Mono', monospace",
        },
      }],
    } : {}),
    series: [
      {
        type: "line",
        smooth: true,
        symbol: "circle",
        symbolSize: 7,
        data: solidData,
        itemStyle: { color },
        lineStyle: { color, width: 2 },
        areaStyle: { color, opacity: 0.15 },
        z: 2,
      },
      ...(partial ? [{
        type: "line",
        smooth: false,
        symbol: "emptyCircle",
        symbolSize: 7,
        data: partialData,
        itemStyle: { color: "#f59e0b" },
        lineStyle: { color: "#f59e0b", width: 2, type: "dashed" },
        areaStyle: { color: "#f59e0b", opacity: 0.07 },
        z: 1,
      }] : []),
    ],
  };
}

export default function ImpactPage() {
  const [searchParams] = useSearchParams();
  const searchKey = searchParams.toString();
  const [reportResult, setReportResult] = useState<
    ScopedResult<ImpactReport> | null
  >(null);
  const report = resultForScope(reportResult, searchKey);
  const [error, setError] = useState<string | null>(null);
  const requestGeneration = useRef(0);

  useEffect(() => {
    let cancelled = false;
    const generation = ++requestGeneration.current;
    setError(null);
    getImpactReport(new URLSearchParams(searchKey))
      .then((nextReport) => {
        if (!cancelled && isLatestRequest(generation, requestGeneration.current)) {
          setReportResult({ scopeKey: searchKey, payload: nextReport });
        }
      })
      .catch((err) => {
        if (!cancelled && isLatestRequest(generation, requestGeneration.current)) {
          setError(err instanceof Error ? err.message : String(err));
          setReportResult(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [searchKey]);

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
  const totalCitations = report.citation_impact.points.reduce((s, p) => s + p.value, 0);
  const normalizedCitations = report.normalized_citation_impact;
  const partialYearActive = isPartialYear(report.yoy_attributed.points);
  const lastYear = report.yoy_attributed.points.length > 0
    ? report.yoy_attributed.points[report.yoy_attributed.points.length - 1].year
    : null;

  return (
    <div>
      <FilterBar />
      <div className="eval-headline" style={{ marginTop: "0.4rem" }}>
        <div className="cell">
          <div className="label">AC-attributed papers (CORE + RELATED)</div>
          <div className="value">{total}</div>
          {partialYearActive && (
            <div style={{ fontSize: "0.72rem", color: "#f59e0b", marginTop: 2 }}>
              excl. partial {lastYear}
            </div>
          )}
        </div>
        <div className="cell">
          <div className="label">Citation edges (corpus)</div>
          <div className="value">{totalCitations}</div>
        </div>
        <div className="cell">
          <div className="label">Field-year normalized citations</div>
          <div className="value">
            {normalizedCitations.normalized_index?.toFixed(2) ?? "—"}
          </div>
          <div style={{ fontSize: "0.72rem", color: "var(--muted)", marginTop: 2 }}>
            {normalizedCitations.covered_papers}/{normalizedCitations.total_papers} papers covered
          </div>
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

      <AnalysisScopePanel audit={report.audit} title="Impact evidence scope" />

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
          <h3>Normalized external citation impact</h3>
          <p className="metric-note">
            Mean citations per covered paper relative to this corpus&apos;s same-field,
            same-year baseline. 1.00 is the baseline; this is not a proprietary global FWCI.
          </p>
          {normalizedCitations.normalized_index == null ? (
            <div className="empty">
              No external citation snapshots in scope. Run the citation snapshot refresh job.
            </div>
          ) : (
            <>
              <div className="impact-citation-summary">
                <strong>{normalizedCitations.normalized_index.toFixed(2)}</strong>
                <span>{(normalizedCitations.coverage * 100).toFixed(1)}% snapshot coverage</span>
                <small>
                  Snapshot range {normalizedCitations.snapshot_oldest_at
                    ? new Date(normalizedCitations.snapshot_oldest_at).toLocaleDateString()
                    : "unknown"} – {normalizedCitations.snapshot_newest_at
                    ? new Date(normalizedCitations.snapshot_newest_at).toLocaleDateString()
                    : "unknown"}
                </small>
              </div>
              <ul className="impact-list">
                {normalizedCitations.by_institution.slice(0, 6).map((item) => (
                  <li key={item.institution_id}>
                    <span>{item.institution_name}</span>
                    <span>
                      {item.normalized_index.toFixed(2)} · {item.paper_count} paper(s)
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
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
