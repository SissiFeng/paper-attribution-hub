import { useCallback, useEffect, useMemo, useState } from "react";

import {
  confirmClassification,
  getReviewQueue,
  getReviewQueueSize,
  skipReview,
  submitReview,
} from "@/lib/api";
import { RagStatusBadge, RagStatusPanel } from "@/components/RagStatusBadge";
import type { QueueItem, RelevanceLabel } from "@/types";

const LABEL_OPTIONS: RelevanceLabel[] = [
  "CORE_RELEVANT",
  "RELATED_RELEVANT",
  "ADJACENT",
  "UNCERTAIN",
  "EXCLUDE",
];

interface Toast {
  text: string;
  kind: "success" | "error";
}

function relativeTime(iso: string | null): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const diffMs = Date.now() - then;
  const min = Math.floor(diffMs / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day}d ago`;
  return new Date(iso).toLocaleDateString();
}

function reasonClass(reason: string): "good" | "warn" | "danger" | "" {
  const lower = reason.toLowerCase();
  if (lower.includes("disqualifying") || lower.includes("rejected")) return "danger";
  if (lower.includes("uncertain") || lower.includes("low confidence") || lower.includes("borderline"))
    return "warn";
  if (lower.includes("matched ac") || lower.includes("confirmed")) return "good";
  return "";
}

export default function ReviewQueuePage() {
  const [items, setItems] = useState<QueueItem[]>([]);
  const [size, setSize] = useState<number>(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [working, setWorking] = useState(false);
  const [toast, setToast] = useState<Toast | null>(null);
  const [reviewerName, setReviewerName] = useState<string>(() => {
    return localStorage.getItem("pas_reviewer") || "";
  });
  const [notes, setNotes] = useState<string>("");
  const [pendingLabel, setPendingLabel] = useState<RelevanceLabel | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [queue, count] = await Promise.all([
        getReviewQueue({ limit: 50 }),
        getReviewQueueSize(),
      ]);
      setItems(queue);
      setSize(count.count);
      if (queue.length && !queue.some((q) => q.paper_id === selectedId)) {
        setSelectedId(queue[0].paper_id);
        setPendingLabel(null);
        setNotes("");
      } else if (!queue.length) {
        setSelectedId(null);
      }
    } catch (e) {
      setToast({ text: e instanceof Error ? e.message : String(e), kind: "error" });
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2800);
    return () => clearTimeout(t);
  }, [toast]);

  useEffect(() => {
    if (reviewerName) localStorage.setItem("pas_reviewer", reviewerName);
  }, [reviewerName]);

  const selected = useMemo(
    () => items.find((it) => it.paper_id === selectedId) ?? null,
    [items, selectedId]
  );

  const handleSelect = (paperId: string) => {
    setSelectedId(paperId);
    setPendingLabel(null);
    setNotes("");
  };

  const advanceAfterAction = (currentId: string) => {
    const idx = items.findIndex((it) => it.paper_id === currentId);
    const next = items[idx + 1] ?? items[idx - 1] ?? null;
    setSelectedId(next ? next.paper_id : null);
    setItems((prev) => prev.filter((it) => it.paper_id !== currentId));
    setSize((n) => Math.max(0, n - 1));
    setPendingLabel(null);
    setNotes("");
  };

  const handleConfirm = async () => {
    if (!selected) return;
    setWorking(true);
    try {
      await confirmClassification(selected.paper_id, {
        reviewer: reviewerName || undefined,
      });
      setToast({ text: `Confirmed ${selected.paper_id} as ${selected.label}`, kind: "success" });
      advanceAfterAction(selected.paper_id);
    } catch (e) {
      setToast({ text: e instanceof Error ? e.message : String(e), kind: "error" });
    } finally {
      setWorking(false);
    }
  };

  const handleCorrect = async () => {
    if (!selected || !pendingLabel) return;
    setWorking(true);
    try {
      await submitReview(selected.paper_id, {
        human_label: pendingLabel,
        reviewer: reviewerName || undefined,
        notes: notes || undefined,
      });
      setToast({
        text: `Corrected ${selected.paper_id}: ${selected.label} → ${pendingLabel}`,
        kind: "success",
      });
      advanceAfterAction(selected.paper_id);
    } catch (e) {
      setToast({ text: e instanceof Error ? e.message : String(e), kind: "error" });
    } finally {
      setWorking(false);
    }
  };

  const handleSkip = async () => {
    if (!selected) return;
    setWorking(true);
    try {
      await skipReview(selected.paper_id, { cooldown_days: 7 });
      setToast({ text: `Deferred ${selected.paper_id} for 7 days`, kind: "success" });
      advanceAfterAction(selected.paper_id);
    } catch (e) {
      setToast({ text: e instanceof Error ? e.message : String(e), kind: "error" });
    } finally {
      setWorking(false);
    }
  };

  return (
    <div className="v7-page">
      <div className="v7-hero">
        <div>
          <h1>Review Queue</h1>
          <p>
            Priority-sorted by review-need. Confirm what the classifier got right; correct what it
            got wrong. Corrections feed back into the active-learning loop.
          </p>
        </div>
        <div className="v7-hero-actions">
          <input
            className="v7-btn ghost"
            placeholder="reviewer name"
            value={reviewerName}
            onChange={(e) => setReviewerName(e.target.value)}
            style={{ width: 140 }}
          />
          <button className="v7-btn" onClick={() => void load()} disabled={loading}>
            ↻ {loading ? "Loading…" : "Refresh"}
          </button>
        </div>
      </div>

      <div className="v7-stat-grid">
        <div className="v7-stat">
          <div className="label">Outstanding</div>
          <div className="value">{size}</div>
          <div className="delta">papers flagged for review</div>
        </div>
        <div className="v7-stat">
          <div className="label">Top priority</div>
          <div className="value">
            {items[0] ? items[0].priority.toFixed(2) : "—"}
          </div>
          <div className="delta">highest-priority score in queue</div>
        </div>
        <div className="v7-stat">
          <div className="label">Loaded</div>
          <div className="value">{items.length}</div>
          <div className="delta">showing on this page</div>
        </div>
      </div>

      <div className="v7-split">
        <div className="v7-list">
          {loading && items.length === 0 ? (
            <>
              <div className="v7-skel card" />
              <div className="v7-skel card" />
              <div className="v7-skel card" />
            </>
          ) : items.length === 0 ? (
            <div className="v7-empty">
              <span className="icon">✓</span>
              <div>The review queue is clear.</div>
              <div style={{ marginTop: 8, fontSize: 13 }}>
                The next pipeline run will surface new candidates.
              </div>
            </div>
          ) : (
            items.map((it) => (
              <button
                key={it.paper_id}
                className={`v7-list-item ${it.paper_id === selectedId ? "active" : ""}`}
                onClick={() => handleSelect(it.paper_id)}
                style={{ textAlign: "left" }}
              >
                <div className="item-row">
                  <span className="priority-pill">⚡ {it.priority.toFixed(2)}</span>
                  <span className={`v7-label ${it.label}`}>{it.label.replace("_", " ")}</span>
                  <RagStatusBadge status={it.rag_status} compact />
                </div>
                <div className="item-title">{it.title}</div>
                <div className="item-meta">
                  <span>conf {it.confidence.toFixed(2)}</span>
                  <span>·</span>
                  <span>{relativeTime(it.last_classified_at)}</span>
                  {it.provenance && (
                    <>
                      <span>·</span>
                      <span>{it.provenance}</span>
                    </>
                  )}
                  {it.has_human_review && (
                    <>
                      <span>·</span>
                      <span style={{ color: "var(--accent)" }}>reviewed</span>
                    </>
                  )}
                </div>
              </button>
            ))
          )}
        </div>

        {selected ? (
          <div className="v7-detail">
            <div className="v7-detail-head">
              <div style={{ flex: 1 }}>
                <h2>{selected.title}</h2>
                <div className="meta-row">
                  <span>
                    <code style={{ fontFamily: "ui-monospace, monospace", fontSize: "0.8rem" }}>
                      {selected.paper_id}
                    </code>
                  </span>
                  <span>{relativeTime(selected.last_classified_at)}</span>
                  {selected.provenance && <span>{selected.provenance}</span>}
                </div>
              </div>
              <span className={`v7-label ${selected.label}`}>
                {selected.label.replace("_", " ")}
              </span>
            </div>

            <div className="v7-score-grid">
              <div className="v7-score-cell">
                <div className="label">Confidence</div>
                <div className="value">{selected.confidence.toFixed(2)}</div>
                <div className="bar">
                  <i style={{ width: `${selected.confidence * 100}%` }} />
                </div>
              </div>
              <div className="v7-score-cell">
                <div className="label">Priority</div>
                <div className="value">{selected.priority.toFixed(2)}</div>
                <div className="bar">
                  <i style={{ width: `${selected.priority * 100}%` }} />
                </div>
              </div>
            </div>

            <RagStatusPanel status={selected.rag_status} />

            <div>
              <h2 style={{ fontSize: "1rem", margin: "0 0 0.5rem" }}>Why this is flagged</h2>
              <ul className="v7-reasons">
                {selected.reasons.length === 0 ? (
                  <li>No specific reasons recorded.</li>
                ) : (
                  selected.reasons.map((r, i) => (
                    <li key={i} className={reasonClass(r)}>
                      {r}
                    </li>
                  ))
                )}
              </ul>
            </div>

            <div>
              <h2 style={{ fontSize: "1rem", margin: "0 0 0.5rem" }}>
                Correct the label
              </h2>
              <div className="v7-label-select">
                {LABEL_OPTIONS.map((opt) => (
                  <button
                    key={opt}
                    className={pendingLabel === opt ? `active ${opt}` : ""}
                    onClick={() => setPendingLabel(opt === pendingLabel ? null : opt)}
                  >
                    {opt.replace("_", " ")}
                  </button>
                ))}
              </div>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Notes (optional)"
                rows={2}
                style={{
                  marginTop: 8,
                  width: "100%",
                  background: "rgba(255,255,255,0.03)",
                  border: "1px solid var(--v7-glass-border)",
                  borderRadius: 8,
                  color: "var(--text)",
                  padding: "0.5rem 0.7rem",
                  fontFamily: "inherit",
                  fontSize: "0.88rem",
                  resize: "vertical",
                }}
              />
            </div>

            <div className="v7-action-bar">
              <button
                className="v7-btn success"
                onClick={handleConfirm}
                disabled={working}
              >
                ✓ Confirm {selected.label.replace("_", " ")}
              </button>
              <button
                className="v7-btn primary"
                onClick={handleCorrect}
                disabled={!pendingLabel || working}
              >
                ✎ Submit correction
              </button>
              <button className="v7-btn ghost" onClick={handleSkip} disabled={working}>
                ⤳ Defer 7d
              </button>
              <a
                className="v7-btn ghost"
                href={`/?selected=${selected.paper_id}`}
                target="_blank"
                rel="noreferrer"
                style={{ marginLeft: "auto" }}
              >
                Open in main view →
              </a>
            </div>
          </div>
        ) : (
          <div className="v7-detail">
            <div className="v7-empty">
              <span className="icon">⌛</span>
              <div>Select a paper from the queue to review.</div>
            </div>
          </div>
        )}
      </div>

      {toast && <div className={`v7-toast ${toast.kind}`}>{toast.text}</div>}
    </div>
  );
}
