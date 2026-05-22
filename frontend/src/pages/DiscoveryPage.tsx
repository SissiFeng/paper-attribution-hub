import { useCallback, useEffect, useState } from "react";

import {
  approveDiscoveryCandidate,
  listDiscoveryQueue,
  rejectDiscoveryCandidate,
  runDiscovery,
} from "@/lib/api";
import type { DiscoveryCandidate, DiscoveryRunResult } from "@/types";

const STATUS_TABS: { label: string; status: string }[] = [
  { label: "Queued", status: "queued" },
  { label: "Auto-ingested", status: "auto_ingested" },
  { label: "Approved", status: "approved" },
  { label: "Rejected", status: "rejected" },
];

export default function DiscoveryPage() {
  const [status, setStatus] = useState("queued");
  const [items, setItems] = useState<DiscoveryCandidate[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [lastRun, setLastRun] = useState<DiscoveryRunResult | null>(null);
  const [reviewer, setReviewer] = useState("");

  const load = useCallback(async () => {
    setError(null);
    try {
      setItems(await listDiscoveryQueue(status));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [status]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleRun = async () => {
    setRunning(true);
    setError(null);
    try {
      const r = await runDiscovery();
      setLastRun(r);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  };

  const handleApprove = async (id: string) => {
    try {
      await approveDiscoveryCandidate(id, { reviewer: reviewer || undefined });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleReject = async (id: string) => {
    try {
      await rejectDiscoveryCandidate(id, { reviewer: reviewer || undefined });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div>
      <div className="filters" style={{ marginBottom: "0.6rem" }}>
        <button onClick={handleRun} disabled={running}>
          {running ? "Running…" : "Run discovery"}
        </button>
        <input
          type="text"
          value={reviewer}
          placeholder="reviewer name"
          onChange={(e) => setReviewer(e.target.value)}
        />
        <span style={{ color: "var(--muted)" }}>
          {lastRun
            ? `Last run: ${lastRun.candidates_seen} candidates · ${lastRun.auto_ingested} auto · ${lastRun.queued} queued`
            : "Hits OpenAlex / S2 / Crossref (with cache). May take seconds."}
        </span>
      </div>

      <div className="filters">
        {STATUS_TABS.map((t) => (
          <button
            key={t.status}
            className={`chip-toggle ${status === t.status ? "active" : ""}`}
            onClick={() => setStatus(t.status)}
          >
            {t.label}
          </button>
        ))}
        <button onClick={() => void load()} style={{ marginLeft: "auto" }}>
          Refresh
        </button>
      </div>

      {error && (
        <div style={{ color: "var(--uncertain)", marginTop: "0.8rem" }}>
          Backend error: {error}
        </div>
      )}

      {items.length === 0 ? (
        <div className="empty">
          {status === "queued"
            ? "No queued candidates. Click 'Run discovery' to pull from external APIs."
            : `No items with status "${status}".`}
        </div>
      ) : (
        <div className="discovery-list">
          {items.map((c) => (
            <DiscoveryCandidateCard
              key={c.id}
              candidate={c}
              onApprove={() => void handleApprove(c.id)}
              onReject={() => void handleReject(c.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function DiscoveryCandidateCard({
  candidate,
  onApprove,
  onReject,
}: {
  candidate: DiscoveryCandidate;
  onApprove: () => void;
  onReject: () => void;
}) {
  const showActions = candidate.status === "queued";
  return (
    <div className="discovery-card">
      <div className="discovery-header">
        <h3>{candidate.title}</h3>
        <span className="discovery-confidence">
          {(candidate.confidence * 100).toFixed(0)}%
        </span>
      </div>
      <div className="discovery-meta">
        <span>{candidate.year ?? "—"}</span>
        <span>·</span>
        <span>{candidate.venue ?? "—"}</span>
        <span>·</span>
        <span>
          source: <span className="evidence-type">{candidate.source}</span>
        </span>
        {candidate.doi && (
          <>
            <span>·</span>
            <a
              href={`https://doi.org/${candidate.doi}`}
              target="_blank"
              rel="noreferrer"
            >
              {candidate.doi}
            </a>
          </>
        )}
      </div>

      {candidate.authors.length > 0 && (
        <div style={{ color: "var(--muted)", fontSize: "0.85rem", marginTop: "0.4rem" }}>
          {candidate.authors.map((a) => a.name).join(", ")}
        </div>
      )}

      <h4 style={{ marginTop: "0.8rem", marginBottom: "0.2rem", color: "var(--muted)", fontSize: "0.8rem" }}>
        Why we surfaced it
      </h4>
      <ul className="discovery-triggers">
        {candidate.triggers.map((t, i) => (
          <li key={i}>
            <strong>{t.strategy}</strong>{" "}
            <span style={{ color: "var(--muted)" }}>· {t.source}</span>
            <div>{t.detail}</div>
          </li>
        ))}
      </ul>

      {candidate.abstract && (
        <details style={{ marginTop: "0.6rem" }}>
          <summary style={{ cursor: "pointer", color: "var(--muted)" }}>Abstract</summary>
          <p style={{ marginTop: "0.4rem" }}>{candidate.abstract}</p>
        </details>
      )}

      {showActions && (
        <div className="discovery-actions">
          <button onClick={onApprove}>Approve & ingest</button>
          <button onClick={onReject}>Reject</button>
        </div>
      )}
      {candidate.reviewer && (
        <div style={{ marginTop: "0.5rem", color: "var(--muted)", fontSize: "0.8rem" }}>
          Reviewed by <strong>{candidate.reviewer}</strong>
          {candidate.review_notes ? ` — ${candidate.review_notes}` : ""}
        </div>
      )}
    </div>
  );
}
