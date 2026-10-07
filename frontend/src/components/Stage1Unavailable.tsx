import type { Stage1Readiness } from "@/types";

interface Stage1UnavailableProps {
  title: string;
  description: string;
  statusTitle?: string;
  statusDescription?: string;
  readiness: Stage1Readiness;
  loading: boolean;
  onRefresh: () => void;
}

export function Stage1Unavailable({
  title,
  description,
  statusTitle,
  statusDescription,
  readiness,
  loading,
  onRefresh,
}: Stage1UnavailableProps) {
  return (
    <div className="v7-page">
      <div className="v7-hero">
        <div>
          <h1>{title}</h1>
          <p>{description}</p>
        </div>
        <div className="v7-hero-actions">
          <button className="v7-btn" onClick={onRefresh} disabled={loading}>
            ↻ {loading ? "Loading…" : "Refresh"}
          </button>
        </div>
      </div>

      <div className="v7-card">
        <div className="v7-empty">
          <span className="icon">⏳</span>
          <div>{statusTitle ?? "Tier 1 data is still being prepared."}</div>
          <div style={{ marginTop: 8, fontSize: 13, maxWidth: 720 }}>
            {statusDescription ?? (
              <>
                {readiness.fulltexts_imported} of {readiness.metadata_papers}
                PDF-backed Tier 1 papers have verified Zotero Markdown imported
                from S3 into the backend. No legacy, mock, AC-member, or partial
                classification data is displayed here. This view will remain
                unavailable until full-text acquisition, training, and validation
                are complete and the results are explicitly promoted.
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
