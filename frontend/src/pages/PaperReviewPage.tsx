import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { EvidencePanel } from "@/components/EvidencePanel";
import { FilterBar } from "@/components/FilterBar";
import { PaperTable } from "@/components/PaperTable";
import { listPapers } from "@/lib/api";
import { filterFromSearchParams, filterToSearchParams } from "@/lib/filter";
import type { Paper } from "@/types";

const LABEL_COLORS: Record<string, string> = {
  CORE_RELEVANT: "#34d399",
  RELATED_RELEVANT: "#6594B1",
  SDL_FIELD_RELEVANT: "#a78bfa",
  ADJACENT: "#f59e0b",
  UNCERTAIN: "#fb923c",
  EXCLUDE: "#9aa3b2",
};

export default function PaperReviewPage() {
  const [searchParams] = useSearchParams();
  const [papers, setPapers] = useState<Paper[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [offset, setOffset] = useState(0);
  const PAGE_SIZE = 50;

  const filter = filterFromSearchParams(searchParams);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Apply filterFromSearchParams so DEFAULT_FILTER.labels are included
      // even when the URL has no ?labels= params (fresh page load).
      const filter = filterFromSearchParams(searchParams);
      const params = filterToSearchParams(filter);
      params.set("limit", String(PAGE_SIZE));
      params.set("offset", String(offset));
      const fetched = await listPapers(params);
      setPapers(fetched);
      // Do NOT auto-select — drawer only opens when user explicitly clicks a row
      setSelectedId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams.toString(), offset]);

  useEffect(() => {
    setOffset(0); // reset page when filter changes
  }, [searchParams.toString()]);

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

  return (
    <div>
      {/* Hero */}
      <div className="v7-hero" style={{ marginBottom: "1rem" }}>
        <div>
          <h1>Papers</h1>
          <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
            {isDefaultView
              ? "Showing AC-attributed papers (CORE + RELATED). Use label filters below to explore other categories."
              : `Filtered by: ${activeLabels.length === 0 ? "all labels" : activeLabels.map(l => l.replace(/_/g, " ")).join(", ")}`}
          </p>
        </div>
      </div>

      <FilterBar />

      {/* Stats row */}
      {papers.length > 0 && (
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

      {error && (
        <div style={{ color: "var(--uncertain)", marginBottom: "1rem" }}>
          Backend error: {error}.
        </div>
      )}

      <PaperTable
        papers={papers}
        selectedId={selectedId}
        onSelect={(p) => setSelectedId(p.id)}
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
              width: "min(52vw, 780px)",
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
              <EvidencePanel paper={selected} onReviewed={() => void load()} />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
