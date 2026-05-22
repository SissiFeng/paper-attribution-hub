import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { EvidencePanel } from "@/components/EvidencePanel";
import { FilterBar } from "@/components/FilterBar";
import { PaperTable } from "@/components/PaperTable";
import { listPapers } from "@/lib/api";
import type { Paper } from "@/types";

export default function PaperReviewPage() {
  const [searchParams] = useSearchParams();
  const [papers, setPapers] = useState<Paper[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const fetched = await listPapers(searchParams);
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
  }, [searchParams.toString()]);

  useEffect(() => {
    void load();
  }, [load]);

  const selected = useMemo(
    () => papers.find((p) => p.id === selectedId) ?? null,
    [papers, selectedId]
  );

  return (
    <div>
      <FilterBar />
      <div style={{ margin: "0.4rem 0 1rem", color: "var(--muted)" }}>
        {loading ? "Loading…" : `${papers.length} papers`}
      </div>

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

      {selected && <EvidencePanel paper={selected} onReviewed={() => void load()} />}
    </div>
  );
}
