import { useEffect, useState } from "react";

import { ClassificationBadge, ConfidenceBar } from "@/components/ClassificationBadge";
import { RagStatusPanel } from "@/components/RagStatusBadge";
import { WikiPanel } from "@/components/WikiPanel";
import { getGraphExplanation, submitReview } from "@/lib/api";
import type { FulltextEvidence, GraphExplanation, Paper } from "@/types";

function FulltextEvidenceTabs({ evidence }: { evidence: FulltextEvidence[] }) {
  const positive = evidence.filter((e) => e.evidence_type !== "disqualifying" && e.score >= 0);
  const negative = evidence.filter((e) => e.evidence_type === "disqualifying" || e.score < 0);
  const [tab, setTab] = useState<"positive" | "negative">(
    positive.length === 0 && negative.length > 0 ? "negative" : "positive"
  );

  if (positive.length === 0 && negative.length === 0) return null;

  return (
    <>
      <h3>Full-text evidence</h3>
      <div className="v7-subtabs" style={{ marginBottom: "0.6rem" }}>
        <button
          className={tab === "positive" ? "active" : ""}
          onClick={() => setTab("positive")}
          type="button"
        >
          Supporting ({positive.length})
        </button>
        <button
          className={tab === "negative" ? "active" : ""}
          onClick={() => setTab("negative")}
          type="button"
          style={{ color: negative.length ? "var(--uncertain)" : undefined }}
        >
          Disqualifying ({negative.length})
        </button>
      </div>

      {tab === "positive" ? (
        positive.length === 0 ? (
          <div style={{ color: "var(--muted)", fontSize: "0.85rem", padding: "0.4rem 0" }}>
            No supporting full-text evidence extracted.
          </div>
        ) : (
          <ul className="evidence-list">
            {positive.map((e) => (
              <li key={e.id} className={`evidence-item evidence-${e.evidence_type}`}>
                <div className="evidence-header">
                  <span className="evidence-type">{e.evidence_type.replace(/_/g, " ")}</span>
                  <span className="evidence-source">{e.evidence_source}</span>
                  {e.chunk_id && (
                    <span className="evidence-chunk-id">{e.chunk_id}</span>
                  )}
                </div>
                <div className="evidence-text">{e.evidence_text}</div>
              </li>
            ))}
          </ul>
        )
      ) : negative.length === 0 ? (
        <div style={{ color: "var(--muted)", fontSize: "0.85rem", padding: "0.4rem 0" }}>
          No disqualifying evidence recorded — nothing in the paper argues against the label.
        </div>
      ) : (
        <ul className="evidence-list">
          {negative.map((e) => (
            <li
              key={e.id}
              className="evidence-item"
              style={{ borderLeftColor: "var(--uncertain)" }}
            >
              <div className="evidence-header">
                <span className="evidence-type" style={{ color: "var(--uncertain)" }}>
                  ⚠ {e.evidence_type.replace(/_/g, " ")}
                </span>
                <span className="evidence-source">{e.evidence_source}</span>
                {e.chunk_id && <span className="evidence-chunk-id">{e.chunk_id}</span>}
              </div>
              <div className="evidence-text">{e.evidence_text}</div>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

interface Props {
  paper: Paper;
  onReviewed?: () => void;
  readOnly?: boolean;
}

const HUMAN_LABELS = ["INCLUDE", "EXCLUDE", "UNCERTAIN"];

type PanelTab = "evidence" | "wiki";

export function EvidencePanel({ paper, onReviewed, readOnly = false }: Props) {
  const c = paper.classification;
  const [tab, setTab] = useState<PanelTab>("evidence");
  const [reviewer, setReviewer] = useState(paper.review?.reviewer ?? "");
  const [notes, setNotes] = useState(paper.review?.notes ?? "");
  const [status, setStatus] = useState<string>("");
  const [graph, setGraph] = useState<GraphExplanation | null>(null);

  useEffect(() => {
    let cancelled = false;
    setGraph(null);
    if (readOnly) return;
    getGraphExplanation(paper.id)
      .then((g) => !cancelled && setGraph(g))
      .catch(() => {
        if (!cancelled) setGraph(null);
      });
    return () => {
      cancelled = true;
    };
  }, [paper.id, readOnly]);

  const handle = async (label: string) => {
    setStatus("Saving…");
    try {
      await submitReview(paper.id, {
        human_label: label,
        reviewer: reviewer || undefined,
        notes: notes || undefined,
      });
      setStatus(`Saved (${label}).`);
      onReviewed?.();
    } catch (err) {
      setStatus(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <section className="evidence-panel" style={{ paddingTop: "0.75rem" }}>
      {/* Tab bar */}
      <div className="v7-subtabs" style={{ marginBottom: "1rem" }}>
        <button
          className={tab === "evidence" ? "active" : ""}
          onClick={() => setTab("evidence")}
          type="button"
        >
          Evidence
        </button>
        <button
          className={tab === "wiki" ? "active" : ""}
          onClick={() => setTab("wiki")}
          type="button"
        >
          ◈ Wiki
        </button>
      </div>

      {/* Wiki tab */}
      {tab === "wiki" && <WikiPanel paperId={paper.id} readOnly={readOnly} />}

      {/* Evidence tab */}
      {tab === "evidence" && (<>

      {c && (
        <>
          <div style={{ marginTop: "0.8rem" }}>
            <ClassificationBadge label={c.label} /> &nbsp;
            <ConfidenceBar value={c.confidence} />
          </div>

          {!readOnly && <RagStatusPanel status={paper.rag_status} />}

          <div className="score-grid">
            {[
              { label: "Author", value: c.author_score },
              { label: "Institution", value: c.institution_score },
              { label: "Topic", value: c.topic_score },
              { label: "Full-text", value: c.fulltext_evidence_score },
              { label: "Network", value: c.network_score },
              { label: "Citation", value: c.citation_score },
            ].map((s) => (
              <div key={s.label} className="cell">
                <div className="label">{s.label}</div>
                <div className="value">{s.value.toFixed(2)}</div>
              </div>
            ))}
          </div>
          <div style={{ color: "var(--muted)", fontSize: "0.85rem", marginBottom: "0.6rem" }}>
            Model {c.model_version}
          </div>

          <h3>Why?</h3>
          <ul className="reasons">
            {(c.reasons ?? []).map((r, i) => (
              <li key={i}>{r}</li>
            ))}
            {(!c.reasons || c.reasons.length === 0) && (
              <li style={{ color: "var(--muted)" }}>No reasons recorded.</li>
            )}
          </ul>

          {c.matched_people.length > 0 && (
            <>
              <h3>Matched AC people</h3>
              <div className="matched-list">
                {c.matched_people.map((m) => {
                  const badge =
                    m.match_type === "ac_publication_confirmed" ? "AC Publications"
                    : m.match_type === "exact_author_match" ? "exact"
                    : m.match_type === "alias_match" ? "alias"
                    : m.match_type === "initials_match" ? "initials"
                    : m.match_type === "fuzzy_match" ? "fuzzy"
                    : m.match_type?.replace(/_/g, " ") ?? "";
                  return (
                    <span key={m.person_id ?? m.name} className="chip ac" title={m.match_type}>
                      {m.name}
                      {badge && (
                        <span style={{
                          marginLeft: 6, fontSize: "0.7rem", opacity: 0.75,
                          fontFamily: "'JetBrains Mono', monospace",
                        }}>
                          [{badge}]
                        </span>
                      )}
                    </span>
                  );
                })}
              </div>
            </>
          )}

          {c.matched_institutions.length > 0 && (
            <>
              <h3>Institutions</h3>
              <div className="matched-list">
                {c.matched_institutions.map((m) => (
                  <span
                    key={m.institution_id ?? m.canonical_name}
                    className={`chip ${m.is_partner ? "partner" : ""}`}
                    title={m.is_partner ? "AC Partner institution" : "External institution"}
                  >
                    {m.canonical_name}
                    {m.is_partner && (
                      <span style={{ marginLeft: 6, fontSize: "0.7rem", opacity: 0.75 }}>
                        [AC Partner]
                      </span>
                    )}
                  </span>
                ))}
              </div>
            </>
          )}

          {c.matched_topics.length > 0 && (
            <>
              <h3>Topics</h3>
              <div className="matched-list">
                {c.matched_topics.map((m) => (
                  <span
                    key={m.topic_id}
                    className={`chip ${m.is_core ? "core" : ""}`}
                    title={`Score: ${m.score.toFixed(2)} · ${m.is_core ? "Core SDL topic" : "Adjacent topic"}`}
                  >
                    {m.name}
                    <span style={{ marginLeft: 6, fontSize: "0.7rem", opacity: 0.75 }}>
                      {m.is_core ? "[core]" : "[adjacent]"}
                    </span>
                  </span>
                ))}
              </div>
            </>
          )}

          {graph && (graph.second_degree_paths.length > 0 || graph.citation_signals.length > 0 || graph.direct_ac_authors.length > 0) && (
            <>
              <h3>Graph signals</h3>
              <p style={{ color: "var(--muted)", marginTop: 0 }}>{graph.summary}</p>
              {graph.second_degree_paths.length > 0 && (
                <ul className="graph-paths">
                  {graph.second_degree_paths.map((p, i) => (
                    <li key={i}>
                      <strong>{p.via_author_name}</strong> ↔{" "}
                      <span style={{ color: "var(--accent)" }}>{p.ac_author_name}</span>
                      <span style={{ color: "var(--muted)" }}>
                        {" "}— {p.shared_papers.length} shared paper{p.shared_papers.length !== 1 ? "s" : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              {graph.citation_signals.length > 0 && (
                <ul className="graph-paths">
                  {graph.citation_signals.map((s) => (
                    <li key={s.cited_ac_core_id}>
                      Cites AC core:{" "}
                      <em>{s.cited_ac_core_title}</em>
                      {s.cited_doi && (
                        <span style={{ color: "var(--muted)" }}> · {s.cited_doi}</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}

          <FulltextEvidenceTabs evidence={c.fulltext_evidence} />
        </>
      )}

      {paper.abstract && (
        <>
          <h3>Abstract</h3>
          <p style={{ color: "var(--muted)" }}>{paper.abstract}</p>
        </>
      )}

      {!readOnly && <><h3>Human decision</h3>
      <div className="review-form">
        {HUMAN_LABELS.map((l) => (
          <button key={l} onClick={() => handle(l)}>
            {l}
          </button>
        ))}
        <input
          type="text"
          placeholder="reviewer"
          value={reviewer}
          onChange={(e) => setReviewer(e.target.value)}
        />
        <input
          type="text"
          placeholder="notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          style={{ flex: 1 }}
        />
        <span className="status">{status}</span>
      </div>
      {paper.review && (
        <div style={{ marginTop: "0.6rem", color: "var(--muted)" }}>
          Last review: <strong>{paper.review.human_label}</strong> by{" "}
          {paper.review.reviewer ?? "anonymous"}
          {paper.review.notes ? ` — ${paper.review.notes}` : ""}
        </div>
      )}</>}
      </>)}
    </section>
  );
}
