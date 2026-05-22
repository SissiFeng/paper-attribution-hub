import { useCallback, useEffect, useState } from "react";

import { getEvidenceGaps } from "@/lib/api";
import type { EvidenceGapBucket, EvidenceGapReport, RelevanceLabel } from "@/types";

const ICON_FOR_BUCKET: Record<string, string> = {
  core_missing_funding: "💸",
  core_missing_methods: "🧪",
  adjacent_with_funding: "⤴",
  disqualifying_vs_high_label: "⚠",
  low_confidence_auto_core: "🤖",
};

export default function EvidenceGapsPage() {
  const [report, setReport] = useState<EvidenceGapReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedBucket, setExpandedBucket] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getEvidenceGaps();
      setReport(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const totalGaps =
    report?.buckets.reduce((s, b) => s + b.count, 0) ?? 0;

  return (
    <div className="v7-page">
      <div className="v7-hero">
        <div>
          <h1>Evidence Gaps</h1>
          <p>
            Where the classifier's confidence and the underlying evidence disagree. Each card
            surfaces a different failure mode — drill in to see the offending papers and decide
            whether to confirm, correct, or chase the missing evidence.
          </p>
        </div>
        <div className="v7-hero-actions">
          <button className="v7-btn" onClick={() => void load()} disabled={loading}>
            ↻ Refresh
          </button>
        </div>
      </div>

      <div className="v7-stat-grid">
        <div className="v7-stat">
          <div className="label">Total gaps</div>
          <div className="value">{totalGaps}</div>
          <div className="delta">across all buckets</div>
        </div>
        <div className="v7-stat">
          <div className="label">Scanned</div>
          <div className="value">{report?.total_papers_scanned ?? 0}</div>
          <div className="delta">classified papers</div>
        </div>
        <div className="v7-stat">
          <div className="label">Buckets with gaps</div>
          <div className="value">
            {report?.buckets.filter((b) => b.count > 0).length ?? 0}
          </div>
          <div className="delta">of {report?.buckets.length ?? 0} total</div>
        </div>
      </div>

      {error && (
        <div
          className="v7-card"
          style={{ borderColor: "rgba(249,115,22,0.4)", color: "var(--uncertain)" }}
        >
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
          <span className="icon">✨</span>
          <div>No evidence gaps detected.</div>
          <div style={{ marginTop: 8, fontSize: 13 }}>
            Every classified paper has consistent supporting evidence.
          </div>
        </div>
      ) : (
        <div className="v7-gap-grid">
          {report.buckets.map((bucket) => (
            <BucketCard
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

function BucketCard({
  bucket,
  expanded,
  onToggle,
}: {
  bucket: EvidenceGapBucket;
  expanded: boolean;
  onToggle: () => void;
}) {
  const icon = ICON_FOR_BUCKET[bucket.bucket] ?? "•";
  const isEmpty = bucket.count === 0;
  return (
    <div
      className="v7-gap-card"
      style={isEmpty ? { opacity: 0.6 } : {}}
    >
      <div className="gap-head">
        <h3>
          <span style={{ fontSize: "1.2rem" }}>{icon}</span>
          {bucket.label}
        </h3>
        <span className="gap-count">{bucket.count}</span>
      </div>
      <div style={{ color: "var(--muted)", fontSize: "0.82rem", marginBottom: 8 }}>
        {bucket.description}
      </div>

      {bucket.entries.length === 0 ? (
        <div style={{ color: "var(--muted)", fontSize: "0.84rem", padding: "0.4rem 0" }}>
          {isEmpty ? "Nothing in this bucket — nice." : "No examples loaded."}
        </div>
      ) : (
        <>
          <ul className="v7-gap-list">
            {(expanded ? bucket.entries : bucket.entries.slice(0, 3)).map((e) => (
              <li
                key={e.paper_id}
                onClick={() => {
                  window.open(`/?selected=${e.paper_id}`, "_blank");
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      display: "flex",
                      gap: 6,
                      alignItems: "center",
                      marginBottom: 4,
                    }}
                  >
                    <span className={`v7-label ${e.label as RelevanceLabel}`}>
                      {e.label.replace("_", " ")}
                    </span>
                    <span style={{ color: "var(--muted)", fontSize: "0.74rem" }}>
                      conf {e.confidence.toFixed(2)}
                    </span>
                  </div>
                  <div
                    style={{
                      fontSize: "0.84rem",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {e.title}
                  </div>
                  <div
                    style={{
                      color: "var(--muted)",
                      fontSize: "0.74rem",
                      marginTop: 4,
                      lineHeight: 1.35,
                    }}
                  >
                    {e.reason}
                  </div>
                </div>
                {e.missing_types.length > 0 && (
                  <span className="missing">
                    missing {e.missing_types.join(", ")}
                  </span>
                )}
              </li>
            ))}
          </ul>
          {bucket.entries.length > 3 && (
            <button
              className="v7-btn ghost"
              onClick={onToggle}
              style={{ marginTop: 8, width: "100%", justifyContent: "center" }}
            >
              {expanded
                ? "Show fewer"
                : `Show all ${bucket.entries.length} examples`}
            </button>
          )}
        </>
      )}
    </div>
  );
}
