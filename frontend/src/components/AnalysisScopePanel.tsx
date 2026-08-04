import { useState } from "react";

import type { AnalysisAudit } from "@/types";

interface Props {
  audit: AnalysisAudit;
  title?: string;
}

function percent(value: number, total: number): string {
  if (total <= 0) return "0%";
  return `${Math.round((value / total) * 100)}%`;
}

export function AnalysisScopePanel({ audit, title = "Evidence scope" }: Props) {
  const [copied, setCopied] = useState(false);
  const [auditCopied, setAuditCopied] = useState(false);
  const fingerprint = audit.filter_fingerprint.slice(0, 12);
  const sources = Object.entries(audit.corpus_source_breakdown).sort((a, b) => b[1] - a[1]);

  const copyFingerprint = async () => {
    await navigator.clipboard?.writeText(audit.filter_fingerprint);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  };
  const projection = audit.projection ?? audit.graph_filter;

  const copyAudit = async () => {
    await navigator.clipboard?.writeText(JSON.stringify(audit, null, 2));
    setAuditCopied(true);
    window.setTimeout(() => setAuditCopied(false), 1400);
  };

  return (
    <section className="analysis-scope" aria-label={`${title} audit`}>
      <header className="analysis-scope-header">
        <div>
          <span className="analysis-scope-kicker">Reproducible analysis</span>
          <h2>{title}</h2>
        </div>
        <button
          type="button"
          className="analysis-fingerprint"
          onClick={() => void copyFingerprint()}
          title="Copy full filter fingerprint"
        >
          scope {fingerprint} {copied ? "copied" : "copy"}
        </button>
      </header>

      <div className="analysis-scope-grid">
        <div><strong>{audit.included_papers}</strong><span>papers included</span></div>
        <div><strong>{percent(audit.reviewed_papers, audit.included_papers)}</strong><span>human reviewed</span></div>
        <div><strong>{percent(audit.fulltext_papers, audit.included_papers)}</strong><span>full text available</span></div>
        <div><strong>{audit.classified_papers}</strong><span>model classified</span></div>
      </div>

      <div className="analysis-source-strip" aria-label="Corpus source coverage">
        {sources.length > 0 ? sources.map(([source, count]) => (
          <span key={source}>{source.replace(/_/g, " ")} <strong>{count}</strong></span>
        )) : <span>No corpus-source provenance recorded</span>}
      </div>

      <details className="analysis-method">
        <summary>Algorithm and metric contract</summary>
        <dl>
          <div><dt>Algorithm</dt><dd><code>{audit.algorithm}</code></dd></div>
          {Object.entries(audit.metric_definitions).map(([metric, definition]) => (
            <div key={metric}><dt>{metric.replace(/_/g, " ")}</dt><dd>{definition}</dd></div>
          ))}
          {Object.entries(audit.filter_semantics ?? {}).map(([rule, definition]) => (
            <div key={rule}><dt>{rule.replace(/_/g, " ")}</dt><dd>{definition}</dd></div>
          ))}
          {projection && (
            <div><dt>Projection</dt><dd><code>{JSON.stringify(projection)}</code></dd></div>
          )}
          {audit.projection_fingerprint && (
            <div><dt>Projection hash</dt><dd><code>{audit.projection_fingerprint}</code></dd></div>
          )}
          <div><dt>Paper-set hash</dt><dd><code>{audit.paper_set_sha256}</code></dd></div>
          {audit.paper_set_encoding && (
            <div><dt>Paper-set encoding</dt><dd><code>{audit.paper_set_encoding}</code></dd></div>
          )}
          {Object.entries(audit.dependencies ?? {}).map(([name, dependency]) => (
            <div key={name}>
              <dt>{name.replace(/_/g, " ")} dependency</dt>
              <dd>
                {dependency.included_papers} papers · scope{" "}
                <code>{dependency.filter_fingerprint.slice(0, 12)}</code> · set{" "}
                <code>{dependency.paper_set_sha256}</code>
                {dependency.purpose ? ` · ${dependency.purpose}` : ""}
              </dd>
            </div>
          ))}
          {Object.entries(audit.evidence_subsets ?? {}).map(([name, subset]) => (
            <div key={name}>
              <dt>{name.replace(/_/g, " ")} evidence subset</dt>
              <dd>
                {subset.count} papers · set <code>{subset.paper_set_sha256}</code>
                {subset.paper_set_encoding ? ` · ${subset.paper_set_encoding}` : ""}
                {subset.purpose ? ` · ${subset.purpose}` : ""}
              </dd>
            </div>
          ))}
          <div><dt>Generated</dt><dd>{new Date(audit.generated_at).toLocaleString()}</dd></div>
        </dl>
        <button type="button" className="analysis-fingerprint" onClick={() => void copyAudit()}>
          {auditCopied ? "Audit copied" : "Copy full audit JSON"}
        </button>
      </details>
    </section>
  );
}
