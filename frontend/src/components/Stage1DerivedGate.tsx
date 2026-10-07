import { useCallback, useEffect, useState } from "react";
import { Outlet } from "react-router-dom";

import { getStage1Readiness } from "@/lib/api";
import type { Stage1Readiness } from "@/types";
import { Stage1Unavailable } from "@/components/Stage1Unavailable";

export function Stage1DerivedGate() {
  const [readiness, setReadiness] = useState<Stage1Readiness | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setReadiness(await getStage1Readiness());
    } catch (caught) {
      setReadiness(null);
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) {
    return (
      <div className="v7-page">
        <div className="v7-card">
          <div className="v7-empty">
            Derived data is unavailable because Stage 1 provenance could not
            be verified. {error}
          </div>
        </div>
      </div>
    );
  }

  if (!readiness) {
    return <div className="empty">Verifying the Zotero Tier 1 corpus…</div>;
  }

  if (readiness.stage1_only && !readiness.derived_views_enabled) {
    return (
      <Stage1Unavailable
        title="Derived analysis unavailable"
        description="This view stays empty until every Tier 1 full text has been imported from the verified Zotero Markdown bucket and the controlled training and validation results have been explicitly promoted."
        readiness={readiness}
        loading={loading}
        onRefresh={() => void load()}
      />
    );
  }

  return <Outlet />;
}
