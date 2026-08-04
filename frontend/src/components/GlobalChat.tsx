import {
  FormEvent,
  KeyboardEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Link, useLocation } from "react-router-dom";

import { retrieveSqlChat, submitRagFeedback } from "@/lib/api";
import {
  chatPageContext,
  numericSearchParam,
  scopedEvidencePaperId,
} from "@/lib/chatContext";
import type { ConversationTurn, SqlChatOut } from "@/types";

const STORAGE_KEY = "pas.global-sql-chat.v2";
const MAX_MESSAGES = 24;
const MAX_QUERY_LENGTH = 2000;

type FeedbackState = "idle" | "saving" | "saved" | "error";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  result?: SqlChatOut;
  feedback?: FeedbackState;
};

type FailedRequest = {
  query: string;
  conversation: ConversationTurn[];
};

const STARTERS = [
  "How many papers are in the current filtered scope?",
  "Count papers by year.",
  "Top 10 institutions by distinct papers.",
  "Which papers use \"Bayesian optimization\"?",
];

function newId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

function isSqlChatOut(value: unknown): value is SqlChatOut {
  if (!value || typeof value !== "object") return false;
  const row = value as Record<string, unknown>;
  return typeof row.answer === "string"
    && row.model === "deterministic-text-to-sql"
    && typeof row.intent === "string"
    && typeof row.planner === "string"
    && typeof row.resolved_query === "string"
    && typeof row.sql === "string"
    && Array.isArray(row.rows)
    && Boolean(row.audit)
    && typeof row.conversation_turns_used === "number"
    && (row.page_context == null || typeof row.page_context === "string");
}

function loadMessages(): ChatMessage[] {
  try {
    const parsed: unknown = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((value): value is Record<string, unknown> => Boolean(value) && typeof value === "object")
      .filter((value) =>
        (value.role === "user" || value.role === "assistant")
        && typeof value.content === "string"
        && value.content.trim().length > 0,
      )
      .slice(-MAX_MESSAGES)
      .map((value) => ({
        id: typeof value.id === "string" ? value.id : newId(),
        role: value.role as "user" | "assistant",
        content: String(value.content).slice(0, 12000),
        result: isSqlChatOut(value.result) ? value.result : undefined,
        feedback: value.feedback === "saved" ? "saved" : "idle",
      }));
  } catch {
    return [];
  }
}

function conversationFrom(messages: ChatMessage[]): ConversationTurn[] {
  return messages.slice(-12).map((message) => ({
    role: message.role,
    content: message.content.slice(0, 4000),
  }));
}

export function GlobalChat() {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>(loadMessages);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [failedRequest, setFailedRequest] = useState<FailedRequest | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const launcherRef = useRef<HTMLButtonElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const requestGeneration = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const inFlightRef = useRef(false);
  const activeRequestRef = useRef<FailedRequest | null>(null);
  const wasOpenRef = useRef(false);

  const params = useMemo(
    () => new URLSearchParams(location.search),
    [location.search],
  );
  const yearFrom = numericSearchParam(params, "year_from");
  const yearTo = numericSearchParam(params, "year_to");
  const scopedPaperId = scopedEvidencePaperId(location.pathname);
  const currentPageContext = chatPageContext(location.pathname, location.search);

  useEffect(() => {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-MAX_MESSAGES)));
    } catch {
      // The chat remains usable when browser storage is disabled or full.
    }
  }, [messages]);

  useEffect(() => {
    if (open) {
      inputRef.current?.focus();
    } else if (wasOpenRef.current) {
      launcherRef.current?.focus();
    }
    wasOpenRef.current = open;
  }, [open]);

  useEffect(() => {
    if (!open) return;
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, loading, open]);

  useEffect(() => () => abortRef.current?.abort(), []);

  async function send(
    rawQuery: string,
    conversation: ConversationTurn[],
    appendUser: boolean,
  ) {
    const normalized = rawQuery.trim().slice(0, MAX_QUERY_LENGTH);
    if (!normalized || inFlightRef.current) return;

    const generation = ++requestGeneration.current;
    inFlightRef.current = true;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const activeRequest = { query: normalized, conversation };
    activeRequestRef.current = activeRequest;
    let timedOut = false;
    const timeoutId = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, 90_000);
    if (appendUser) {
      const userMessage: ChatMessage = {
        id: newId(),
        role: "user",
        content: normalized,
      };
      setMessages((current) => [
        ...current,
        userMessage,
      ].slice(-MAX_MESSAGES));
    }
    setQuery("");
    setLoading(true);
    setError(null);
    setFailedRequest(null);

    try {
      const result = await retrieveSqlChat({
        query: normalized,
        paper_ids: scopedPaperId ? [scopedPaperId] : null,
        conversation,
        page_context: currentPageContext,
      }, params, controller.signal);
      if (generation !== requestGeneration.current) return;
      const assistantMessage: ChatMessage = {
        id: newId(),
        role: "assistant",
        content: result.answer,
        result,
        feedback: "idle",
      };
      setMessages((current) => [
        ...current,
        assistantMessage,
      ].slice(-MAX_MESSAGES));
      activeRequestRef.current = null;
    } catch (caught) {
      if (generation !== requestGeneration.current) return;
      if (controller.signal.aborted && !timedOut) return;
      const failureMessage = caught instanceof Error ? caught.message : "";
      setError(
        timedOut
          ? "The database query exceeded 90 seconds. Narrow the question or try again."
          : failureMessage.includes("422")
            ? "This question could not be mapped to an approved SQL template. Try one of the supported examples or narrow the wording."
            : "The read-only SQL assistant could not reach the database API. Check the connection and try again.",
      );
      setFailedRequest(activeRequest);
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
    void send(query, conversationFrom(messages), true);
  }

  function handleInputKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (query.trim() && !loading) {
        void send(query, conversationFrom(messages), true);
      }
    }
    if (event.key === "Escape") setOpen(false);
  }

  function clearConversation() {
    ++requestGeneration.current;
    abortRef.current?.abort();
    inFlightRef.current = false;
    activeRequestRef.current = null;
    setMessages([]);
    setLoading(false);
    setError(null);
    setFailedRequest(null);
    setQuery("");
    inputRef.current?.focus();
  }

  function cancelRequest() {
    const active = activeRequestRef.current;
    ++requestGeneration.current;
    abortRef.current?.abort();
    inFlightRef.current = false;
    activeRequestRef.current = null;
    setLoading(false);
    setError("The request was cancelled. You can retry when ready.");
    setFailedRequest(active);
  }

  async function saveFeedback(message: ChatMessage, rating: number) {
    if (!message.result || message.feedback === "saving" || message.feedback === "saved") return;
    setMessages((current) => current.map((item) =>
      item.id === message.id ? { ...item, feedback: "saving" } : item
    ));
    try {
      await submitRagFeedback({
        query: message.result.resolved_query || message.content,
        rating,
        failure_type: rating <= 2 ? "sql_chat_answer_needs_work" : null,
        answer_model: message.result.model,
        source_chunk_ids: [],
        source_paper_ids: [],
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

  return (
    <div className={`global-chat ${open ? "is-open" : ""}`}>
      {open && (
        <section
          id="global-corpus-chat"
          className="global-chat-panel"
          role="dialog"
          aria-modal="false"
          aria-label="Ask the paper corpus"
          onKeyDown={(event) => {
            if (event.key === "Escape") setOpen(false);
          }}
        >
          <header className="global-chat-header">
            <div>
              <span className="review-kicker">Deterministic read-only queries</span>
              <h2>Ask the database</h2>
            </div>
            <div className="global-chat-header-actions">
              {messages.length > 0 && (
                <button type="button" onClick={clearConversation}>Clear</button>
              )}
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
            <span>Strict Text-to-SQL</span>
            <span>No LLM</span>
            {(yearFrom != null || yearTo != null) && (
              <span>{yearFrom ?? "…"}–{yearTo ?? "…"}</span>
            )}
            {scopedPaperId && <span>Paper {scopedPaperId}</span>}
            <Link to="/retrieval" onClick={() => setOpen(false)}>Graph RAG workspace (separate)</Link>
          </div>

          <div className="global-chat-messages" ref={scrollRef} aria-live="polite">
            {messages.length === 0 && !loading && (
              <div className="global-chat-empty">
                <strong>Ask for structured corpus facts.</strong>
                <p>Every answer is rendered directly from a parameter-bound, read-only SQL template. Unsupported or ambiguous questions fail closed; the current page filter and paper scope are inherited.</p>
                <div>
                  {STARTERS.map((starter) => (
                    <button
                      key={starter}
                      type="button"
                      onClick={() => void send(starter, [], true)}
                    >
                      {starter}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((message) => (
              <article key={message.id} className={`global-chat-message ${message.role}`}>
                <div className="global-chat-role">{message.role === "user" ? "You" : "SQL assistant"}</div>
                <div className="global-chat-content">{message.content}</div>
                {message.result && (
                  <>
                    <div className="global-chat-answer-meta">
                      <span>{message.result.intent}</span>
                      <span>{message.result.rows.length} rows</span>
                      <span>No LLM</span>
                    </div>
                    <details className="global-chat-sources">
                      <summary>Inspect SQL, parameters, rows, and audit</summary>
                      {message.result.page_context && (
                        <div className="global-chat-retrieval-query">
                          <strong>Page context:</strong> {message.result.page_context}
                        </div>
                      )}
                      <div className="global-chat-retrieval-query">
                        <strong>Resolved question:</strong> {message.result.resolved_query}
                      </div>
                      <div className="global-chat-sql-audit">
                        <strong>SQL template</strong>
                        <pre>{message.result.sql}</pre>
                        <strong>Bound parameters</strong>
                        <pre>{JSON.stringify(message.result.parameters, null, 2)}</pre>
                        <strong>Returned rows</strong>
                        <pre>{JSON.stringify(message.result.rows, null, 2)}</pre>
                        <div className="global-chat-sql-fingerprints">
                          <span>Scope papers: {message.result.audit.scope_paper_count}</span>
                          <span>Filter: {message.result.audit.page_filter_fingerprint.slice(0, 12)}</span>
                          <span>Paper set: {message.result.audit.scope_paper_set_sha256.slice(0, 12)}</span>
                          <span>Statement: {message.result.audit.statement_sha256.slice(0, 12)}</span>
                          <span>{message.result.audit.parameter_binding}</span>
                        </div>
                      </div>
                    </details>
                    <div className="global-chat-feedback" aria-live="polite">
                      {message.feedback === "saved" ? (
                        <span>Feedback saved.</span>
                      ) : (
                        <>
                          <span>Was this SQL-backed answer useful?</span>
                          <button
                            type="button"
                            disabled={message.feedback === "saving"}
                            onClick={() => void saveFeedback(message, 5)}
                          >
                            Useful
                          </button>
                          <button
                            type="button"
                            disabled={message.feedback === "saving"}
                            onClick={() => void saveFeedback(message, 1)}
                          >
                            Needs work
                          </button>
                          {message.feedback === "error" && <span role="alert">Feedback failed. Try again.</span>}
                        </>
                      )}
                    </div>
                  </>
                )}
              </article>
            ))}

            {loading && (
              <div className="global-chat-loading" role="status">
                <span aria-hidden="true" />
                <span>Planning approved SQL and querying the database…</span>
                <button type="button" onClick={cancelRequest}>Cancel</button>
              </div>
            )}
            {error && (
              <div className="global-chat-error" role="alert">
                <span>{error}</span>
                {failedRequest && (
                  <button
                    type="button"
                    onClick={() => void send(
                      failedRequest.query,
                      failedRequest.conversation,
                      false,
                    )}
                  >
                    Try again
                  </button>
                )}
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
                placeholder="Ask for counts, papers, authors, institutions, methods, topics, funders, or the review queue…"
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={handleInputKeyDown}
                disabled={loading}
              />
              <button type="submit" disabled={loading || !query.trim()}>
                {loading ? "Searching" : "Send"}
              </button>
            </div>
            <small>Enter to send · Shift+Enter for a new line · unsupported questions are rejected instead of sent to an LLM.</small>
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
          <span>Ask the database</span>
        </button>
      )}
    </div>
  );
}
