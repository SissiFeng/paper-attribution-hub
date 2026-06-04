import type { RagStatus } from "@/types";

const LABELS: Record<string, string> = {
  ready: "RAG ready",
  missing_fulltext: "Needs fulltext",
  needs_ingest: "Needs ingest",
  needs_embeddings: "Needs embeddings",
  no_attribution_evidence: "No evidence",
};

const DETAILS: Record<string, string> = {
  ready: "Fulltext chunks, embeddings, and attribution evidence are ready.",
  missing_fulltext: "Upload a PDF/TXT/MD or run fulltext fetch.",
  needs_ingest: "Fulltext is marked available, but chunks are missing.",
  needs_embeddings: "Chunks exist, but embeddings are incomplete.",
  no_attribution_evidence: "Chunks are searchable, but attribution evidence was not extracted.",
};

interface Props {
  status?: RagStatus | null;
  compact?: boolean;
}

export function RagStatusBadge({ status, compact = false }: Props) {
  const key = status?.status ?? "missing_fulltext";
  const label = LABELS[key] ?? key.replace(/_/g, " ");
  const title = status?.action_hint ?? DETAILS[key] ?? label;
  return (
    <span
      className={`rag-status-badge ${status?.ready ? "ready" : "needs-action"} ${key}`}
      title={title}
    >
      <span className="rag-status-dot" />
      {compact ? label.replace("Needs ", "") : label}
    </span>
  );
}

export function RagStatusPanel({ status }: { status?: RagStatus | null }) {
  const s = status;
  if (!s) {
    return (
      <div className="rag-status-panel needs-action">
        <div className="rag-status-panel-head">
          <RagStatusBadge status={s} />
        </div>
        <p>Fulltext readiness has not been computed for this paper.</p>
      </div>
    );
  }

  return (
    <div className={`rag-status-panel ${s.ready ? "ready" : "needs-action"}`}>
      <div className="rag-status-panel-head">
        <RagStatusBadge status={s} />
        <span className="rag-status-action">
          {s.needs_action ? s.needs_action.replace(/_/g, " ") : "ready"}
        </span>
      </div>
      <p>{s.action_hint}</p>
      <div className="rag-status-metrics">
        <span>{s.chunk_count} chunks</span>
        <span>{s.embedded_chunk_count} embedded</span>
        <span>{s.evidence_count} evidence</span>
        <span>{s.attribution_evidence_count} attribution</span>
      </div>
    </div>
  );
}
