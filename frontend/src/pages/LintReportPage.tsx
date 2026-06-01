import { useCallback, useEffect, useState } from "react";

import { getLintReport } from "@/lib/api";
import type { LintBucket, LintReport } from "@/types";

export default function LintReportPage() {
  const [report, setReport] = useState<LintReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedBucket, setExpandedBucket] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setReport(await getLintReport());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="v7-page">
      <div className="v7-hero">
        <div>
          <h1>Lint Report</h1>
          <p>
            Website-blocking attribution problems and reporting warnings after ingest.
          </p>
        </div>
        <div className="v7-hero-actions">
          <button className="v7-btn" onClick={() => void load()} disabled={loading}>
            Refresh
          </button>
        </div>
      </div>

      <div className="v7-stat-grid">
        <div className="v7-stat">
          <div className="label">Website blockers</div>
          <div className="value">{report?.website_blockers ?? 0}</div>
          <div className="delta">must resolve before public claims</div>
        </div>
        <div className="v7-stat">
          <div className="label">Reporting warnings</div>
          <div className="value">{report?.reporting_warnings ?? 0}</div>
          <div className="delta">acceptable for aggregate metrics</div>
        </div>
        <div className="v7-stat">
          <div className="label">Scanned</div>
          <div className="value">{report?.total_papers_scanned ?? 0}</div>
          <div className="delta">knowledge-base papers</div>
        </div>
      </div>

      {error && (
        <div className="v7-card" style={{ borderColor: "rgba(249,115,22,0.4)" }}>
          Backend error: {error}
        </div>
      )}

      {loading && !report ? (
        <div className="v7-gap-grid">
          <div className="v7-skel card" style={{ height: 220 }} />
          <div className="v7-skel card" style={{ height: 220 }} />
          <div className="v7-skel card" style={{ height: 220 }} />
        </div>
      ) : !report || report.buckets.every((b) => b.count === 0) ? (
        <div className="v7-empty">
          <span className="icon">OK</span>
          <div>No lint findings detected.</div>
        </div>
      ) : (
        <div className="v7-gap-grid">
          {report.buckets.map((bucket) => (
            <LintBucketCard
              key={bucket.bucket}
              bucket={bucket}
              expanded={expandedBucket === bucket.bucket}
              onToggle={() =>
                setExpandedBucket(expandedBucket === bucket.bucket ? null : bucket.bucket)
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}

function LintBucketCard({
  bucket,
  expanded,
  onToggle,
}: {
  bucket: LintBucket;
  expanded: boolean;
  onToggle: () => void;
}) {
  const isBlocker = bucket.severity === "blocker";
  return (
    <div className="v7-gap-card" style={bucket.count === 0 ? { opacity: 0.6 } : {}}>
      <div className="gap-head">
        <h3>
          <span className={`v7-label ${isBlocker ? "EXCLUDE" : "UNCERTAIN"}`}>
            {bucket.severity}
          </span>
          {bucket.label}
        </h3>
        <span className="gap-count">{bucket.count}</span>
      </div>
      <div style={{ color: "var(--muted)", fontSize: "0.82rem", marginBottom: 8 }}>
        {bucket.description}
      </div>

      {bucket.entries.length === 0 ? (
        <div style={{ color: "var(--muted)", fontSize: "0.84rem", padding: "0.4rem 0" }}>
          No examples loaded.
        </div>
      ) : (
        <>
          <ul className="v7-gap-list">
            {(expanded ? bucket.entries : bucket.entries.slice(0, 3)).map((e) => (
              <li key={e.paper_id} onClick={() => window.open(`/?selected=${e.paper_id}`, "_blank")}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 4 }}>
                    {e.label && <span className={`v7-label ${e.label}`}>{e.label.replace("_", " ")}</span>}
                    <span style={{ color: "var(--muted)", fontSize: "0.74rem" }}>{e.paper_id}</span>
                  </div>
                  <div style={{ fontSize: "0.84rem", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {e.title}
                  </div>
                  <div style={{ color: "var(--muted)", fontSize: "0.74rem", marginTop: 4, lineHeight: 1.35 }}>
                    {e.reason}
                  </div>
                </div>
              </li>
            ))}
          </ul>
          {bucket.entries.length > 3 && (
            <button className="v7-btn ghost" onClick={onToggle} style={{ marginTop: 8, width: "100%", justifyContent: "center" }}>
              {expanded ? "Show fewer" : `Show all ${bucket.entries.length} examples`}
            </button>
          )}
        </>
      )}
    </div>
  );
}
