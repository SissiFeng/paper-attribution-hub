import { useCallback, useEffect, useMemo, useState } from "react";

import {
  getModelEvolutionStatus,
  getReviewQueue,
  getReviewQueueSize,
  getStage1Readiness,
  skipReview,
  submitReview,
  updateReviewAssignment,
} from "@/lib/api";
import { RagStatusBadge, RagStatusPanel } from "@/components/RagStatusBadge";
import { Stage1Unavailable } from "@/components/Stage1Unavailable";
import type {
  AcRelevanceJudgement,
  AiForScienceJudgement,
  EvidenceLevel,
  JudgementBasis,
  QueueItem,
  RelevanceLabel,
  SdlJudgement,
  Stage1Readiness,
} from "@/types";

const LABEL_OPTIONS: RelevanceLabel[] = [
  "CORE_RELEVANT",
  "RELATED_RELEVANT",
  "ADJACENT",
  "UNCERTAIN",
  "EXCLUDE",
];
const SDL_OPTIONS: Array<{ value: SdlJudgement; label: string }> = [
  { value: "CONFIRMED_SDL", label: "Confirmed SDL" },
  { value: "PROBABLE_SDL", label: "Probable SDL" },
  { value: "SDL_ADJACENT", label: "SDL-adjacent" },
  { value: "NOT_SDL", label: "Not SDL" },
  { value: "INSUFFICIENT_EVIDENCE", label: "Need evidence" },
];
const AC_OPTIONS: Array<{ value: AcRelevanceJudgement; label: string }> = [
  { value: "AC_RELEVANT", label: "AC relevant" },
  { value: "NOT_AC_RELEVANT", label: "Not AC relevant" },
  { value: "INSUFFICIENT_EVIDENCE", label: "Need evidence" },
];
const AI_OPTIONS: Array<{ value: AiForScienceJudgement; label: string }> = [
  { value: "AI_FOR_SCIENCE", label: "AI for science" },
  { value: "NOT_AI_FOR_SCIENCE", label: "Not AI for science" },
  { value: "INSUFFICIENT_EVIDENCE", label: "Need evidence" },
];
const EVIDENCE_OPTIONS: Array<{ value: EvidenceLevel; label: string }> = [
  { value: "TITLE_ONLY", label: "Title only" },
  { value: "ABSTRACT", label: "Title + abstract" },
  { value: "FULLTEXT", label: "Full text" },
  { value: "SUPPORTING_INFORMATION", label: "Supporting information" },
  { value: "UNKNOWN", label: "Unknown" },
];

interface Toast {
  text: string;
  kind: "success" | "error";
}

type QueueMode = "all" | "mine" | "unassigned";
type Stage1Batch =
  | "train-1"
  | "train-2"
  | "train-3"
  | "validation"
  | "frozen-test";

const STAGE1_BATCHES: Array<{
  value: Stage1Batch;
  label: string;
  role: NonNullable<QueueItem["stage1_role"]>;
  round: number | null;
}> = [
  { value: "train-1", label: "Train · round 1", role: "train", round: 1 },
  { value: "train-2", label: "Train · round 2", role: "train", round: 2 },
  { value: "train-3", label: "Train · round 3", role: "train", round: 3 },
  { value: "validation", label: "Validation", role: "validation", round: null },
  { value: "frozen-test", label: "Frozen test", role: "frozen_test", round: null },
];

function matchesStage1Batch(item: QueueItem, batch: Stage1Batch): boolean {
  const spec = STAGE1_BATCHES.find((candidate) => candidate.value === batch);
  return Boolean(
    spec &&
      item.stage1_role === spec.role &&
      (spec.round === null || item.stage1_round === spec.round),
  );
}

function stage1BatchName(item: QueueItem): string {
  const ordinal = item.stage1_ordinal ? ` · #${item.stage1_ordinal}` : "";
  if (item.stage1_role === "train") {
    return `Train · round ${item.stage1_round ?? "—"}${ordinal}`;
  }
  if (item.stage1_role === "frozen_test") return `Frozen test${ordinal}`;
  if (item.stage1_role === "validation") return `Validation${ordinal}`;
  return "Stage 1";
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
  const [readiness, setReadiness] = useState<Stage1Readiness | null>(null);
  const [working, setWorking] = useState(false);
  const [toast, setToast] = useState<Toast | null>(null);
  const [reviewerName, setReviewerName] = useState<string>(() => {
    return localStorage.getItem("pas_reviewer") || "";
  });
  const [notes, setNotes] = useState<string>("");
  const [pendingLabel, setPendingLabel] = useState<RelevanceLabel | null>(null);
  const [sdlJudgement, setSdlJudgement] = useState<SdlJudgement | null>(null);
  const [acJudgement, setAcJudgement] = useState<AcRelevanceJudgement | null>(null);
  const [aiJudgement, setAiJudgement] = useState<AiForScienceJudgement | null>(null);
  const [evidenceLevel, setEvidenceLevel] = useState<EvidenceLevel>("ABSTRACT");
  const [judgementBasis, setJudgementBasis] = useState<JudgementBasis>("DUAL_REVIEW");
  const [queueMode, setQueueMode] = useState<QueueMode>("all");
  const [stage1Batch, setStage1Batch] = useState<Stage1Batch>("train-1");
  const queueParams = useMemo(() => ({
    assignee: queueMode === "mine" ? reviewerName.trim() || undefined : undefined,
    unassigned_only: queueMode === "unassigned",
  }), [queueMode, reviewerName]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const stage1 = await getStage1Readiness();
      setReadiness(stage1);
      if (!stage1.derived_views_enabled) {
        setItems([]);
        setSize(0);
        setSelectedId(null);
        return;
      }
      const [queue, count] = await Promise.all([
        getReviewQueue({ limit: stage1.stage1_only ? 200 : 50, ...queueParams }),
        getReviewQueueSize(queueParams),
      ]);
      const visibleQueue = stage1.stage1_only
        ? queue.filter((item) => matchesStage1Batch(item, stage1Batch))
        : queue;
      setItems(visibleQueue);
      setSize(stage1.stage1_only ? visibleQueue.length : count.count);
      setSelectedId((current) => (
        current && visibleQueue.some((item) => item.paper_id === current)
          ? current
          : visibleQueue[0]?.paper_id ?? null
      ));
    } catch (e) {
      setToast({ text: e instanceof Error ? e.message : String(e), kind: "error" });
    } finally {
      setLoading(false);
    }
  }, [queueParams, stage1Batch]);

  useEffect(() => {
    void load();
  }, [load]);

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

  useEffect(() => {
    const stage1 = Boolean(readiness?.stage1_only);
    setPendingLabel(stage1 ? null : selected?.label ?? null);
    setNotes("");
    setSdlJudgement(selected?.sdl_judgement ?? null);
    setAcJudgement(stage1 ? null : selected?.ac_relevance_judgement ?? null);
    setAiJudgement(stage1 ? null : selected?.ai_for_science_judgement ?? null);
    setEvidenceLevel(selected?.evidence_level ?? (stage1 ? "FULLTEXT" : "ABSTRACT"));
    setJudgementBasis(stage1 ? "STRICT_SDL" : selected?.judgement_basis ?? "DUAL_REVIEW");
  }, [readiness?.stage1_only, selectedId]);

  const handleSelect = (paperId: string) => {
    setSelectedId(paperId);
  };

  const advanceAfterAction = (currentId: string) => {
    const idx = items.findIndex((it) => it.paper_id === currentId);
    const next = items[idx + 1] ?? items[idx - 1] ?? null;
    setSelectedId(next ? next.paper_id : null);
    setItems((prev) => prev.filter((it) => it.paper_id !== currentId));
    setSize((n) => Math.max(0, n - 1));
    setPendingLabel(null);
    setNotes("");
    setSdlJudgement(null);
    setAcJudgement(null);
    setAiJudgement(null);
    setEvidenceLevel("ABSTRACT");
    setJudgementBasis("DUAL_REVIEW");
  };

  const handleSubmitReview = async () => {
    const stage1 = Boolean(readiness?.stage1_only);
    if (!selected || !sdlJudgement || (!stage1 && !acJudgement)) return;
    const needsFulltext =
      sdlJudgement === "INSUFFICIENT_EVIDENCE" ||
      (!stage1 && acJudgement === "INSUFFICIENT_EVIDENCE");
    setWorking(true);
    try {
      await submitReview(selected.paper_id, {
        human_label: stage1 || needsFulltext
          ? undefined
          : pendingLabel ?? selected.label,
        sdl_judgement: sdlJudgement,
        ac_relevance_judgement: stage1 ? undefined : acJudgement ?? undefined,
        ai_for_science_judgement: stage1 ? undefined : aiJudgement ?? undefined,
        review_status: needsFulltext ? "NEEDS_FULLTEXT" : "COMPLETED",
        evidence_level: evidenceLevel,
        judgement_basis: stage1 ? "STRICT_SDL" : judgementBasis,
        reviewer: reviewerName || undefined,
        notes: notes || undefined,
      });
      const evolutionStatus = stage1 || needsFulltext
        ? null
        : await getModelEvolutionStatus();
      const learningUpdate = evolutionStatus
        ? evolutionStatus.pending_reviews === 0 &&
          evolutionStatus.latest_run
          ? ` · full retrain ${evolutionStatus.latest_run.status.toLowerCase()}`
          : evolutionStatus.reviews_until_retrain === 0
          ? ` · ${evolutionStatus.active_run ? "retraining in progress" : "retraining batch ready"}`
          : ` · ${evolutionStatus.reviews_until_retrain} reviews to next retrain`
        : "";
      setToast({
        text: needsFulltext
          ? `Saved ${selected.paper_id} for full-text review`
          : stage1
          ? `Saved blinded strict-SDL label · ${stage1BatchName(selected)}`
          : `Saved ${selected.paper_id} and added its label to the learning loop${learningUpdate}`,
        kind: "success",
      });
      if (needsFulltext) {
        setItems((previous) =>
          previous.map((item) =>
            item.paper_id === selected.paper_id
              ? {
                  ...item,
                  has_human_review: true,
                  sdl_judgement: sdlJudgement,
                  ac_relevance_judgement: acJudgement,
                  ai_for_science_judgement: aiJudgement,
                  review_status: "NEEDS_FULLTEXT",
                  evidence_level: evidenceLevel,
                  judgement_basis: judgementBasis,
                }
              : item
          )
        );
        const index = items.findIndex(
          (item) => item.paper_id === selected.paper_id
        );
        const next = items[index + 1] ?? items[index - 1] ?? null;
        if (next) setSelectedId(next.paper_id);
      } else {
        advanceAfterAction(selected.paper_id);
      }
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

  const handleAssignment = async (assignee: string | null) => {
    if (!selected) return;
    if (assignee && !reviewerName.trim()) {
      setToast({ text: "Enter your reviewer name before claiming a paper.", kind: "error" });
      return;
    }
    setWorking(true);
    try {
      await updateReviewAssignment(selected.paper_id, {
        assignee,
        assigned_by: reviewerName.trim() || undefined,
      });
      setToast({
        text: assignee
          ? `Assigned ${selected.paper_id} to ${assignee}`
          : `Released ${selected.paper_id}`,
        kind: "success",
      });
      await load();
    } catch (e) {
      setToast({ text: e instanceof Error ? e.message : String(e), kind: "error" });
    } finally {
      setWorking(false);
    }
  };

  if (readiness && !readiness.derived_views_enabled) {
    return (
      <Stage1Unavailable
        title="Review Queue"
        description="Human review begins only after the Tier 1 full-text corpus has been acquired and the classifier has completed its controlled training and validation rounds."
        readiness={readiness}
        loading={loading}
        onRefresh={() => void load()}
      />
    );
  }

  return (
    <div className="v7-page">
      <div className="v7-hero">
        <div>
          <h1>Review Queue</h1>
          <p>
            {readiness?.stage1_only
              ? "Blinded strict-SDL annotation over the frozen Zotero Tier 1 batches. AC relevance and model predictions are excluded."
              : "Review SDL relevance and AC reporting relevance independently. Model-label corrections are optional and only explicit corrections feed the training loop."}
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
          <div className="delta">
            {queueMode === "mine"
              ? `assigned to ${reviewerName || "you"}`
              : queueMode === "unassigned"
                ? "available to claim"
                : "papers flagged for review"}
          </div>
        </div>
        <div className="v7-stat">
          <div className="label">{readiness?.stage1_only ? "Current batch" : "Top priority"}</div>
          <div className="value">
            {readiness?.stage1_only
              ? items[0]
                ? stage1BatchName(items[0])
                : "—"
              : items[0]
                ? items[0].priority.toFixed(2)
                : "—"}
          </div>
          <div className="delta">
            {readiness?.stage1_only
              ? `${readiness.completed_label_counts?.[
                  stage1Batch === "train-1"
                    ? "train_round_1"
                    : stage1Batch === "train-2"
                      ? "train_round_2"
                      : stage1Batch === "train-3"
                        ? "train_round_3"
                        : stage1Batch === "validation"
                          ? "validation"
                          : "frozen_test"
                ] ?? 0} completed`
              : "highest-priority score in queue"}
          </div>
        </div>
        <div className="v7-stat">
          <div className="label">Loaded</div>
          <div className="value">{items.length}</div>
          <div className="delta">showing on this page</div>
        </div>
      </div>

      <div className="v7-graph-toolbar" aria-label="Review queue ownership">
        <span className="toolbar-label">
          {readiness?.stage1_only ? "Review batch" : "Queue"}
        </span>
        {readiness?.stage1_only && (
          <select
            className="v7-btn ghost"
            value={stage1Batch}
            aria-label="Select frozen Stage 1 review batch"
            onChange={(event) => setStage1Batch(event.target.value as Stage1Batch)}
          >
            {STAGE1_BATCHES.map((batch) => {
              const configuredCount =
                batch.role === "train" && batch.round !== null
                  ? readiness.train_round_counts?.[String(batch.round)]
                  : readiness.split_role_counts?.[batch.role];
              return (
                <option key={batch.value} value={batch.value}>
                  {batch.label} · {configuredCount ?? 0}
                </option>
              );
            })}
          </select>
        )}
        {(["all", "mine", "unassigned"] as QueueMode[]).map((mode) => (
          <button
            type="button"
            key={mode}
            className={`v7-toggle ${queueMode === mode ? "on" : ""}`}
            aria-pressed={queueMode === mode}
            disabled={mode === "mine" && !reviewerName.trim()}
            onClick={() => setQueueMode(mode)}
          >
            {mode === "all"
              ? "All queued"
              : mode === "mine"
                ? "Assigned to me"
                : "Unassigned"}
          </button>
        ))}
        <span className="metric-note">
          {readiness?.stage1_only
            ? "Predictions are hidden while annotating. Training reads only completed train-round labels."
            : "Claims divide the workload; the final review records the actual reviewer."}
        </span>
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
                  {readiness?.stage1_only ? (
                    <span className="priority-pill">{stage1BatchName(it)}</span>
                  ) : (
                    <>
                      <span className="priority-pill">⚡ {it.priority.toFixed(2)}</span>
                      <span className={`v7-label ${it.label}`}>{it.label.replace("_", " ")}</span>
                    </>
                  )}
                  <RagStatusBadge status={it.rag_status} compact />
                </div>
                <div className="item-title">{it.title}</div>
                <div className="item-meta">
                  {!readiness?.stage1_only && (
                    <>
                      <span>conf {it.confidence.toFixed(2)}</span>
                      <span>·</span>
                    </>
                  )}
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
                  {it.review_assignee && (
                    <>
                      <span>·</span>
                      <span>assigned to {it.review_assignee}</span>
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
                  {selected.screening_route && (
                    <span className={`screening-route ${selected.screening_route}`}>
                      {selected.screening_route.replace(/_/g, " ")}
                    </span>
                  )}
                </div>
              </div>
              {readiness?.stage1_only ? (
                <span className="priority-pill">{stage1BatchName(selected)}</span>
              ) : (
                <span className={`v7-label ${selected.label}`}>
                  {selected.label.replace("_", " ")}
                </span>
              )}
            </div>

            {!readiness?.stage1_only && (
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
            )}

            <RagStatusPanel status={selected.rag_status} />

            <div className="review-assignment" role="group" aria-label="Review assignment">
              <div>
                <span className="review-kicker">Work allocation</span>
                <strong>
                  {selected.review_assignee
                    ? `Assigned to ${selected.review_assignee}`
                    : "Unassigned"}
                </strong>
                {selected.review_assigned_at && (
                  <small> since {relativeTime(selected.review_assigned_at)}</small>
                )}
              </div>
              {selected.review_assignee ? (
                <button
                  type="button"
                  className="v7-btn ghost"
                  disabled={working}
                  onClick={() => void handleAssignment(null)}
                >
                  Release
                </button>
              ) : (
                <button
                  type="button"
                  className="v7-btn"
                  disabled={working || !reviewerName.trim()}
                  onClick={() => void handleAssignment(reviewerName.trim())}
                >
                  Claim for me
                </button>
              )}
            </div>

            {selected.screening_reason && (
              <div className="screening-rationale" role="note">
                <span>Why this paper reached review</span>
                <p>{selected.screening_reason}</p>
              </div>
            )}

            <section className="review-context" aria-labelledby="review-context-heading">
              <div className="review-section-heading">
                <div>
                  <span className="review-kicker">Decision context</span>
                  <h2 id="review-context-heading">What the reviewer can verify</h2>
                </div>
                {selected.full_text_url && (
                  <a
                    className="v7-btn ghost"
                    href={selected.full_text_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open paper ↗
                  </a>
                )}
              </div>
              <dl className="review-context-grid">
                <div>
                  <dt>Authors</dt>
                  <dd>
                    {selected.authors?.length
                      ? selected.authors.join(", ")
                      : "Not available"}
                  </dd>
                </div>
                <div>
                  <dt>Institutions</dt>
                  <dd>
                    {selected.institutions?.length
                      ? selected.institutions.join(", ")
                      : "Not available"}
                  </dd>
                </div>
                <div>
                  <dt>Publication</dt>
                  <dd>
                    {[selected.year, selected.venue].filter(Boolean).join(" · ") ||
                      "Not available"}
                    {selected.doi ? ` · ${selected.doi}` : ""}
                  </dd>
                </div>
                <div>
                  <dt>Corpus sources</dt>
                  <dd className="source-chip-row">
                    {(selected.corpus_sources?.length
                      ? selected.corpus_sources
                      : [selected.provenance || selected.source || "unknown"]
                    ).map((source) => (
                      <span className="source-chip" key={source}>
                        {source.replace(/_/g, " ")}
                      </span>
                    ))}
                  </dd>
                </div>
              </dl>
              <div className="review-abstract">
                <span>Abstract</span>
                <p>
                  {selected.abstract ||
                    "No abstract is available. Mark the evidence level honestly and open the full text when possible."}
                </p>
              </div>
            </section>

            {!readiness?.stage1_only && (
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
            )}

            <section className="dual-review" aria-labelledby="dual-review-heading">
              <div className="review-section-heading">
                <div>
                  <span className="review-kicker">
                    {readiness?.stage1_only ? "Blinded gold annotation" : "Independent judgements"}
                  </span>
                  <h2 id="dual-review-heading">
                    {readiness?.stage1_only
                      ? "Strict SDL relevance only"
                      : "Separate SDL from AC relevance"}
                  </h2>
                </div>
                <span className="review-required">
                  {readiness?.stage1_only ? "SDL required" : "SDL + AC required"}
                </span>
              </div>
              <div className="dual-review-grid">
                <fieldset>
                  <legend>Is this an SDL paper?</legend>
                  <div className="review-choice-stack">
                    {SDL_OPTIONS.map((option) => (
                      <button
                        type="button"
                        key={option.value}
                        aria-pressed={sdlJudgement === option.value}
                        className={sdlJudgement === option.value ? "active" : ""}
                        onClick={() => setSdlJudgement(option.value)}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                </fieldset>
                {!readiness?.stage1_only && (
                  <fieldset>
                    <legend>Is this AC relevant?</legend>
                    <div className="review-choice-stack">
                      {AC_OPTIONS.map((option) => (
                        <button
                          type="button"
                          key={option.value}
                          aria-pressed={acJudgement === option.value}
                          className={acJudgement === option.value ? "active" : ""}
                          onClick={() => setAcJudgement(option.value)}
                        >
                          {option.label}
                        </button>
                      ))}
                    </div>
                  </fieldset>
                )}
              </div>
              <div className="review-secondary-row">
                {!readiness?.stage1_only && (
                  <label>
                    <span>AI for science (optional)</span>
                    <select
                      value={aiJudgement ?? ""}
                      onChange={(event) =>
                        setAiJudgement(
                          (event.target.value || null) as AiForScienceJudgement | null
                        )
                      }
                    >
                      <option value="">Not assessed</option>
                      {AI_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                <label>
                  <span>Evidence reviewed</span>
                  <select
                    value={evidenceLevel}
                    onChange={(event) =>
                      setEvidenceLevel(event.target.value as EvidenceLevel)
                    }
                  >
                    {EVIDENCE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                {readiness?.stage1_only ? (
                  <div>
                    <span>Judgement basis</span>
                    <strong>Strict SDL · model-blinded</strong>
                  </div>
                ) : (
                  <label>
                    <span>Judgement basis</span>
                    <select
                      value={judgementBasis}
                      onChange={(event) =>
                        setJudgementBasis(event.target.value as JudgementBasis)
                      }
                    >
                      <option value="DUAL_REVIEW">Dual SDL + AC review</option>
                      <option value="AC_REPORTING">AC reporting judgement</option>
                      <option value="STRICT_SDL">Strict SDL judgement</option>
                      <option value="OTHER">Other documented basis</option>
                    </select>
                  </label>
                )}
              </div>
            </section>

            {!readiness?.stage1_only && <div>
              <h2 style={{ fontSize: "1rem", margin: "0 0 0.5rem" }}>
                Classifier training label
              </h2>
              <p className="review-helper">
                The current prediction is preselected. Confirm it or choose a correction; completed
                reviews enter the next 20-paper full retraining batch. Reviews needing more evidence
                stay out of training.
              </p>
              <div className="v7-label-select">
                {LABEL_OPTIONS.map((opt) => (
                  <button
                    key={opt}
                    className={pendingLabel === opt ? `active ${opt}` : ""}
                    onClick={() => setPendingLabel(opt)}
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
            </div>}

            <div className="v7-action-bar">
              <button
                className="v7-btn primary review-submit"
                onClick={handleSubmitReview}
                disabled={!sdlJudgement || (!readiness?.stage1_only && !acJudgement) || working}
              >
                {working
                  ? "Saving…"
                  : readiness?.stage1_only
                    ? "Save blinded SDL label"
                    : "Save independent review"}
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
