import {
  FormEvent,
  KeyboardEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Link, useLocation } from "react-router-dom";

import {
  archiveWikiSynthesis,
  chatScopeFromPage,
  createChatSession,
  getChatSession,
  getStage1Readiness,
  streamChatMessage,
  submitRagFeedback,
} from "@/lib/api";
import {
  chatPageContext,
  numericSearchParam,
  scopedEvidencePaperId,
} from "@/lib/chatContext";
import type {
  ChatAnswerKind,
  ChatMessage,
  ChatScope,
  ChatStreamEvent,
} from "@/types";

const SESSION_STORAGE_KEY = "pas.global-tier1-chat-session.v4";
const MAX_MESSAGES = 24;
const MAX_QUERY_LENGTH = 2000;

type FeedbackState = "idle" | "saving" | "saved" | "error";
type ArchiveState = "idle" | "saving" | "saved" | "error";
type UiMessage = ChatMessage & {
  feedback?: FeedbackState;
  archive?: ArchiveState;
  synthesisId?: string;
};

const STARTERS = [
  "How many papers are in the current filtered scope?",
  "Which Tier 1 papers use Bayesian optimization?",
  "Compare the automation approaches used across these papers.",
  "Top 10 institutions by distinct papers.",
];

const ANSWER_LABELS: Record<ChatAnswerKind, string> = {
  verified_structured: "Verified structured result",
  evidence_grounded: "Citation-linked synthesis",
  partial_evidence: "Partial evidence",
  insufficient_evidence: "Insufficient evidence",
};

function newId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

function optimisticUserMessage(content: string): UiMessage {
  return {
    id: newId(),
    ordinal: 0,
    role: "user",
    content,
    status: "complete",
    answer_kind: null,
    model: null,
    tool_name: null,
    sources: [],
    audit: {},
    scope: {},
    created_at: new Date().toISOString(),
  };
}

function storedSessionId(): string | null {
  try {
    return sessionStorage.getItem(SESSION_STORAGE_KEY);
  } catch {
    return null;
  }
}

function setStoredSessionId(sessionId: string | null) {
  try {
    if (sessionId) sessionStorage.setItem(SESSION_STORAGE_KEY, sessionId);
    else sessionStorage.removeItem(SESSION_STORAGE_KEY);
  } catch {
    // Server persistence remains available when browser storage is unavailable.
  }
}

function numberFrom(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringFrom(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

export function GlobalChat() {
  const [reader, setReader] = useState<string | null>(null);
  useEffect(() => {
    let current = 0;
    const refresh = () => {
      const version = ++current;
      setReader(null);
      sessionStorage.removeItem(SESSION_STORAGE_KEY);
      fetch('/api/auth/me', { credentials: 'same-origin', cache: 'no-store' })
        .then(async response => response.ok ? response.json() : null)
        .then(user => { if (version === current) setReader(user?.id || null); })
        .catch(() => { if (version === current) setReader(null); });
    };
    const changed = (event: StorageEvent) => { if (event.key === 'pas.identity.changed') refresh(); };
    refresh(); window.addEventListener('storage', changed);
    return () => { current++; window.removeEventListener('storage', changed); };
  }, []);
  if (!reader) return <a className="global-chat-launcher" href="/reading/">Open my reading room</a>;
  return <AuthenticatedGlobalChat key={reader}/>;
}

function AuthenticatedGlobalChat() {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [status, setStatus] = useState("Checking the current corpus scope…");
  const [error, setError] = useState<string | null>(null);
  const [failedQuery, setFailedQuery] = useState<string | null>(null);
  const [derivedViewsEnabled, setDerivedViewsEnabled] = useState(false);
  const sessionIdRef = useRef<string | null>(storedSessionId());
  const restoredSessionRef = useRef<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const launcherRef = useRef<HTMLButtonElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const requestGeneration = useRef(0);
  const inFlightRef = useRef(false);
  const wasOpenRef = useRef(false);

  const params = useMemo(
    () => new URLSearchParams(location.search),
    [location.search],
  );
  const yearFrom = numericSearchParam(params, "year_from");
  const yearTo = numericSearchParam(params, "year_to");
  const scopedPaperId = scopedEvidencePaperId(location.pathname);
  const currentPageContext = chatPageContext(location.pathname, location.search);
  const currentScope = useMemo(
    () => chatScopeFromPage(params, scopedPaperId, currentPageContext),
    [params, scopedPaperId, currentPageContext],
  );

  useEffect(() => {
    if (open) inputRef.current?.focus();
    else if (wasOpenRef.current) launcherRef.current?.focus();
    wasOpenRef.current = open;
  }, [open]);

  useEffect(() => {
    if (!open) return;
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, loading, loadingHistory, open]);

  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    let active = true;
    void getStage1Readiness()
      .then((readiness) => {
        if (active) {
          setDerivedViewsEnabled(
            !readiness.stage1_only || readiness.derived_views_enabled,
          );
        }
      })
      .catch(() => {
        if (active) setDerivedViewsEnabled(false);
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const sessionId = sessionIdRef.current;
    if (
      !open
      || loadingHistory
      || messages.length > 0
      || !sessionId
      || restoredSessionRef.current === sessionId
    ) return;
    let active = true;
    restoredSessionRef.current = sessionId;
    setLoadingHistory(true);
    void getChatSession(sessionId)
      .then((chat) => {
        if (active) setMessages(chat.messages.slice(-MAX_MESSAGES));
      })
      .catch(() => {
        sessionIdRef.current = null;
        setStoredSessionId(null);
      })
      .finally(() => {
        if (active) setLoadingHistory(false);
      });
    return () => { active = false; };
  }, [open, loadingHistory, messages.length]);

  async function ensureSession(scope: ChatScope): Promise<string> {
    if (sessionIdRef.current) return sessionIdRef.current;
    const created = await createChatSession(scope, "Tier 1 research");
    sessionIdRef.current = created.id;
    restoredSessionRef.current = created.id;
    setStoredSessionId(created.id);
    return created.id;
  }

  function applyStreamEvent(event: ChatStreamEvent) {
    if (event.type === "status") {
      setStatus(event.status === "reasoning"
        ? "Choosing a read-only evidence tool…"
        : event.status);
    }
    if (event.type === "tool") {
      setStatus(event.tool_name === "search_fulltext_evidence"
        ? "Searching indexed full text and checking citations…"
        : "Running a verified structured query…");
    }
  }

  async function send(rawQuery: string, appendUser = true) {
    const normalized = rawQuery.trim().slice(0, MAX_QUERY_LENGTH);
    if (!normalized || inFlightRef.current) return;

    const generation = ++requestGeneration.current;
    inFlightRef.current = true;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    let timedOut = false;
    const timeoutId = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, 90_000);

    if (appendUser) {
      setMessages((current) => [
        ...current,
        optimisticUserMessage(normalized),
      ].slice(-MAX_MESSAGES));
    }
    setQuery("");
    setLoading(true);
    setStatus("Checking the current corpus scope…");
    setError(null);
    setFailedQuery(null);

    try {
      const sessionId = await ensureSession(currentScope);
      const assistant = await streamChatMessage(
        sessionId,
        { query: normalized, scope: currentScope },
        applyStreamEvent,
        controller.signal,
      );
      if (generation !== requestGeneration.current) return;
      const assistantMessage: UiMessage = {
        ...assistant,
        feedback: "idle",
        archive: "idle",
      };
      setMessages((current) => [
        ...current,
        assistantMessage,
      ].slice(-MAX_MESSAGES));
    } catch (caught) {
      if (generation !== requestGeneration.current) return;
      if (controller.signal.aborted && !timedOut) return;
      const failureMessage = caught instanceof Error ? caught.message : "";
      setError(
        timedOut
          ? "The evidence search exceeded 90 seconds. Narrow the question or try again."
          : /blocked|raw sql|write-oriented/i.test(failureMessage)
            ? "For safety, raw SQL and write operations are blocked. Ask for the information in plain language."
            : failureMessage.includes("422")
              ? "This request could not be interpreted safely. Try more specific wording."
              : "The research assistant could not complete this request. Check the connection and try again.",
      );
      setFailedQuery(normalized);
    } finally {
      window.clearTimeout(timeoutId);
      if (generation === requestGeneration.current) {
        inFlightRef.current = false;
        setLoading(false);
      }
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    void send(query);
  }

  function handleInputKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (query.trim() && !loading) void send(query);
    }
    if (event.key === "Escape") setOpen(false);
  }

  function newConversation() {
    ++requestGeneration.current;
    abortRef.current?.abort();
    inFlightRef.current = false;
    sessionIdRef.current = null;
    restoredSessionRef.current = null;
    setStoredSessionId(null);
    setMessages([]);
    setLoading(false);
    setError(null);
    setFailedQuery(null);
    setQuery("");
    inputRef.current?.focus();
  }

  function cancelRequest() {
    ++requestGeneration.current;
    abortRef.current?.abort();
    inFlightRef.current = false;
    setLoading(false);
    setError("The request was cancelled. You can retry when ready.");
  }

  async function saveFeedback(message: UiMessage, rating: number) {
    if (message.role !== "assistant" || message.feedback === "saving" || message.feedback === "saved") return;
    setMessages((current) => current.map((item) =>
      item.id === message.id ? { ...item, feedback: "saving" } : item
    ));
    const precedingQuestion = [...messages]
      .reverse()
      .find((item) => item.role === "user" && item.ordinal < message.ordinal)?.content
      ?? message.content;
    try {
      await submitRagFeedback({
        query: precedingQuestion,
        rating,
        failure_type: rating <= 2 ? "tier1_chat_answer_needs_work" : null,
        answer_model: message.model ?? "unknown",
        source_chunk_ids: message.sources.map((source) => source.chunk_id),
        source_paper_ids: Array.from(new Set(message.sources.map((source) => source.paper_id))),
      });
      setMessages((current) => current.map((item) =>
        item.id === message.id ? { ...item, feedback: "saved" } : item
      ));
    } catch {
      setMessages((current) => current.map((item) =>
        item.id === message.id ? { ...item, feedback: "error" } : item
      ));
    }
  }

  async function archiveAnswer(message: UiMessage) {
    if (
      message.role !== "assistant"
      || message.answer_kind === "insufficient_evidence"
      || message.archive === "saving"
      || message.archive === "saved"
    ) return;
    setMessages((current) => current.map((item) =>
      item.id === message.id ? { ...item, archive: "saving" } : item
    ));
    const title = [...messages]
      .reverse()
      .find((item) => item.role === "user" && item.ordinal < message.ordinal)
      ?.content.slice(0, 240);
    try {
      const synthesis = await archiveWikiSynthesis(message.id, title);
      setMessages((current) => current.map((item) =>
        item.id === message.id
          ? { ...item, archive: "saved", synthesisId: synthesis.id }
          : item
      ));
    } catch {
      setMessages((current) => current.map((item) =>
        item.id === message.id ? { ...item, archive: "error" } : item
      ));
    }
  }

  if (!derivedViewsEnabled) return null;

  return (
    <div className={`global-chat ${open ? "is-open" : ""}`}>
      {open && (
        <section
          id="global-corpus-chat"
          className="global-chat-panel"
          role="dialog"
          aria-modal="false"
          aria-label="Ask the Tier 1 paper corpus"
          onKeyDown={(event) => {
            if (event.key === "Escape") setOpen(false);
          }}
        >
          <header className="global-chat-header">
            <div>
              <span className="review-kicker">Tier 1 research workspace</span>
              <h2>Corpus assistant</h2>
            </div>
            <div className="global-chat-header-actions">
              <button type="button" onClick={newConversation}>New chat</button>
              <button
                type="button"
                className="global-chat-icon-button"
                aria-label="Close corpus chat"
                onClick={() => setOpen(false)}
              >
                <svg aria-hidden="true" viewBox="0 0 24 24" width="18" height="18">
                  <path d="M6 6l12 12M18 6L6 18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
              </button>
            </div>
          </header>

          <div className="global-chat-scope">
            <span>Tier 1 only</span>
            <span>Read-only tools</span>
            <span>Sources required</span>
            {(yearFrom != null || yearTo != null) && (
              <span>{yearFrom ?? "…"}–{yearTo ?? "…"}</span>
            )}
            {scopedPaperId && <span>Paper {scopedPaperId}</span>}
            <Link to="/retrieval" onClick={() => setOpen(false)}>Evidence workspace</Link>
          </div>

          <div className="global-chat-messages" ref={scrollRef} aria-live="polite">
            {messages.length === 0 && !loading && !loadingHistory && (
              <div className="global-chat-empty">
                <strong>Ask the current paper scope.</strong>
                <p>Counts and lists come from verified read-only queries. Findings and comparisons must cite indexed passages. If the corpus cannot support a claim, the answer says so.</p>
                <div>
                  {STARTERS.map((starter) => (
                    <button key={starter} type="button" onClick={() => void send(starter)}>
                      {starter}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((message) => {
              const answerKind = message.answer_kind;
              const paperCount = numberFrom(message.scope.paper_count);
              const rows = Array.isArray(message.audit.rows) ? message.audit.rows : [];
              const missingEvidence = Array.isArray(message.audit.missing_evidence)
                ? message.audit.missing_evidence.filter((item): item is string => typeof item === "string")
                : [];
              return (
                <article key={message.id} className={`global-chat-message ${message.role}`}>
                  <div className="global-chat-role">{message.role === "user" ? "You" : "Corpus assistant"}</div>
                  <div className="global-chat-content">{message.content}</div>

                  {message.role === "assistant" && answerKind && (
                    <>
                      <div className={`global-chat-trust ${answerKind}`}>
                        <strong>{ANSWER_LABELS[answerKind]}</strong>
                        <span>
                          {answerKind === "verified_structured"
                            ? "Computed from an approved query template; no language model used."
                            : answerKind === "evidence_grounded"
                              ? "Citations resolve to the passages below; semantic faithfulness has not been independently judged."
                              : answerKind === "partial_evidence"
                                ? "Relevant passages were found, but the synthesis or citations are not fully verified."
                                : "The indexed corpus does not support a reliable answer."}
                        </span>
                      </div>
                      <div className="global-chat-answer-meta">
                        {message.tool_name && <span>{message.tool_name.replaceAll("_", " ")}</span>}
                        {paperCount != null && <span>{paperCount} papers in scope</span>}
                        {message.sources.length > 0 && <span>{message.sources.length} passages</span>}
                        {message.model && <span>{message.model}</span>}
                      </div>
                    </>
                  )}

                  {missingEvidence.length > 0 && (
                    <div className="global-chat-warning">
                      <strong>Evidence limits</strong>
                      <span>{missingEvidence.join(" ")}</span>
                    </div>
                  )}

                  {message.sources.length > 0 && (
                    <details className="global-chat-sources" open>
                      <summary>Evidence from {message.sources.length} indexed passages</summary>
                      {message.sources.slice(0, 8).map((source, index) => (
                        <article className="global-chat-source" key={source.chunk_id}>
                          <div>
                            <Link
                              to={`/papers/${encodeURIComponent(source.paper_id)}/evidence-map`}
                              onClick={() => setOpen(false)}
                            >
                              [{index + 1}] {source.paper_title || `Paper ${source.paper_id}`}
                            </Link>
                            <span>
                              {source.section_title || source.section_type}
                              {source.score != null ? ` · ${source.score.toFixed(3)}` : ""}
                            </span>
                          </div>
                          <p>{source.text.slice(0, 460)}{source.text.length > 460 ? "…" : ""}</p>
                        </article>
                      ))}
                    </details>
                  )}

                  {message.role === "assistant" && answerKind === "insufficient_evidence" && message.sources.length === 0 && (
                    <div className="global-chat-no-evidence">
                      No indexed passage was strong enough to support an answer. Broaden the wording or confirm that the relevant PDFs are indexed.
                    </div>
                  )}

                  {message.role === "assistant" && answerKind === "verified_structured" && (
                    <details className="global-chat-sources">
                      <summary>Inspect query, rows, and audit trail</summary>
                      <div className="global-chat-sql-audit">
                        <strong>Approved SELECT template</strong>
                        <pre>{stringFrom(message.audit.sql) ?? "Query text unavailable"}</pre>
                        <strong>Bound parameters</strong>
                        <pre>{JSON.stringify(message.audit.parameters ?? {}, null, 2)}</pre>
                        <strong>Returned rows</strong>
                        <pre>{JSON.stringify(rows, null, 2)}</pre>
                        <div className="global-chat-sql-fingerprints">
                          <span>Read-only: {message.audit.read_only === true ? "yes" : "unknown"}</span>
                          <span>LLM used: {message.audit.llm_used === true ? "yes" : "no"}</span>
                          {stringFrom(message.audit.scope_paper_set_sha256) && (
                            <span>Paper set: {stringFrom(message.audit.scope_paper_set_sha256)?.slice(0, 12)}</span>
                          )}
                          {stringFrom(message.audit.statement_sha256) && (
                            <span>Statement: {stringFrom(message.audit.statement_sha256)?.slice(0, 12)}</span>
                          )}
                        </div>
                      </div>
                    </details>
                  )}

                  {message.role === "assistant" && answerKind && (
                    <div className="global-chat-feedback" aria-live="polite">
                      {message.feedback === "saved" ? (
                        <span>Feedback saved.</span>
                      ) : (
                        <>
                          <span>Was this answer useful?</span>
                          <button type="button" disabled={message.feedback === "saving"} onClick={() => void saveFeedback(message, 5)}>Useful</button>
                          <button type="button" disabled={message.feedback === "saving"} onClick={() => void saveFeedback(message, 1)}>Needs work</button>
                          {message.feedback === "error" && <span role="alert">Feedback failed. Try again.</span>}
                        </>
                      )}
                      {answerKind !== "insufficient_evidence" && (
                        <>
                          <button
                            type="button"
                            disabled={message.archive === "saving" || message.archive === "saved"}
                            onClick={() => void archiveAnswer(message)}
                          >
                            {message.archive === "saving"
                              ? "Archiving…"
                              : message.archive === "saved"
                                ? "Draft archived; review required"
                                : "Archive as draft"}
                          </button>
                          {message.archive === "error" && (
                            <span role="alert">Draft archival failed. Try again.</span>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </article>
              );
            })}

            {(loading || loadingHistory) && (
              <div className="global-chat-loading" role="status">
                <span aria-hidden="true" />
                <span>{loadingHistory ? "Restoring this conversation…" : status}</span>
                {loading && <button type="button" onClick={cancelRequest}>Cancel</button>}
              </div>
            )}
            {error && (
              <div className="global-chat-error" role="alert">
                <span>{error}</span>
                {failedQuery && <button type="button" onClick={() => void send(failedQuery)}>Try again</button>}
              </div>
            )}
          </div>

          <form className="global-chat-composer" onSubmit={handleSubmit}>
            <label htmlFor="global-chat-query">Question</label>
            <div>
              <textarea
                ref={inputRef}
                id="global-chat-query"
                value={query}
                maxLength={MAX_QUERY_LENGTH}
                rows={2}
                placeholder="Ask about papers, methods, findings, people, institutions, or comparisons…"
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={handleInputKeyDown}
                disabled={loading}
              />
              <button type="submit" disabled={loading || !query.trim()}>
                {loading ? "Working" : "Send"}
              </button>
            </div>
            <small>Enter to send · Shift+Enter for a new line · current page filters define the evidence scope.</small>
          </form>
        </section>
      )}

      {!open && (
        <button
          ref={launcherRef}
          type="button"
          className="global-chat-launcher"
          aria-expanded="false"
          aria-controls="global-corpus-chat"
          onClick={() => setOpen(true)}
        >
          <svg aria-hidden="true" viewBox="0 0 24 24" width="20" height="20">
            <path d="M5 5.5h14v10H9l-4 3v-13Z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
            <path d="M8 9h8M8 12h5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
          <span>Ask Tier 1</span>
        </button>
      )}
    </div>
  );
}
