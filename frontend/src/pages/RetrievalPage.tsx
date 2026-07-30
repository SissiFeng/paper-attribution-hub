import { useState } from "react";
import { retrieveAnswer, searchPropositions, submitRagFeedback } from "@/lib/api";
import type { AnswerOut, PropositionHit, RagModuleStep } from "@/types";
import styles from "./RetrievalPage.module.css";

// ── Graph path visualizer ──────────────────────────────────────────────────
// Parses graph_context strings like:
//   "network: Via Author → AC Author (3 shared papers) | cites AC core: Title"
// and renders them as a node-dot + dashed-arrow diagram.

type PathSegment = { kind: "network" | "cite"; nodes: string[]; detail?: string };

function parseGraphContext(ctx: string): PathSegment[] {
  return ctx.split(" | ").map((seg) => {
    if (seg.startsWith("network: ")) {
      const body = seg.slice(9);
      const m = body.match(/^(.+?) → (.+?) \((\d+) shared/);
      if (m) return { kind: "network" as const, nodes: [m[1].trim(), m[2].trim()], detail: `${m[3]} shared` };
      return { kind: "network" as const, nodes: body.split(" → ").map((s) => s.trim()) };
    }
    if (seg.startsWith("cites AC core: ")) {
      const title = seg.slice(15);
      return { kind: "cite" as const, nodes: ["paper", title.length > 44 ? title.slice(0, 42) + "…" : title] };
    }
    return { kind: "network" as const, nodes: [seg.slice(0, 50)] };
  });
}

function GraphPath({ context }: { context: string }) {
  const segments = parseGraphContext(context);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {segments.map((seg, si) => {
        const color = seg.kind === "cite" ? "var(--amber)" : "var(--blue)";
        return (
          <div key={si} style={{ display: "flex", alignItems: "flex-start" }}>
            {seg.nodes.map((node, ni) => (
              <div key={ni} style={{ display: "flex", alignItems: "flex-start" }}>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 3 }}>
                  <div style={{ width: 7, height: 7, borderRadius: "50%", background: color, marginTop: 1 }} />
                  <span style={{
                    fontSize: 9.5, color: "var(--muted)", textAlign: "center",
                    letterSpacing: "0.03em", lineHeight: 1.25, maxWidth: 74,
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                    fontFamily: "var(--mono)",
                  }}>
                    {node}
                  </span>
                </div>
                {ni < seg.nodes.length - 1 && (
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "1px 3px 0" }}>
                    <svg width="48" height="8" style={{ overflow: "visible" }}>
                      <line x1="0" y1="3.5" x2="40" y2="3.5" stroke={color} strokeWidth="1.3" strokeDasharray="3 2.5" />
                      <polygon points="37,1 41,3.5 37,6" fill={color} />
                    </svg>
                    {seg.detail && (
                      <span style={{ fontSize: 8.5, color: "var(--muted)", whiteSpace: "nowrap", marginTop: 1, fontFamily: "var(--mono)" }}>
                        {seg.detail}
                      </span>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

// ── Reasoning-trace rendering ───────────────────────────────────────────────
// The backend already returns module_trace; the agent UI surfaces it as the
// pipeline "thinking" instead of hiding it.

const STEP_LABEL: Record<string, string> = {
  routing: "route",
  memory: "recall",
  search: "retrieve",
  agentic_search: "traverse",
  fusion: "fuse",
  predict: "assess",
  demonstrate: "answer",
};

const numOf = (v: unknown) => (typeof v === "number" ? v : undefined);
const strOf = (v: unknown) => (v == null ? undefined : String(v));

function describeStep(step: RagModuleStep): { label: string; detail: string; think: boolean; skip: boolean } {
  const label = STEP_LABEL[step.module] ?? step.module;
  const skipped = strOf(step.skipped);
  if (skipped) return { label, detail: skipped.replace(/_/g, " "), think: false, skip: true };

  let detail = "";
  switch (step.module) {
    case "routing":
      detail = [strOf(step.query_type), strOf(step.mode)].filter(Boolean).join(" · ");
      break;
    case "memory":
      detail = `${numOf(step.low_rating_count) ?? 0} signals`;
      break;
    case "search":
      detail = `${numOf(step.candidates) ?? 0} chunks`;
      break;
    case "agentic_search":
      detail = `${numOf(step.links) ?? numOf(step.agentic_links) ?? 0} links`;
      break;
    case "fusion":
      detail = `${numOf(step.sources) ?? 0} sources`;
      break;
    case "predict": {
      const es = numOf(step.evidence_score);
      detail = es != null ? `evidence ${es.toFixed(2)}` : "scored";
      break;
    }
    case "demonstrate":
      detail = strOf(step.model) ?? "grounded";
      break;
    default: {
      const first = Object.entries(step).find(
        ([k, v]) => k !== "module" && (typeof v === "number" || typeof v === "string"),
      );
      detail = first ? `${first[0]} ${first[1]}` : "";
    }
  }
  return { label, detail, think: step.module === "agentic_search", skip: false };
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export const PREDICATE_OPTIONS = ["uses_method", "funded_by", "cites", "belongs_to_topic"];

const EXAMPLES = [
  "Which papers use Bayesian optimization for materials discovery?",
  "What automation platforms are used in self-driving labs?",
  "Papers funded by NSERC on closed-loop synthesis",
  "Compare active learning approaches across SDL papers",
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
  const [runKey, setRunKey] = useState(0);

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
      setActiveTab("answer");
      setRunKey((k) => k + 1);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

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

  const scoreBar = (v: number | null, cls: string) =>
    v != null ? (
      <div className={styles.scoreRow}>
        <span className={`${styles.scoreTrack}`}>
          <span className={`${styles.scoreFill} ${styles[cls]}`} style={{ width: `${Math.min(100, v * 100)}%` }} />
        </span>
        <span className={styles.scoreVal}>{v.toFixed(3)}</span>
      </div>
    ) : (
      <span className={styles.scoreVal} style={{ color: "var(--faint)" }}>—</span>
    );

  const trace: RagModuleStep[] = result?.module_trace ?? [];

  return (
    <div className={styles.page}>
      <div className={styles.inner}>
        <h1 className={styles.h1}>Graph-Enhanced Retrieval</h1>
        <p className={styles.sub}>
          BM25 + cosine + RRF · graph centrality re-ranking (PPR, Evans-Chen) · proposition-first channel · graph-path context
        </p>

        <form className={styles.ask} onSubmit={handleSearch}>
          <div className={styles.field}>
            <span className={styles.glyph}>&gt;_</span>
            <input
              className={styles.input}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask the corpus — e.g. which labs use Bayesian optimization after 2022?"
              aria-label="Research question"
            />
          </div>
          <select className={styles.topk} value={topK} onChange={(e) => setTopK(Number(e.target.value))} aria-label="Sources to retrieve">
            {[4, 8, 12, 20].map((n) => (
              <option key={n} value={n}>top {n}</option>
            ))}
          </select>
          <button className={styles.go} type="submit" disabled={loading}>
            {loading ? "Thinking…" : "Ask"}
          </button>
        </form>

        {error && <div className={styles.error}>{error}</div>}

        {loading && (
          <>
            <div className={styles.agentLabel}><span className={styles.pulse} /> Reasoning over the corpus…</div>
          </>
        )}

        {!result && !loading && !error && (
          <div className={styles.empty}>
            <svg width="46" height="46" viewBox="0 0 48 48" fill="none" strokeWidth="1.6">
              <circle cx="20" cy="20" r="12" />
              <line x1="30" y1="30" x2="42" y2="42" />
              <line x1="14" y1="20" x2="26" y2="20" strokeWidth="1.3" />
              <line x1="20" y1="14" x2="20" y2="26" strokeWidth="1.3" />
            </svg>
            <div className={styles.emptyLabel}>Ask a question about the SDL paper corpus</div>
            <div className={styles.examples}>
              {EXAMPLES.map((q) => (
                <button key={q} type="button" className={styles.example} onClick={() => setQuery(q)}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {result && !loading && (
          <>
            {trace.length > 0 && (
              <>
                <div className={styles.agentLabel}><span className={styles.pulse} /> Reasoning</div>
                <div className={styles.trace} key={runKey}>
                  {trace.map((step, i) => {
                    const d = describeStep(step);
                    return (
                      <span
                        key={i}
                        className={`${styles.step} ${d.think ? styles.stepThink : ""} ${d.skip ? styles.stepSkip : ""}`}
                        style={{ animationDelay: `${i * 0.07}s` }}
                      >
                        <span className={styles.k}>{d.label}</span>
                        {d.detail}
                        <span className={styles.tick}>{d.skip ? "–" : "✓"}</span>
                      </span>
                    );
                  })}
                </div>
              </>
            )}

            <p className={styles.answer}>{result.answer}</p>
            <div className={styles.answerMeta}>
              {(result.execution_mode ?? "adaptive")} mode · {result.model} · {result.chunks_retrieved} chunks searched · {result.sources.length} sources
            </div>

            <div className={styles.stats}>
              <div className={styles.stat}>
                <div className={styles.statN} style={{ fontSize: 17, paddingTop: 4 }}>{result.query_type}</div>
                <div className={styles.statL}>query type</div>
              </div>
              <div className={styles.stat}>
                <div className={styles.statN}>{result.evidence_score.toFixed(2)}</div>
                <div className={styles.statL}>evidence score</div>
              </div>
              <div className={styles.stat}>
                <div className={styles.statN}>{result.source_precision.toFixed(2)}</div>
                <div className={styles.statL}>source precision</div>
              </div>
              <div className={styles.stat}>
                <div className={`${styles.statN} ${result.should_retry ? styles.warn : styles.good}`} style={{ fontSize: 15, paddingTop: 6 }}>
                  {result.should_retry ? "review" : "sufficient"}
                </div>
                <div className={styles.statL}>evidence signal</div>
              </div>
            </div>

            {result.missing_evidence.length > 0 && (
              <div className={styles.note}>
                {result.missing_evidence.map((m) => <span key={m}>⚠ {m}</span>)}
              </div>
            )}

            <div className={styles.tabs}>
              <button className={`${styles.tab} ${activeTab === "answer" ? styles.tabActive : ""}`} onClick={() => setActiveTab("answer")}>
                Evidence &amp; sources
              </button>
              <button className={`${styles.tab} ${activeTab === "propositions" ? styles.tabActive : ""}`} onClick={() => setActiveTab("propositions")}>
                Propositions ({propHits?.length ?? 0})
              </button>
              <span className={styles.tabMeta}>graph-path re-ranked</span>
            </div>

            {activeTab === "answer" && (
              <>
                {result.proposition_hints.length > 0 && (
                  <div className={styles.propChips}>
                    {result.proposition_hints.slice(0, 6).map((h, i) => (
                      <span key={i} className={styles.propChip}>
                        {h.predicate}: {h.object_value.slice(0, 40)}
                      </span>
                    ))}
                  </div>
                )}

                <div className={styles.sources}>
                  {result.sources.map((src, i) => (
                    <div key={src.chunk_id} className={styles.source}>
                      <div className={styles.srcHead}>
                        <span className={styles.srcId}>
                          <span className={styles.srcCite}>{i + 1}</span>
                          {src.paper_id}
                          <span className={styles.srcSection}>
                            {src.section_type}{src.section_title ? ` · ${src.section_title}` : ""}
                          </span>
                        </span>
                        <span className={styles.srcScore}>score {(src.score ?? 0).toFixed(3)}</span>
                      </div>

                      <div className={styles.scores}>
                        <span className={styles.scoreLabel}>BM25</span>{scoreBar(src.bm25_score, "sBm25")}
                        <span className={styles.scoreLabel}>cosine</span>{scoreBar(src.cosine_score, "sCos")}
                        <span className={styles.scoreLabel}>graph</span>{scoreBar(src.graph_score, "sGraph")}
                      </div>

                      {src.graph_context && (
                        <div className={styles.graphPath}>
                          <div className={styles.graphPathLabel}>GRAPH PATH</div>
                          <GraphPath context={src.graph_context} />
                        </div>
                      )}

                      <p className={styles.excerpt}>
                        {src.text.slice(0, 400)}{src.text.length > 400 ? "…" : ""}
                      </p>
                    </div>
                  ))}
                </div>

                <div className={styles.feedback}>
                  <span>Was this answer useful?</span>
                  <button type="button" className={styles.fbGood} disabled={feedbackSent} onClick={() => void handleFeedback(5)}>
                    Useful
                  </button>
                  <select className={styles.fbSelect} value={failureType} onChange={(e) => setFailureType(e.target.value)} disabled={feedbackSent}>
                    <option value="missing_source">Missing source</option>
                    <option value="wrong_source">Wrong source</option>
                    <option value="hallucination">Hallucination risk</option>
                    <option value="too_broad">Too broad</option>
                    <option value="stale">Stale evidence</option>
                  </select>
                  <button type="button" className={styles.fbBad} disabled={feedbackSent} onClick={() => void handleFeedback(1)}>
                    Needs work
                  </button>
                  {feedbackSent && <span>Feedback saved.</span>}
                </div>
              </>
            )}

            {activeTab === "propositions" && propHits && (
              <div className={styles.propList}>
                {propHits.length === 0 ? (
                  <p className={styles.propMeta}>No structured propositions matched this query.</p>
                ) : (
                  propHits.map((h, i) => (
                    <div key={i} className={styles.propCard}>
                      <div className={styles.propTop}>
                        <span className={styles.propPred}>{h.predicate}</span>
                        <span className={styles.propScore}>score {h.score.toFixed(3)} · conf {h.confidence.toFixed(2)}</span>
                      </div>
                      <div className={styles.propObj}>{h.object_value}</div>
                      <div className={styles.propClaim}>{h.claim_text}</div>
                      <div className={styles.propMeta}>
                        paper: {h.paper_id}{h.source_section ? ` · §${h.source_section}` : ""}
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
