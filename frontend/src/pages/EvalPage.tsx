import { useCallback, useEffect, useState } from "react";

import { getEvalReport } from "@/lib/api";
import type { EvalReport } from "@/types";

export default function EvalPage() {
  const [report, setReport] = useState<EvalReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [k, setK] = useState(5);

  const load = useCallback(async () => {
    setError(null);
    try {
      const r = await getEvalReport(k);
      setReport(r);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [k]);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) {
    return (
      <div style={{ color: "var(--uncertain)" }}>
        {error}. Make sure <code>data/eval_labels.csv</code> exists and the API
        is running.
      </div>
    );
  }
  if (!report) {
    return <div className="empty">Loading…</div>;
  }

  const labels = Object.keys(report.confusion);

  return (
    <div>
      <div className="eval-scope-notice" role="note">
        <strong>{report.label_scope ?? "UNSPECIFIED"} reference set</strong>
        <span>
          {report.allowed_claim ??
            "The label scope is not documented; treat these metrics as diagnostic."}
        </span>
        {(report.annotation_sources?.length ?? 0) > 0 && (
          <small>
            Annotation source: {report.annotation_sources?.join(", ")} · Evidence:{" "}
            {report.evidence_levels?.join(", ")}
          </small>
        )}
      </div>
      <div className="eval-headline">
        <div className="cell">
          <div className="label">Accuracy</div>
          <div className="value">{(report.accuracy * 100).toFixed(1)}%</div>
        </div>
        <div className="cell">
          <div className="label">Macro F1</div>
          <div className="value">{report.macro_f1.toFixed(3)}</div>
        </div>
        <div className="cell">
          <div className="label">Macro P / R</div>
          <div className="value">
            {report.macro_precision.toFixed(2)} / {report.macro_recall.toFixed(2)}
          </div>
        </div>
        <div className="cell">
          <div className="label">Evidence recall@{report.k}</div>
          <div className="value">
            {report.evidence_recall_at_k != null
              ? `${(report.evidence_recall_at_k * 100).toFixed(1)}%`
              : "—"}
          </div>
        </div>
        <div className="cell">
          <div className="label">Papers evaluated</div>
          <div className="value">{report.n_evaluated}</div>
        </div>
      </div>

      <div className="filters">
        <label>
          k:&nbsp;
          <input
            type="number"
            min={1}
            max={20}
            value={k}
            onChange={(e) => setK(Number(e.target.value))}
            style={{ width: 70 }}
          />
        </label>
        <button onClick={() => void load()}>Recompute</button>
      </div>

      <h3>Per-label metrics</h3>
      <table className="eval-table">
        <thead>
          <tr>
            <th>Label</th>
            <th>Precision</th>
            <th>Recall</th>
            <th>F1</th>
            <th>Support</th>
          </tr>
        </thead>
        <tbody>
          {report.per_label.map((m) => (
            <tr key={m.label}>
              <td>{m.label.replace(/_/g, " ")}</td>
              <td>{m.precision.toFixed(3)}</td>
              <td>{m.recall.toFixed(3)}</td>
              <td>{m.f1.toFixed(3)}</td>
              <td>{m.support}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 style={{ marginTop: "1.6rem" }}>
        Confusion matrix (rows = reference, cols = prediction)
      </h3>
      <table className="eval-table">
        <thead>
          <tr>
            <th></th>
            {labels.map((l) => (
              <th key={l}>{l.replace(/_/g, " ")}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {labels.map((gold) => (
            <tr key={gold}>
              <th>{gold.replace(/_/g, " ")}</th>
              {labels.map((pred) => (
                <td key={pred}>{report.confusion[gold]?.[pred] ?? 0}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
