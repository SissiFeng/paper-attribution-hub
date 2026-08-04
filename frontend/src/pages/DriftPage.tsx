import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { AnalysisScopePanel } from "@/components/AnalysisScopePanel";
import { FilterBar } from "@/components/FilterBar";
import { getDriftReport } from "@/lib/api";
import {
  isLatestRequest,
  resultForScope,
  type ScopedResult,
} from "@/lib/scopedResult";
import type { DriftReport } from "@/types";

export default function DriftPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const thresholdValue = Number(searchParams.get("drift_threshold") ?? "0.7");
  const threshold =
    Number.isFinite(thresholdValue) &&
    thresholdValue >= 0 &&
    thresholdValue <= 1
      ? thresholdValue
      : 0.7;
  const topNValue = Number(searchParams.get("top_n_per_year") ?? "5");
  const topNPerYear =
    Number.isInteger(topNValue) && topNValue >= 1 && topNValue <= 20
      ? topNValue
      : 5;
  const searchKey = searchParams.toString();
  const scopeKey = JSON.stringify([searchKey, threshold, topNPerYear]);
  const [reportResult, setReportResult] = useState<
    ScopedResult<DriftReport> | null
  >(null);
  const report = resultForScope(reportResult, scopeKey);
  const [error, setError] = useState<string | null>(null);
  const requestGeneration = useRef(0);

  useEffect(() => {
    let cancelled = false;
    const generation = ++requestGeneration.current;
    setError(null);
    getDriftReport(new URLSearchParams(searchKey), threshold, topNPerYear)
      .then((nextReport) => {
        if (!cancelled && isLatestRequest(generation, requestGeneration.current)) {
          setReportResult({ scopeKey, payload: nextReport });
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
  }, [scopeKey, searchKey, threshold, topNPerYear]);

  const setProjectionParam = (key: string, value: number) => {
    const next = new URLSearchParams(searchKey);
    next.set(key, String(value));
    setSearchParams(next);
  };

  return (
    <div>
      <FilterBar />
      <div className="filters" style={{ marginTop: "0.4rem" }}>
        <label>
          Drift threshold (cosine similarity):&nbsp;
          <input
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={threshold}
            onChange={(e) =>
              setProjectionParam("drift_threshold", Number(e.target.value))
            }
            style={{ width: 80 }}
          />
        </label>
        <label>
          Top topics per year:&nbsp;
          <input
            type="number"
            min={1}
            max={20}
            step={1}
            value={topNPerYear}
            onChange={(e) =>
              setProjectionParam("top_n_per_year", Number(e.target.value))
            }
            style={{ width: 64 }}
          />
        </label>
        <span style={{ color: "var(--muted)" }}>
          Higher threshold = stricter stability requirement; more transitions
          flagged.
        </span>
      </div>

      {error && (
        <div style={{ color: "var(--uncertain)" }}>Backend error: {error}</div>
      )}

      {report && (
        <>
          <AnalysisScopePanel audit={report.audit} title="Drift evidence scope" />
          <h3 style={{ marginTop: "1rem" }}>
            Drift events ({report.drift_events.length})
          </h3>
          {report.drift_events.length === 0 ? (
            <div className="empty">
              No adjacent-year cosine similarity fell below the configured
              threshold ({report.drift_threshold}).
            </div>
          ) : (
            <ul className="drift-events">
              {report.drift_events.map((e, i) => (
                <li key={i}>
                  <div className="drift-header">
                    <strong>
                      {e.from_year} → {e.to_year}
                    </strong>
                    <span className="drift-similarity">
                      cosine sim {e.cosine_similarity}
                    </span>
                  </div>
                  {e.new_topics.length > 0 && (
                    <div>
                      <span className="evidence-type">new</span>{" "}
                      {e.new_topics.join(", ")}
                    </div>
                  )}
                  {e.faded_topics.length > 0 && (
                    <div>
                      <span className="evidence-type">faded</span>{" "}
                      {e.faded_topics.join(", ")}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}

          <h3 style={{ marginTop: "1.4rem" }}>Year-by-year top topics</h3>
          <div className="drift-years">
            {report.per_year.map((y) => (
              <div key={y.year} className="drift-year-card">
                <div className="drift-year-head">
                  <strong>{y.year}</strong>
                  <span style={{ color: "var(--muted)" }}>
                    {y.total_papers} papers
                  </span>
                </div>
                <ul>
                  {y.top_topics.map((t) => (
                    <li key={t.topic_id}>
                      <span>{t.name}</span>
                      <span style={{ color: "var(--muted)" }}>
                        {(t.share * 100).toFixed(0)}% · {t.paper_count}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
