import { useCallback, useEffect, useMemo, useState } from "react";

import { getDuplicateCandidates } from "@/lib/api";
import type { DuplicateGroup, DuplicateReport } from "@/types";

export default function DuplicateCandidatesPage() {
  const [report, setReport] = useState<DuplicateReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "blocker" | "warning">("all");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setReport(await getDuplicateCandidates());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const groups = useMemo(() => {
    const source = report?.groups ?? [];
    return filter === "all" ? source : source.filter((g) => g.severity === filter);
  }, [filter, report]);

  return (
    <div className="v7-page">
      <div className="v7-hero">
        <div>
          <h1>Duplicate Candidates</h1>
          <p>
            Same-title records with different DOI values, grouped for canonical review before website publication.
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
          <div className="label">Blocker groups</div>
          <div className="value">{report?.blocker_groups ?? 0}</div>
          <div className="delta">ambiguous DOI conflicts</div>
        </div>
        <div className="v7-stat">
          <div className="label">Warning groups</div>
          <div className="value">{report?.warning_groups ?? 0}</div>
          <div className="delta">likely version pairs</div>
        </div>
        <div className="v7-stat">
          <div className="label">Records involved</div>
          <div className="value">{report?.paper_count ?? 0}</div>
          <div className="delta">{report?.group_count ?? 0} duplicate groups</div>
        </div>
      </div>

      <div className="v7-card" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {(["all", "blocker", "warning"] as const).map((key) => (
          <button
            key={key}
            className={`v7-btn ${filter === key ? "" : "ghost"}`}
            onClick={() => setFilter(key)}
          >
            {key === "all" ? "All" : key}
          </button>
        ))}
      </div>

      {error && (
        <div className="v7-card" style={{ borderColor: "rgba(249,115,22,0.4)" }}>
          Backend error: {error}
        </div>
      )}

      {loading && !report ? (
        <div className="v7-gap-grid">
          <div className="v7-skel card" style={{ height: 240 }} />
          <div className="v7-skel card" style={{ height: 240 }} />
        </div>
      ) : groups.length === 0 ? (
        <div className="v7-empty">
          <span className="icon">OK</span>
          <div>No duplicate candidates in this filter.</div>
        </div>
      ) : (
        <div className="v7-gap-grid">
          {groups.map((group) => (
            <DuplicateGroupCard key={group.key} group={group} />
          ))}
        </div>
      )}
    </div>
  );
}

function DuplicateGroupCard({ group }: { group: DuplicateGroup }) {
  const isBlocker = group.severity === "blocker";
  return (
    <div className="v7-gap-card">
      <div className="gap-head">
        <h3>
          <span className={`v7-label ${isBlocker ? "EXCLUDE" : "UNCERTAIN"}`}>
            {group.severity}
          </span>
          {group.title}
        </h3>
        <span className="gap-count">{group.candidates.length}</span>
      </div>

      <div style={{ color: "var(--muted)", fontSize: "0.82rem", marginBottom: 10 }}>
        {group.reason}
      </div>

      <div style={{ display: "grid", gap: 8 }}>
        {group.candidates.map((candidate) => {
          const canonical = candidate.paper_id === group.canonical_paper_id;
          return (
            <button
              key={candidate.paper_id}
              className="v7-card"
              style={{
                textAlign: "left",
                borderColor: canonical ? "rgba(14,165,233,0.45)" : undefined,
                cursor: "pointer",
              }}
              onClick={() => window.open(`/?selected=${candidate.paper_id}`, "_blank")}
            >
              <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap", marginBottom: 6 }}>
                {canonical && <span className="v7-label CORE_RELEVANT">canonical</span>}
                {candidate.is_preprint && <span className="v7-label UNCERTAIN">preprint</span>}
                {candidate.label && (
                  <span className={`v7-label ${candidate.label}`}>{candidate.label.replace("_", " ")}</span>
                )}
                <span style={{ color: "var(--muted)", fontSize: "0.74rem" }}>{candidate.paper_id}</span>
              </div>
              <div style={{ fontSize: "0.84rem", lineHeight: 1.35, marginBottom: 6 }}>
                {candidate.doi ?? "No DOI"}
              </div>
              <div style={{ color: "var(--muted)", fontSize: "0.74rem", lineHeight: 1.35 }}>
                {candidate.provenance} · {candidate.year ?? "year unknown"} · score {candidate.score.toFixed(2)}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
