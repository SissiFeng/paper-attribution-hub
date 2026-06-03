import { useState } from "react";
import { retrieveAnswer, searchPropositions } from "@/lib/api";
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
