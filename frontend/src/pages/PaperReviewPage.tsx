import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { EvidencePanel } from "@/components/EvidencePanel";
import { FilterBar } from "@/components/FilterBar";
import { PaperTable } from "@/components/PaperTable";
import { listPapers } from "@/lib/api";
import { filterFromSearchParams } from "@/lib/filter";
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
  const [searchParams, setSearchParams] = useSearchParams();
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
      const params = new URLSearchParams(searchParams);
      params.set("limit", String(PAGE_SIZE));
      params.set("offset", String(offset));
      const fetched = await listPapers(params);
      setPapers(fetched);
      if (fetched.length > 0 && !fetched.some((p) => p.id === selectedId)) {
        setSelectedId(fetched[0].id);
      } else if (fetched.length === 0) {
        setSelectedId(null);
      }
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

      {selected && <EvidencePanel paper={selected} onReviewed={() => void load()} />}
    </div>
  );
}
