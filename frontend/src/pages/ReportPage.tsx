import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { FilterBar } from "@/components/FilterBar";
import { generateReport, API_BASE } from "@/lib/api";
import {
  isLatestRequest,
  resultForScope,
  type ScopedResult,
} from "@/lib/scopedResult";
import type { ReportResult } from "@/types";

const SECTIONS: { key: string; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "growth", label: "Growth" },
  { key: "themes", label: "Top themes" },
  { key: "emerging", label: "Emerging" },
  { key: "drift", label: "Topic drift" },
];

const BACKENDS = [
  { key: "template", label: "Templated (deterministic, no LLM)" },
  { key: "anthropic", label: "Anthropic Claude rewriter (optional)" },
];

const REPORT_ENTITIES: { key: string; label: string }[] = [
  { key: "none", label: "No entity restriction" },
  { key: "university_of_toronto", label: "University of Toronto" },
  { key: "toronto", label: "Toronto institutions" },
  { key: "ac_activity", label: "AC member activity" },
  { key: "ac_sdl_overlap", label: "AC + strict SDL overlap" },
];

const EVIDENCE_MODES: { key: string; label: string }[] = [
  { key: "human_only", label: "Human-confirmed SDL only" },
  { key: "human_high_confidence", label: "Human + high-confidence model SDL" },
  { key: "human_plus_probable", label: "Human + probable SDL" },
  { key: "all_threshold", label: "All model-classified (threshold)" },
];

/**
 * Render a [src:metric.key] tag as a clickable link back to the analytics
 * query that produced the number. The metric map gives us the actual URL.
 */
function ProseWithLinks({
  prose,
  metrics,
}: {
  prose: string;
  metrics: { key: string; source_link: string; label: string; value: string | number }[];
}) {
  const byKey = new Map(metrics.map((m) => [m.key, m]));
  const parts: (string | { tag: string })[] = [];
  const re = /\[src:([a-zA-Z0-9_.]+)\]/g;
  let cursor = 0;
  let match: RegExpExecArray | null;
  while ((match = re.exec(prose)) !== null) {
    if (match.index > cursor) parts.push(prose.slice(cursor, match.index));
    parts.push({ tag: match[1] });
    cursor = match.index + match[0].length;
  }
  if (cursor < prose.length) parts.push(prose.slice(cursor));

  return (
    <p className="report-prose">
      {parts.map((p, i) => {
        if (typeof p === "string") return <span key={i}>{p}</span>;
        const m = byKey.get(p.tag);
        if (!m) {
          return (
            <span key={i} className="report-src missing">
              [{p.tag}?]
            </span>
          );
        }
        return (
          <a
            key={i}
            href={`${API_BASE}${m.source_link}`}
            target="_blank"
            rel="noreferrer"
            className="report-src"
            title={`${m.label} = ${m.value}\n${m.source_link}`}
          >
            [src]
          </a>
        );
      })}
    </p>
  );
}

export default function ReportPage() {
  const [searchParams] = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [enabledSections, setEnabledSections] = useState<string[]>(
    SECTIONS.map((s) => s.key)
  );
  const [backend, setBackend] = useState<string>("template");
  const [reportEntity, setReportEntity] = useState<string>("none");
  const [evidenceMode, setEvidenceMode] = useState<string>("human_plus_probable");
  const [confidenceThreshold, setConfidenceThreshold] = useState<number>(0.8);
  const [allowNeedsFulltext, setAllowNeedsFulltext] = useState(false);
  const [allowAbstractOnly, setAllowAbstractOnly] = useState(false);
  const [excludeUnreviewedBroad, setExcludeUnreviewedBroad] = useState(true);
  const [includeModelOnly, setIncludeModelOnly] = useState(false);
  const searchKey = searchParams.toString();
  const policyState = JSON.stringify([
    reportEntity,
    evidenceMode,
    confidenceThreshold,
    allowNeedsFulltext,
    allowAbstractOnly,
    excludeUnreviewedBroad,
    includeModelOnly,
  ]);
  const scopeKey = JSON.stringify([searchKey, enabledSections, backend, policyState]);
  const [reportResult, setReportResult] = useState<
    ScopedResult<ReportResult> | null
  >(null);
  const report = resultForScope(reportResult, scopeKey);
  const requestGeneration = useRef(0);

  useEffect(() => {
    requestGeneration.current += 1;
    setError(null);
    setGenerating(false);
  }, [scopeKey]);

  const handleGenerate = async () => {
    const generation = ++requestGeneration.current;
    const requestScopeKey = scopeKey;
    setGenerating(true);
    setError(null);
    try {
      const nextReport = await generateReport(
        {
          sections: enabledSections,
          backend,
          report_entity: reportEntity,
          report_evidence_mode: evidenceMode,
          report_evidence_confidence_threshold: confidenceThreshold,
          report_evidence_include_model_only: includeModelOnly,
          report_evidence_allow_needs_fulltext: allowNeedsFulltext,
          report_evidence_allow_abstract_only: allowAbstractOnly,
          report_evidence_exclude_unreviewed_broad: excludeUnreviewedBroad,
        },
        new URLSearchParams(searchKey)
      );
      if (isLatestRequest(generation, requestGeneration.current)) {
        setReportResult({ scopeKey: requestScopeKey, payload: nextReport });
      }
    } catch (err) {
      if (isLatestRequest(generation, requestGeneration.current)) {
        setError(err instanceof Error ? err.message : String(err));
        setReportResult(null);
      }
    } finally {
      if (isLatestRequest(generation, requestGeneration.current)) setGenerating(false);
    }
  };

  return (
    <div>
      <FilterBar />
      <div className="report-controls">
        <div className="report-section-toggles">
          {SECTIONS.map((s) => (
            <button
              key={s.key}
              className={`chip-toggle ${enabledSections.includes(s.key) ? "active" : ""}`}
              onClick={() =>
                setEnabledSections((cur) =>
                  cur.includes(s.key)
                    ? cur.filter((k) => k !== s.key)
                    : [...cur, s.key]
                )
              }
            >
              {s.label}
            </button>
          ))}
        </div>
        <label>
          Reporting entity:&nbsp;
          <select
            value={reportEntity}
            onChange={(e) => setReportEntity(e.target.value)}
          >
            {REPORT_ENTITIES.map((r) => (
              <option key={r.key} value={r.key}>
                {r.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Backend:&nbsp;
          <select value={backend} onChange={(e) => setBackend(e.target.value)}>
            {BACKENDS.map((b) => (
              <option key={b.key} value={b.key}>
                {b.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Evidence scope:&nbsp;
          <select
            value={evidenceMode}
            onChange={(e) => setEvidenceMode(e.target.value)}
          >
            {EVIDENCE_MODES.map((m) => (
              <option key={m.key} value={m.key}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
        {(evidenceMode === "human_high_confidence" ||
          evidenceMode === "all_threshold") && (
          <label>
            Confidence:&nbsp;
            <input
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={confidenceThreshold}
              onChange={(e) => setConfidenceThreshold(Number(e.target.value))}
              style={{ width: "5rem" }}
            />
          </label>
        )}
        <label className="chip-toggle">
          <input
            type="checkbox"
            checked={allowNeedsFulltext}
            onChange={(e) => setAllowNeedsFulltext(e.target.checked)}
          />
          Allow NEEDS_FULLTEXT
        </label>
        <label className="chip-toggle">
          <input
            type="checkbox"
            checked={allowAbstractOnly}
            onChange={(e) => setAllowAbstractOnly(e.target.checked)}
          />
          Allow abstract-only
        </label>
        <label className="chip-toggle">
          <input
            type="checkbox"
            checked={excludeUnreviewedBroad}
            onChange={(e) => setExcludeUnreviewedBroad(e.target.checked)}
          />
          Exclude unreviewed broad retrieval
        </label>
        <label className="chip-toggle">
          <input
            type="checkbox"
            checked={includeModelOnly}
            onChange={(e) => setIncludeModelOnly(e.target.checked)}
          />
          Show model-only separately
        </label>
        <button onClick={() => void handleGenerate()} disabled={generating}>
          {generating ? "Generating…" : "Generate report"}
        </button>
      </div>

      <p style={{ color: "var(--muted)", marginTop: "0.6rem" }}>
        Every <code>[src]</code> tag links back to the analytics query that
        produced that number. The reporting layer never invents digits — if a
        sentence claims a number, that number is in the metrics table below
        the prose. The templated backend is fully deterministic; the
        Anthropic backend is allowed to rewrite sentence structure but
        cannot introduce new numbers (the API validates this).
      </p>

      {error && (
        <div style={{ color: "var(--uncertain)" }}>Backend error: {error}</div>
      )}

      {report && (
        <>
          <div className="report-meta">
            <span>Period: <strong>{report.period_label}</strong></span>
            <span>Backend: <strong>{report.backend}</strong></span>
            <span>
              Evidence:{" "}
              <strong>
                {report.evidence_policy?.mode ?? evidenceMode}
                {report.evidence_policy?.confidence_threshold !== undefined &&
                report.evidence_policy.confidence_threshold > 0
                  ? ` ≥ ${report.evidence_policy.confidence_threshold}`
                  : ""}
              </strong>
            </span>
            <span>Generated: <strong>{new Date(report.generated_at).toLocaleString()}</strong></span>
          </div>

          {report.sections.map((s) => (
            <section key={s.key} className="report-section">
              <h3>{s.title}</h3>
              <ProseWithLinks prose={s.prose} metrics={s.metrics} />
              <details>
                <summary style={{ color: "var(--muted)" }}>
                  Metric trace ({s.metrics.length})
                </summary>
                <table className="eval-table" style={{ marginTop: "0.4rem" }}>
                  <thead>
                    <tr>
                      <th>Key</th>
                      <th>Label</th>
                      <th>Value</th>
                      <th>Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {s.metrics.map((m) => (
                      <tr key={m.key}>
                        <td>
                          <code>{m.key}</code>
                        </td>
                        <td>{m.label}</td>
                        <td>{String(m.value)}</td>
                        <td>
                          <a
                            href={`${API_BASE}${m.source_link}`}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {m.source_link}
                          </a>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            </section>
          ))}
        </>
      )}
    </div>
  );
}
