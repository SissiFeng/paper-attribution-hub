import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { FilterBar } from "@/components/FilterBar";
import { generateReport, API_BASE } from "@/lib/api";
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
  const [report, setReport] = useState<ReportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [enabledSections, setEnabledSections] = useState<string[]>(
    SECTIONS.map((s) => s.key)
  );
  const [backend, setBackend] = useState<string>("template");

  const handleGenerate = async () => {
    setGenerating(true);
    setError(null);
    try {
      const r = await generateReport(
        { sections: enabledSections, backend },
        searchParams
      );
      setReport(r);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setGenerating(false);
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
          Backend:&nbsp;
          <select value={backend} onChange={(e) => setBackend(e.target.value)}>
            {BACKENDS.map((b) => (
              <option key={b.key} value={b.key}>
                {b.label}
              </option>
            ))}
          </select>
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
