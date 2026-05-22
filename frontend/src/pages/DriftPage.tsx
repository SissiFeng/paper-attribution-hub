import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { FilterBar } from "@/components/FilterBar";
import { getDriftReport } from "@/lib/api";
import type { DriftReport } from "@/types";

export default function DriftPage() {
  const [searchParams] = useSearchParams();
  const [threshold, setThreshold] = useState(0.7);
  const [report, setReport] = useState<DriftReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(searchParams);
    params.set("drift_threshold", String(threshold));
    let cancelled = false;
    getDriftReport(params)
      .then((r) => !cancelled && setReport(r))
      .catch(
        (err) => !cancelled && setError(err instanceof Error ? err.message : String(err))
      );
    return () => {
      cancelled = true;
    };
  }, [threshold, searchParams.toString()]);

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
            onChange={(e) => setThreshold(Number(e.target.value))}
            style={{ width: 80 }}
          />
        </label>
        <span style={{ color: "var(--muted)" }}>
          Lower threshold = stricter notion of "stable", more events flagged.
        </span>
      </div>

      {error && (
        <div style={{ color: "var(--uncertain)" }}>Backend error: {error}</div>
      )}

      {report && (
        <>
          <h3 style={{ marginTop: "1rem" }}>
            Drift events ({report.drift_events.length})
          </h3>
          {report.drift_events.length === 0 ? (
            <div className="empty">
              No drift events above the configured threshold (
              {report.drift_threshold}).
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
