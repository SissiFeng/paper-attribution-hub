import { useCallback, useEffect, useState } from "react";

import { listPipelineRuns, runPipeline } from "@/lib/api";
import type { PipelineRun, PipelineRunInput, PipelineStepLog } from "@/types";

interface Toast {
  text: string;
  kind: "success" | "error";
}

function fmtTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtDuration(seconds: number): string {
  if (seconds < 1) return `${(seconds * 1000).toFixed(0)}ms`;
  if (seconds < 60) return `${seconds.toFixed(2)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

function stepIcon(status?: string): { icon: string; cls: string } {
  if (status === "ok") return { icon: "✓", cls: "ok" };
  if (status === "skipped" || status === "disabled") return { icon: "⊝", cls: "skipped" };
  if (status === "failed") return { icon: "✗", cls: "failed" };
  return { icon: "•", cls: "skipped" };
}

function stepSummary(step: PipelineStepLog): string {
  // Extract meaningful counts from step
  const counts: string[] = [];
  for (const [k, v] of Object.entries(step)) {
    if (
      ["name", "status", "started_at", "error"].includes(k) ||
      typeof v !== "number"
    )
      continue;
    counts.push(`${k}=${v}`);
  }
  if (step.error) return String(step.error);
  return counts.length ? counts.join(" · ") : "";
}

export default function PipelineStatusPage() {
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const [opts, setOpts] = useState<PipelineRunInput>({
    do_discovery: false,
    do_fulltext: false,
    use_learned: false,
    use_judge: false,
    triggered_by: "manual",
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await listPipelineRuns(30);
      setRuns(rows);
    } catch (e) {
      setToast({ text: e instanceof Error ? e.message : String(e), kind: "error" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(t);
  }, [toast]);

  const handleRun = async () => {
    setTriggering(true);
    try {
      const result = await runPipeline(opts);
      setToast({
        text: `Run ${result.run_id.slice(0, 12)}… ${result.status} in ${fmtDuration(result.duration_seconds)}`,
        kind: result.status === "success" ? "success" : "error",
      });
      await load();
    } catch (e) {
      setToast({ text: e instanceof Error ? e.message : String(e), kind: "error" });
    } finally {
      setTriggering(false);
    }
  };

  const latest = runs[0];
  const successCount = runs.filter((r) => r.status === "success").length;
  const totalClassified = runs.reduce((sum, r) => sum + r.classified_new, 0);
  const totalFlagged = runs.reduce((sum, r) => sum + r.enqueued_for_review, 0);

  return (
    <div className="v7-page">
      <div className="v7-hero">
        <div>
          <h1>Pipeline Status</h1>
          <p>
            Audit log for the daily scheduled pipeline. Trigger an on-demand run, or scroll
            through history to see what the system has been doing while you weren't watching.
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
          <div className="label">Last run</div>
          <div className="value" style={{ fontSize: "1.2rem" }}>
            {latest ? fmtTime(latest.started_at) : "—"}
          </div>
          <div className="delta">
            {latest ? (
              <>
                {latest.status === "success" ? "✓ success" : "⚠ failed"} · {fmtDuration(latest.duration_seconds)}
              </>
            ) : (
              "no runs yet"
            )}
          </div>
        </div>
        <div className="v7-stat">
          <div className="label">Success rate</div>
          <div className="value">
            {runs.length ? Math.round((successCount / runs.length) * 100) : 0}%
          </div>
          <div className="delta">
            {successCount} / {runs.length} runs
          </div>
        </div>
        <div className="v7-stat">
          <div className="label">Papers classified</div>
          <div className="value">{totalClassified}</div>
          <div className="delta">across {runs.length} runs</div>
        </div>
        <div className="v7-stat">
          <div className="label">Flagged for review</div>
          <div className="value">{totalFlagged}</div>
          <div className="delta">total queued by pipeline</div>
        </div>
      </div>

      <div className="v7-card">
        <h2>
          <span className="accent-dot" /> Manual trigger
        </h2>
        <div className="v7-trigger">
          <div className="v7-toggle-row">
            <label className={`v7-toggle ${opts.do_discovery ? "on" : ""}`}>
              <input
                type="checkbox"
                checked={!!opts.do_discovery}
                onChange={(e) => setOpts({ ...opts, do_discovery: e.target.checked })}
              />
              <span className="check">{opts.do_discovery ? "✓" : ""}</span>
              Discovery (OpenAlex / S2 / Crossref)
            </label>
            <label className={`v7-toggle ${opts.do_fulltext ? "on" : ""}`}>
              <input
                type="checkbox"
                checked={!!opts.do_fulltext}
                onChange={(e) => setOpts({ ...opts, do_fulltext: e.target.checked })}
              />
              <span className="check">{opts.do_fulltext ? "✓" : ""}</span>
              Full-text evidence refresh
            </label>
            <label className={`v7-toggle ${opts.use_learned ? "on" : ""}`}>
              <input
                type="checkbox"
                checked={!!opts.use_learned}
                onChange={(e) => setOpts({ ...opts, use_learned: e.target.checked })}
              />
              <span className="check">{opts.use_learned ? "✓" : ""}</span>
              Learned classifier override
            </label>
            <label className={`v7-toggle ${opts.use_judge ? "on" : ""}`}>
              <input
                type="checkbox"
                checked={!!opts.use_judge}
                onChange={(e) => setOpts({ ...opts, use_judge: e.target.checked })}
              />
              <span className="check">{opts.use_judge ? "✓" : ""}</span>
              LLM judge for borderline
            </label>
          </div>
          <div className="v7-btn-row">
            <button
              className="v7-btn primary"
              onClick={handleRun}
              disabled={triggering}
            >
              {triggering ? (
                <>
                  <span className="v7-pulse-dot" />
                  Running…
                </>
              ) : (
                "▶ Run pipeline now"
              )}
            </button>
            <span style={{ color: "var(--muted)", fontSize: "0.84rem", alignSelf: "center" }}>
              Same logic as the daily cron.
            </span>
          </div>
        </div>
      </div>

      <div className="v7-card">
        <h2>
          <span className="accent-dot" /> Recent runs
        </h2>
        {loading && runs.length === 0 ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div className="v7-skel card" style={{ height: 64 }} />
            <div className="v7-skel card" style={{ height: 64 }} />
            <div className="v7-skel card" style={{ height: 64 }} />
          </div>
        ) : runs.length === 0 ? (
          <div className="v7-empty">
            <span className="icon">📭</span>
            <div>No pipeline runs recorded yet.</div>
            <div style={{ marginTop: 8, fontSize: 13 }}>
              Click "Run pipeline now" above to start.
            </div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {runs.map((run) => {
              const expanded = expandedId === run.run_id;
              return (
                <div key={run.run_id}>
                  <div
                    className="v7-run-row"
                    style={{ cursor: "pointer" }}
                    onClick={() =>
                      setExpandedId(expanded ? null : run.run_id)
                    }
                  >
                    <div className="timestamp">{fmtTime(run.started_at)}</div>
                    <span className={`status-chip ${run.status}`}>{run.status}</span>
                    <div className="stats">
                      <span>
                        <b>{run.classified_new}</b> classified
                      </span>
                      <span>
                        <b>{run.enqueued_for_review}</b> flagged
                      </span>
                      <span>
                        <b>{run.discovered_candidates}</b> discovered
                      </span>
                      <span style={{ color: "var(--muted)" }}>
                        via {run.triggered_by}
                      </span>
                    </div>
                    <div className="duration">{fmtDuration(run.duration_seconds)}</div>
                  </div>
                  {expanded && (
                    <div className="v7-run-detail">
                      <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 6 }}>
                        run_id: <code>{run.run_id}</code>
                      </div>
                      {run.error_message && (
                        <div
                          style={{
                            background: "rgba(249,115,22,0.08)",
                            color: "var(--uncertain)",
                            padding: 8,
                            borderRadius: 6,
                            fontSize: 13,
                            marginBottom: 8,
                            fontFamily: "ui-monospace, monospace",
                          }}
                        >
                          {run.error_message}
                        </div>
                      )}
                      {(run.steps ?? []).map((step, i) => {
                        const { icon, cls } = stepIcon(step.status);
                        return (
                          <div key={i} className="v7-step-row">
                            <span className={`check ${cls}`}>{icon}</span>
                            <span className="step-name">{step.name}</span>
                            <span className="step-detail" style={{ fontSize: "0.78rem" }}>
                              {step.status ?? "—"}
                            </span>
                            <span className="step-detail">{stepSummary(step)}</span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {toast && <div className={`v7-toast ${toast.kind}`}>{toast.text}</div>}
    </div>
  );
}
