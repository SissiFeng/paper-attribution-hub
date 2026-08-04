import { useCallback, useEffect, useState } from "react";

import {
  getModelEvolutionStatus,
  listPipelineRuns,
  runPipeline,
} from "@/lib/api";
import type {
  ModelEvolutionStatus,
  ModelMetricSummary,
  PipelineRun,
  PipelineRunInput,
  PipelineStepLog,
} from "@/types";

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

function stepCount(step: PipelineStepLog | undefined, key: string): number {
  const value = step?.[key];
  return typeof value === "number" ? value : 0;
}

function metricPercent(
  metrics: ModelMetricSummary | null,
  key: "accuracy" | "macro_f1"
): string {
  const value = metrics?.[key];
  return typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "—";
}

function metricDelta(
  candidate: ModelMetricSummary | null,
  incumbent: ModelMetricSummary | null,
  key: "accuracy" | "macro_f1"
): string {
  const next = candidate?.[key];
  const current = incumbent?.[key];
  if (typeof next !== "number" || typeof current !== "number") return "—";
  const delta = (next - current) * 100;
  return `${delta >= 0 ? "+" : ""}${delta.toFixed(1)} pp`;
}

export default function PipelineStatusPage() {
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [evolution, setEvolution] = useState<ModelEvolutionStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const [opts, setOpts] = useState<PipelineRunInput>({
    do_discovery: false,
    do_fulltext: false,
    use_learned: true,
    use_judge: false,
    triggered_by: "manual",
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [rows, modelStatus] = await Promise.all([
        listPipelineRuns(30),
        getModelEvolutionStatus(),
      ]);
      setRuns(rows);
      setEvolution(modelStatus);
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
  const latestScreening = latest?.steps?.find(
    (step) => step.name === "staged_screening"
  );
  const scored = stepCount(latestScreening, "scored");
  const seedReference = stepCount(latestScreening, "seed_reference");
  const reviewSubset = stepCount(latestScreening, "review_subset");
  const positiveReview = stepCount(latestScreening, "positive_review");
  const uncertainReview = stepCount(latestScreening, "uncertain_review");
  const fulltextReview = stepCount(latestScreening, "fulltext_review");
  const screenedOut = stepCount(latestScreening, "screened_out");
  const learningRun = evolution?.active_run ?? evolution?.latest_run ?? null;
  const pulseSize = evolution?.batch_size ?? 20;
  const pulseFilled = Math.min(evolution?.pending_reviews ?? 0, pulseSize);

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

      {evolution && (
        <section
          className="v7-card model-evolution"
          aria-labelledby="model-evolution-title"
        >
          <div className="model-evolution-heading">
            <div>
              <span className="review-kicker">Human review → model evolution</span>
              <h2 id="model-evolution-title">
                <span className="accent-dot" /> 20-review learning pulse
              </h2>
            </div>
            <span
              className={`model-evolution-status ${
                evolution.active_run ? "running" : learningRun?.status.toLowerCase() ?? "idle"
              }`}
            >
              {evolution.active_run ? "training" : learningRun?.status.toLowerCase() ?? "waiting"}
            </span>
          </div>

          <div className="model-evolution-body">
            <div className="learning-pulse-panel">
              <div className="learning-pulse-copy">
                <strong>
                  {evolution.pending_reviews} / {evolution.batch_size}
                </strong>
                <span>
                  {evolution.reviews_until_retrain === 0
                    ? "batch ready for full retraining"
                    : `${evolution.reviews_until_retrain} qualified reviews until the next full retrain`}
                </span>
              </div>
              <div
                className="learning-pulse"
                role="progressbar"
                aria-label="Qualified review progress toward full retraining"
                aria-valuemin={0}
                aria-valuemax={evolution.batch_size}
                aria-valuenow={evolution.pending_reviews}
              >
                {Array.from({ length: pulseSize }, (_, index) => (
                  <span
                    key={index}
                    className={index < pulseFilled ? "filled" : ""}
                    aria-hidden="true"
                  />
                ))}
              </div>
              <div className="learning-pulse-model">
                <span>Production authority</span>
                <code>
                  {evolution.production_authority.status} · {evolution.current_model_version ?? "rules-only baseline"}
                </code>
              </div>
              <div
                className={`validation-readiness ${
                  evolution.production_authority.status === "VERIFIED"
                    || evolution.production_authority.status === "LEGACY_CACHE"
                    ? "ready"
                    : "blocked"
                }`}
              >
                <strong>
                  Serving authority · {evolution.production_authority.status.toLowerCase().replace(/_/g, " ")}
                </strong>
                <span>
                  {evolution.production_authority.error
                    ?? (evolution.production_authority.status === "RULES_ONLY"
                      ? "No learned artifact is currently serving; predictions use the rules baseline."
                      : "The serving artifact passed authority verification.")}
                </span>
                <small>
                  run {evolution.production_authority.production_run_id ?? "none"}
                  {" · "}artifact {evolution.production_authority.artifact_sha256?.slice(0, 12) ?? "none"}
                  {" · "}cache {evolution.production_authority.cache_sync_status ?? (evolution.production_authority.cache_present ? "legacy" : "absent")}
                  {" · "}hash match {String(evolution.production_authority.cache_matches_authority ?? false)}
                </small>
              </div>
              <div
                className={`validation-readiness ${
                  evolution.validation_gate.ready ? "ready" : "blocked"
                }`}
              >
                <strong>
                  Fixed validation · {evolution.validation_gate.ready ? "ready" : "promotion blocked"}
                </strong>
                <span>{evolution.validation_gate.reason}</span>
                <small>
                  {evolution.validation_gate.observed_examples} / {evolution.validation_gate.required_examples} examples
                  {" · "}{evolution.validation_gate.observed_labels.length} / {evolution.validation_gate.required_labels} labels
                </small>
              </div>
            </div>

            <div className="model-gate-panel">
              {learningRun ? (
                <>
                  <div className="model-gate-meta">
                    <span>{learningRun.evaluation_scope ?? "evaluation pending"}</span>
                    <span>{fmtTime(learningRun.started_at)}</span>
                  </div>
                  <div className="model-gate-metrics">
                    <div>
                      <span>Macro F1</span>
                      <strong>{metricPercent(learningRun.candidate_metrics, "macro_f1")}</strong>
                      <small>
                        {metricDelta(
                          learningRun.candidate_metrics,
                          learningRun.incumbent_metrics,
                          "macro_f1"
                        )}
                      </small>
                    </div>
                    <div>
                      <span>Accuracy</span>
                      <strong>{metricPercent(learningRun.candidate_metrics, "accuracy")}</strong>
                      <small>
                        {metricDelta(
                          learningRun.candidate_metrics,
                          learningRun.incumbent_metrics,
                          "accuracy"
                        )}
                      </small>
                    </div>
                  </div>
                  <p>{learningRun.error_message ?? learningRun.promotion_reason}</p>
                  <details className="analysis-method">
                    <summary>Training decision audit</summary>
                    <dl>
                      <div><dt>Lease</dt><dd><code>{learningRun.lease_generation}</code></dd></div>
                      <div><dt>Trigger events</dt><dd>{learningRun.trigger_event_ids.length}</dd></div>
                      <div><dt>Training dataset</dt><dd><code>{learningRun.training_dataset_hash ?? "pending"}</code></dd></div>
                      <div><dt>Validation dataset</dt><dd><code>{learningRun.validation_dataset_hash ?? "not materialized"}</code></dd></div>
                      <div><dt>Candidate artifact</dt><dd><code>{learningRun.candidate_model_sha256 ?? "pending"}</code></dd></div>
                      <div><dt>Incumbent artifact</dt><dd><code>{learningRun.incumbent_model_sha256 ?? "rules-only"}</code></dd></div>
                      <div><dt>Cache</dt><dd>{learningRun.cache_sync_status ?? "pending"}</dd></div>
                      <div><dt>Gate</dt><dd><code>{JSON.stringify(learningRun.promotion_gate_config)}</code></dd></div>
                      <div><dt>Runtime</dt><dd><code>{JSON.stringify(learningRun.runtime_versions)}</code></dd></div>
                    </dl>
                  </details>
                </>
              ) : (
                <p className="model-gate-empty">
                  No retraining attempt yet. The first complete review batch will
                  establish an auditable candidate-versus-incumbent comparison.
                </p>
              )}
            </div>
          </div>

          <div className="model-evolution-contract">
            <span><b>Full retrain</b> on every allowed label</span>
            <span><b>Leakage-safe gate</b> before promotion</span>
            <span><b>DB-authoritative promotion</b> with rebuildable cache</span>
          </div>
        </section>
      )}

      {latestScreening && (
        <section className="v7-card screening-funnel" aria-labelledby="screening-funnel-title">
          <div className="screening-funnel-heading">
            <div>
              <span className="review-kicker">Latest staged screening</span>
              <h2 id="screening-funnel-title">
                <span className="accent-dot" /> Broad corpus → focused review
              </h2>
            </div>
            <span className="screening-funnel-run">
              {latest ? fmtTime(latest.started_at) : "—"}
            </span>
          </div>
          <div className="screening-funnel-rail">
            <div className="screening-funnel-node seed">
              <span>01 · labeled foundation</span>
              <strong>{seedReference.toLocaleString()}</strong>
              <small>explicit training seeds</small>
            </div>
            <span className="screening-funnel-arrow" aria-hidden="true">→</span>
            <div className="screening-funnel-node scored">
              <span>02 · machine triage</span>
              <strong>{scored.toLocaleString()}</strong>
              <small>papers scored in broad corpus</small>
            </div>
            <span className="screening-funnel-arrow" aria-hidden="true">→</span>
            <div className="screening-funnel-node review">
              <span>03 · human attention</span>
              <strong>{reviewSubset.toLocaleString()}</strong>
              <small>
                {positiveReview.toLocaleString()} positive ·{" "}
                {uncertainReview.toLocaleString()} uncertain ·{" "}
                {fulltextReview.toLocaleString()} full text
              </small>
            </div>
          </div>
          <div className="screening-funnel-foot">
            <span>
              <b>{screenedOut.toLocaleString()}</b> high-confidence non-positive
              papers remain searchable without entering the review queue.
            </span>
            <span>
              Review load:{" "}
              <b>{scored ? ((reviewSubset / scored) * 100).toFixed(1) : "0.0"}%</b>
              {" "}of scored corpus
            </span>
          </div>
        </section>
      )}

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
