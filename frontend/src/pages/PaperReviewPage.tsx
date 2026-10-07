import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { EvidencePanel } from "@/components/EvidencePanel";
import { FilterBar } from "@/components/FilterBar";
import { PaperTable } from "@/components/PaperTable";
import { getStage1Readiness, listPapers, listPublicPapers } from "@/lib/api";
import { filterFromSearchParams, filterToSearchParams } from "@/lib/filter";
import {
  isLatestRequest,
  resultForScope,
  type ScopedResult,
} from "@/lib/scopedResult";
import type { Paper, Stage1Readiness } from "@/types";

const LABEL_COLORS: Record<string, string> = {
  CORE_RELEVANT: "#34d399",
  RELATED_RELEVANT: "#6594B1",
  SDL_FIELD_RELEVANT: "#a78bfa",
  ADJACENT: "#f59e0b",
  UNCERTAIN: "#fb923c",
  EXCLUDE: "#9aa3b2",
};

export default function PaperReviewPage({ readOnly = false }: { readOnly?: boolean }) {
  const [searchParams] = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [readiness, setReadiness] = useState<Stage1Readiness | null>(null);
  const [offset, setOffset] = useState(0);
  const PAGE_SIZE = 50;
  const searchKey = searchParams.toString();
  const scopeKey = JSON.stringify([searchKey, offset, PAGE_SIZE]);
  const [papersResult, setPapersResult] = useState<
    ScopedResult<Paper[]> | null
  >(null);
  const papers = resultForScope(papersResult, scopeKey) ?? [];
  const requestGeneration = useRef(0);

  const filter = filterFromSearchParams(searchParams);

  const load = useCallback(async () => {
    const generation = ++requestGeneration.current;
    setLoading(true);
    setError(null);
    try {
      const stage1 = readOnly ? null : await getStage1Readiness();
      setReadiness(stage1);
      // Apply filterFromSearchParams so DEFAULT_FILTER.labels are included
      // even when the URL has no ?labels= params (fresh page load).
      const requestFilter = filterFromSearchParams(new URLSearchParams(searchKey));
      if (stage1?.stage1_only && !stage1.derived_views_enabled) {
        requestFilter.labels = [];
        requestFilter.institutionIds = [];
        requestFilter.topicIds = [];
        requestFilter.fields = [];
        requestFilter.countries = [];
        requestFilter.corpusSources = ["STRICT_SDL_KEYWORD"];
        requestFilter.sdlJudgements = [];
        requestFilter.acRelevanceJudgements = [];
        requestFilter.aiForScienceJudgements = [];
        requestFilter.reviewStatuses = [];
        requestFilter.partnerOnly = false;
        requestFilter.acAuthorOnly = false;
        requestFilter.hasReview = undefined;
        requestFilter.minConfidence = undefined;
        requestFilter.maxConfidence = undefined;
      }
      const params = filterToSearchParams(requestFilter);
      params.set("limit", String(PAGE_SIZE));
      params.set("offset", String(offset));
      const fetched = await (readOnly ? listPublicPapers : listPapers)(params);
      if (isLatestRequest(generation, requestGeneration.current)) {
        setPapersResult({ scopeKey, payload: fetched });
        // Do NOT auto-select — drawer only opens when user explicitly clicks a row
        setSelectedId(null);
      }
    } catch (err) {
      if (isLatestRequest(generation, requestGeneration.current)) {
        setError(err instanceof Error ? err.message : String(err));
        setPapersResult(null);
      }
    } finally {
      if (isLatestRequest(generation, requestGeneration.current)) setLoading(false);
    }
  }, [offset, scopeKey, searchKey, readOnly]);

  useEffect(() => {
    setOffset(0); // reset page when filter changes
  }, [searchKey]);

  useEffect(() => {
    void load();
  }, [load]);

  const selected = useMemo(
    () => papers.find((p) => p.id === selectedId) ?? null,
    [papers, selectedId]
  );

  // Label distribution in current page
  const labelCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const p of papers) {
      const label = p.classification?.label ?? "unclassified";
      counts[label] = (counts[label] ?? 0) + 1;
    }
    return counts;
  }, [papers]);

  const activeLabels = filter.labels;
  const isDefaultView = activeLabels.includes("CORE_RELEVANT") && activeLabels.includes("RELATED_RELEVANT") && activeLabels.length === 2;
  const acquiringTier1 = Boolean(
    readiness?.stage1_only && !readiness.derived_views_enabled,
  );

  return (
    <div>
      {/* Hero */}
      <div className="v7-hero" style={{ marginBottom: "1rem" }}>
        <div>
          <h1>Papers</h1>
          <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
            {readOnly ? 'Browse publications, classification evidence and Wiki. Open a paper for reading and personal research.' : acquiringTier1
              ? `Authoritative Zotero SDL Tier 1 papers with PDF attachments only. ${readiness?.fulltexts_imported ?? 0} of ${readiness?.metadata_papers ?? 0} papers currently have verified Markdown imported from S3.`
              : isDefaultView
              ? "Showing AC-attributed papers (CORE + RELATED). Use label filters below to explore other categories."
              : `Filtered by: ${activeLabels.length === 0 ? "all labels" : activeLabels.map(l => l.replace(/_/g, " ")).join(", ")}`}
          </p>
        </div>
      </div>

      {!acquiringTier1 && <FilterBar readOnly={readOnly} />}

      {/* Stats row */}
      {papers.length > 0 && !acquiringTier1 && (
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", margin: "0.5rem 0 1rem", fontSize: "0.8rem" }}>
          {Object.entries(labelCounts).map(([label, count]) => (
            <span key={label} style={{
              display: "inline-flex", alignItems: "center", gap: 5,
              padding: "2px 10px", borderRadius: 20,
              background: `${LABEL_COLORS[label] ?? "#9aa3b2"}22`,
              border: `1px solid ${LABEL_COLORS[label] ?? "#9aa3b2"}55`,
              color: LABEL_COLORS[label] ?? "var(--muted)",
              fontFamily: "'JetBrains Mono', monospace",
            }}>
              <span style={{ fontWeight: 700 }}>{count}</span>
              {label.replace(/_/g, " ")}
            </span>
          ))}
          {loading && <span style={{ color: "var(--muted)" }}>Loading…</span>}
        </div>
      )}

      {papers.length > 0 && acquiringTier1 && (
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", margin: "0.5rem 0 1rem", fontSize: "0.8rem" }}>
          <span className="status-chip success">Zotero Tier 1 only</span>
          <span className="status-chip">{readiness?.metadata_papers ?? 0} PDF-backed papers</span>
          <span className="status-chip">{readiness?.fulltexts_imported ?? 0} S3 Markdown imports</span>
          {loading && <span style={{ color: "var(--muted)" }}>Loading…</span>}
        </div>
      )}

      {error && (
        <div style={{ color: "var(--uncertain)", marginBottom: "1rem" }}>
          Backend error: {error}.
        </div>
      )}

      {loading && papers.length === 0 && <div className="empty">Loading papers…</div>}

      <PaperTable
        papers={papers}
        selectedId={selectedId}
        onSelect={(p) => setSelectedId(p.id)}
        metadataOnly={acquiringTier1}
        readOnly={readOnly}
      />

      {/* Pagination */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: "1rem", fontSize: "0.85rem", color: "var(--muted)" }}>
        <button
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          style={{ opacity: offset === 0 ? 0.4 : 1 }}
        >
          ← Prev
        </button>
        <span>
          {offset + 1}–{offset + papers.length}
          {papers.length === PAGE_SIZE ? "+" : ""}
        </span>
        <button
          disabled={papers.length < PAGE_SIZE}
          onClick={() => setOffset(offset + PAGE_SIZE)}
          style={{ opacity: papers.length < PAGE_SIZE ? 0.4 : 1 }}
        >
          Next →
        </button>
      </div>

      {/* Right-side drawer */}
      {selected && (
        <>
          {/* Backdrop — click to close */}
          <div
            onClick={() => setSelectedId(null)}
            style={{
              position: "fixed",
              inset: 0,
              zIndex: 200,
              background: "rgba(15,17,21,0.35)",
              backdropFilter: "blur(2px)",
            }}
          />

          {/* Panel */}
          <div
            style={{
              position: "fixed",
              top: 0,
              right: 0,
              bottom: 0,
              width: "min(100vw, max(52vw, 560px), 780px)",
              zIndex: 201,
              background: "var(--surface, #fff)",
              borderLeft: "1px solid var(--border, #d1dce8)",
              boxShadow: "-8px 0 32px rgba(0,0,0,0.12)",
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
            }}
          >
            {/* Drawer header */}
            <div style={{
              display: "flex",
              alignItems: "flex-start",
              justifyContent: "space-between",
              padding: "16px 20px 12px",
              borderBottom: "1px solid var(--border, #d1dce8)",
              flexShrink: 0,
              gap: 12,
            }}>
              <div style={{ minWidth: 0 }}>
                <div style={{
                  fontWeight: 600,
                  fontSize: "0.95rem",
                  color: "var(--text)",
                  lineHeight: 1.35,
                  marginBottom: 4,
                  overflow: "hidden",
                  display: "-webkit-box",
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: "vertical",
                }}>
                  {selected.title}
                </div>
                <div style={{ fontSize: "0.78rem", color: "var(--muted)" }}>
                  {selected.year}
                  {selected.venue ? ` · ${selected.venue}` : ""}
                  {selected.doi ? (
                    <> · <a
                      href={`https://doi.org/${selected.doi}`}
                      target="_blank"
                      rel="noreferrer"
                      style={{ color: "var(--muted)", textDecoration: "underline" }}
                    >{selected.doi}</a></>
                  ) : null}
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
                <Link to={`/papers/${encodeURIComponent(selected.id)}`}>Open paper</Link>
                {!readOnly && !acquiringTier1 && (
                  <Link
                    to={`/papers/${encodeURIComponent(selected.id)}/evidence-map`}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      minHeight: 28,
                      padding: "4px 9px",
                      border: "1px solid var(--border, #d1dce8)",
                      borderRadius: 6,
                      background: "var(--accent-bg)",
                      color: "var(--text)",
                      fontSize: 10,
                      fontWeight: 600,
                      whiteSpace: "nowrap",
                    }}
                  >
                    Evidence map ↗
                  </Link>
                )}
                <button
                  onClick={() => setSelectedId(null)}
                  title="Close"
                  style={{
                    flexShrink: 0,
                    width: 28, height: 28,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    border: "1px solid var(--border, #d1dce8)",
                    borderRadius: 6,
                    background: "transparent",
                    cursor: "pointer",
                    fontSize: 16,
                    color: "var(--muted)",
                    lineHeight: 1,
                  }}
                >
                  ✕
                </button>
              </div>
            </div>

            {/* Scrollable body */}
            <div style={{ flex: 1, overflowY: "auto", padding: "0 20px 24px" }}>
              {acquiringTier1 ? (
                <div className="v7-card" style={{ marginTop: 20 }}>
                  <div className="review-kicker">Verified source</div>
                  <h3>Zotero SDL Tier 1</h3>
                  <p style={{ color: "var(--muted)" }}>
                    {selected.full_text_available
                      ? "The paper's Markdown has been imported from the verified Zotero S3 path."
                      : "PDF-backed Zotero papers are loaded; Markdown import is still pending."}
                  </p>
                  <dl>
                    <dt>Authors</dt>
                    <dd>{selected.authors.map((author) => author.name).join(", ") || "—"}</dd>
                    <dt>DOI</dt>
                    <dd>{selected.doi || "—"}</dd>
                    <dt>Corpus source</dt>
                    <dd>{selected.corpus_sources?.join(", ") || "—"}</dd>
                  </dl>
                  {selected.abstract && (
                    <>
                      <div className="review-kicker" style={{ marginTop: 20 }}>Abstract</div>
                      <p>{selected.abstract}</p>
                    </>
                  )}
                </div>
              ) : (
                <EvidencePanel key={selected.id} paper={selected} readOnly={readOnly} onReviewed={() => void load()} />
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
