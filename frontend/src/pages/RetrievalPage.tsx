import { useState } from "react";
import { retrieveAnswer, searchPropositions, submitRagFeedback } from "@/lib/api";
import type { AnswerOut, PropositionHit } from "@/types";

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export const PREDICATE_OPTIONS = [
  "uses_method",
  "funded_by",
  "cites",
  "belongs_to_topic",
];

export default function RetrievalPage() {
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(8);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnswerOut | null>(null);
  const [propHits, setPropHits] = useState<PropositionHit[] | null>(null);
  const [activeTab, setActiveTab] = useState<"answer" | "propositions">("answer");
  const [error, setError] = useState<string | null>(null);
  const [feedbackSent, setFeedbackSent] = useState(false);
  const [failureType, setFailureType] = useState<string>("missing_source");

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const [ans, props] = await Promise.all([
        retrieveAnswer({ query, top_k: topK }),
        searchPropositions(query, 8),
      ]);
      setResult(ans);
      setPropHits(props);
      setFeedbackSent(false);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  const scoreBar = (v: number | null, color: string) =>
    v != null ? (
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <div
          style={{
            height: 6, borderRadius: 3, background: color,
            width: `${Math.min(100, v * 100)}%`, minWidth: 4, flex: "0 0 auto",
          }}
        />
        <span style={{ fontSize: 11, color: "#aaa" }}>{v.toFixed(3)}</span>
      </div>
    ) : null;

  async function handleFeedback(rating: number) {
    if (!result) return;
    await submitRagFeedback({
      query,
      rating,
      failure_type: rating <= 2 ? failureType : null,
      answer_model: result.model,
      source_chunk_ids: result.sources.map((s) => s.chunk_id),
      source_paper_ids: Array.from(new Set(result.sources.map((s) => s.paper_id))),
    });
    setFeedbackSent(true);
  }

  return (
    <div style={{ padding: "24px 32px", maxWidth: 960, margin: "0 auto" }}>
      <h2 style={{ marginBottom: 4 }}>Graph-Enhanced Retrieval</h2>
      <p style={{ color: "#888", marginBottom: 20, fontSize: 13 }}>
        BM25 + cosine + RRF · graph centrality re-ranking (PPR, Evans-Chen) ·
        proposition-first channel · graph-path context
      </p>

      <form onSubmit={handleSearch} style={{ display: "flex", gap: 10, marginBottom: 24 }}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. Which papers use Bayesian optimization for materials discovery?"
          style={{
            flex: 1, padding: "8px 12px", borderRadius: 6,
            border: "1px solid #333", background: "#1a1a1a", color: "#eee",
            fontSize: 14,
          }}
        />
        <select
          value={topK}
          onChange={(e) => setTopK(Number(e.target.value))}
          style={{
            padding: "8px 10px", borderRadius: 6,
            border: "1px solid #333", background: "#1a1a1a", color: "#aaa",
          }}
        >
          {[4, 8, 12, 20].map((n) => (
            <option key={n} value={n}>top {n}</option>
          ))}
        </select>
        <button
          type="submit"
          disabled={loading}
          style={{
            padding: "8px 20px", borderRadius: 6, background: "#d4a574",
            border: "none", color: "#000", fontWeight: 600, cursor: "pointer",
          }}
        >
          {loading ? "…" : "Search"}
        </button>
      </form>

      {error && (
        <div style={{ color: "#f87171", marginBottom: 16 }}>{error}</div>
      )}

      {!result && !loading && !error && (
        <div
          style={{
            marginTop: 40, textAlign: "center", color: "#444",
            display: "flex", flexDirection: "column", alignItems: "center", gap: 20,
          }}
        >
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none" stroke="#333" strokeWidth="1.5">
            <circle cx="20" cy="20" r="12" />
            <line x1="30" y1="30" x2="42" y2="42" />
            <line x1="14" y1="20" x2="26" y2="20" strokeWidth="1.2" />
            <line x1="20" y1="14" x2="20" y2="26" strokeWidth="1.2" />
          </svg>
          <div style={{ fontSize: 14, color: "#555" }}>
            Ask a question about the SDL paper corpus
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center", maxWidth: 600 }}>
            {[
              "Which papers use Bayesian optimization for materials discovery?",
              "What automation platforms are used in self-driving labs?",
              "Papers funded by NSERC on closed-loop synthesis",
              "Compare active learning approaches across SDL papers",
            ].map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => setQuery(q)}
                style={{
                  padding: "5px 12px", borderRadius: 20, fontSize: 12,
                  border: "1px solid #2a2a2a", background: "#141414",
                  color: "#666", cursor: "pointer",
                }}
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {result && (
        <>
          {/* Tab bar */}
          <div style={{ display: "flex", gap: 0, marginBottom: 16, borderBottom: "1px solid #333" }}>
            {(["answer", "propositions"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                style={{
                  padding: "8px 18px", border: "none", cursor: "pointer",
                  background: "none", fontSize: 13, fontWeight: 600,
                  color: activeTab === tab ? "#d4a574" : "#666",
                  borderBottom: activeTab === tab ? "2px solid #d4a574" : "2px solid transparent",
                }}
              >
                {tab === "answer" ? "Answer & Sources" : `Propositions (${propHits?.length ?? 0})`}
              </button>
            ))}
            <span style={{ marginLeft: "auto", fontSize: 12, color: "#555", padding: "8px 0" }}>
              {result.chunks_retrieved} chunks searched · {result.sources.length} returned · {result.model}
            </span>
          </div>

          <div
            style={{
              display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
              gap: 10, marginBottom: 16,
            }}
          >
            <div style={{ background: "#111", border: "1px solid #2a2a2a", borderRadius: 8, padding: 10 }}>
              <div style={{ fontSize: 11, color: "#666" }}>Query type</div>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{result.query_type}</div>
            </div>
            <div style={{ background: "#111", border: "1px solid #2a2a2a", borderRadius: 8, padding: 10 }}>
              <div style={{ fontSize: 11, color: "#666" }}>Evidence score</div>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{result.evidence_score.toFixed(3)}</div>
            </div>
            <div style={{ background: "#111", border: "1px solid #2a2a2a", borderRadius: 8, padding: 10 }}>
              <div style={{ fontSize: 11, color: "#666" }}>Source precision</div>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{result.source_precision.toFixed(3)}</div>
            </div>
            <div style={{ background: "#111", border: "1px solid #2a2a2a", borderRadius: 8, padding: 10 }}>
              <div style={{ fontSize: 11, color: "#666" }}>Retry signal</div>
              <div style={{ fontSize: 13, fontWeight: 600, color: result.should_retry ? "#fbbf24" : "#7dc97d" }}>
                {result.should_retry ? "Review evidence" : "Enough evidence"}
              </div>
            </div>
          </div>

          {result.missing_evidence.length > 0 && (
            <div
              style={{
                background: "#1a1500", border: "1px solid #4a3900",
                borderRadius: 8, padding: 12, marginBottom: 16,
                color: "#d4a574", fontSize: 13,
              }}
            >
              {result.missing_evidence.map((m) => <div key={m}>{m}</div>)}
            </div>
          )}

          {activeTab === "answer" && (
            <>
              {/* Answer box */}
              <div
                style={{
                  background: "#111", border: "1px solid #2a2a2a",
                  borderRadius: 8, padding: 16, marginBottom: 20,
                  fontSize: 14, lineHeight: 1.7, whiteSpace: "pre-wrap",
                }}
              >
                {result.answer}
              </div>

              {/* Proposition hints (if returned inline) */}
              {result.proposition_hints.length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <div style={{ fontSize: 12, color: "#888", marginBottom: 8 }}>
                    Structured proposition hits (method/funding signals):
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {result.proposition_hints.slice(0, 4).map((h, i) => (
                      <span
                        key={i}
                        style={{
                          background: "#1e2a1e", border: "1px solid #2a4a2a",
                          borderRadius: 4, padding: "3px 8px", fontSize: 12, color: "#7dc97d",
                        }}
                      >
                        {h.predicate}: {h.object_value.slice(0, 40)}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Source cards */}
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {result.sources.map((src, i) => (
                  <div
                    key={src.chunk_id}
                    style={{
                      background: "#111", border: "1px solid #2a2a2a",
                      borderRadius: 8, padding: 14,
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                      <span style={{ fontWeight: 600, fontSize: 13 }}>
                        [{i + 1}] {src.paper_id}
                        <span style={{ color: "#666", marginLeft: 8, fontSize: 12 }}>
                          {src.section_type}
                          {src.section_title ? ` · ${src.section_title}` : ""}
                        </span>
                      </span>
                      <span style={{ fontSize: 12, color: "#888" }}>
                        score {(src.score ?? 0).toFixed(3)}
                      </span>
                    </div>

                    {/* Score breakdown */}
                    <div style={{ display: "grid", gridTemplateColumns: "80px 1fr", gap: "3px 8px", marginBottom: 8 }}>
                      <span style={{ fontSize: 11, color: "#666" }}>BM25</span>
                      {scoreBar(src.bm25_score, "#6594b1")}
                      <span style={{ fontSize: 11, color: "#666" }}>Cosine</span>
                      {scoreBar(src.cosine_score, "#22c55e")}
                      <span style={{ fontSize: 11, color: "#666" }}>Graph</span>
                      {scoreBar(src.graph_score, "#d4a574")}
                    </div>

                    {/* Graph context path */}
                    {src.graph_context && (
                      <div
                        style={{
                          fontSize: 11, color: "#b8860b",
                          background: "#1a1500", borderRadius: 4,
                          padding: "4px 8px", marginBottom: 8,
                        }}
                      >
                        🕸 {src.graph_context}
                      </div>
                    )}

                    <p style={{ fontSize: 13, color: "#ccc", margin: 0, lineHeight: 1.6 }}>
                      {src.text.slice(0, 400)}{src.text.length > 400 ? "…" : ""}
                    </p>
                  </div>
                ))}
              </div>

              <div
                style={{
                  marginTop: 16, padding: 12, border: "1px solid #2a2a2a",
                  borderRadius: 8, background: "#111", display: "flex",
                  alignItems: "center", gap: 10, flexWrap: "wrap",
                }}
              >
                <span style={{ fontSize: 12, color: "#888" }}>Was this answer useful?</span>
                <button
                  type="button"
                  disabled={feedbackSent}
                  onClick={() => void handleFeedback(5)}
                  style={{ padding: "5px 10px", borderRadius: 6, border: "1px solid #2a4a2a", background: "#1e2a1e", color: "#7dc97d" }}
                >
                  Useful
                </button>
                <select
                  value={failureType}
                  onChange={(e) => setFailureType(e.target.value)}
                  disabled={feedbackSent}
                  style={{ padding: "5px 8px", borderRadius: 6, border: "1px solid #333", background: "#1a1a1a", color: "#aaa" }}
                >
                  <option value="missing_source">Missing source</option>
                  <option value="wrong_source">Wrong source</option>
                  <option value="hallucination">Hallucination risk</option>
                  <option value="too_broad">Too broad</option>
                  <option value="stale">Stale evidence</option>
                </select>
                <button
                  type="button"
                  disabled={feedbackSent}
                  onClick={() => void handleFeedback(1)}
                  style={{ padding: "5px 10px", borderRadius: 6, border: "1px solid #4a2a2a", background: "#2a1e1e", color: "#f87171" }}
                >
                  Needs work
                </button>
                {feedbackSent && <span style={{ fontSize: 12, color: "#666" }}>Feedback saved.</span>}
              </div>
            </>
          )}

          {activeTab === "propositions" && propHits && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {propHits.length === 0 ? (
                <p style={{ color: "#666", fontSize: 13 }}>No structured propositions matched this query.</p>
              ) : (
                propHits.map((h, i) => (
                  <div
                    key={i}
                    style={{
                      background: "#111", border: "1px solid #2a3a2a",
                      borderRadius: 8, padding: 14,
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                      <span
                        style={{
                          background: "#1e2a1e", borderRadius: 4,
                          padding: "2px 8px", fontSize: 12, color: "#7dc97d",
                        }}
                      >
                        {h.predicate}
                      </span>
                      <span style={{ fontSize: 12, color: "#666" }}>
                        score {h.score.toFixed(3)} · conf {h.confidence.toFixed(2)}
                      </span>
                    </div>
                    <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
                      {h.object_value}
                    </div>
                    <div style={{ fontSize: 13, color: "#aaa", marginBottom: 6 }}>
                      {h.claim_text}
                    </div>
                    <div style={{ fontSize: 11, color: "#555" }}>
                      paper: {h.paper_id}
                      {h.source_section ? ` · §${h.source_section}` : ""}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
