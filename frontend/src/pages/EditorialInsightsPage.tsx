import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AnalysisScopePanel } from "@/components/AnalysisScopePanel";
import { FilterBar } from "@/components/FilterBar";
import { AnnualChart, TopicsChart } from "@/components/editorial/EditorialCharts";
import { annualPapers, rankedTopics } from "@/components/editorial/data";
import { getTimeline } from "@/lib/api";
import { USE_MOCK } from "@/lib/runtime";
import { resultForScope, type ScopedResult } from "@/lib/scopedResult";
import type { TimelinePayload } from "@/types";

export default function EditorialInsightsPage() {
  const [search] = useSearchParams();
  const scopeKey = search.toString();
  const [result, setResult] = useState<ScopedResult<[TimelinePayload, TimelinePayload]> | null>(null);
  const [failure, setFailure] = useState<ScopedResult<string> | null>(null);
  const [attempt, setAttempt] = useState(0);
  const payload = resultForScope(result, scopeKey);
  const error = resultForScope(failure, scopeKey);
  useEffect(() => {
    let cancelled = false;
    setFailure(null);
    setResult(null);
    Promise.all([
      getTimeline("label", new URLSearchParams(scopeKey), 100),
      getTimeline("topic", new URLSearchParams(scopeKey), 8),
    ]).then((next) => {
      if (!cancelled) setResult({ scopeKey, payload: next });
    }).catch((err: unknown) => {
      if (!cancelled) setFailure({ scopeKey, payload: err instanceof Error ? err.message : String(err) });
    });
    return () => { cancelled = true; };
  }, [scopeKey, attempt]);

  return <div>
    <FilterBar />
    <div className="page-heading-compact"><div><h1>Research, in perspective</h1>
      <p>Publication rhythms and research themes in the current selection.</p></div></div>
    {USE_MOCK && <p role="status">Development sample data — not corpus evidence.</p>}
    <p className="metric-note">Only papers with a publication year enter these charts. Topics can overlap: their counts must not be added together. Recent years may have incomplete coverage.</p>
    {error ? <div role="alert" className="empty">Could not load chart data: {error} <button onClick={() => setAttempt((n) => n + 1)}>Retry</button></div>
      : !payload ? <p role="status" className="empty">Loading the current selection…</p> : <>
        <div className="lf-grid-layout">
          <AnnualChart points={annualPapers(payload[0])} />
          <TopicsChart points={rankedTopics(payload[1])} />
        </div>
        <AnalysisScopePanel audit={payload[0].audit} title="Publication-year evidence scope" />
        <AnalysisScopePanel audit={payload[1].audit} title="Topic-ranking evidence scope" />
      </>}
    <p className="metric-note">Adapted from <a href="https://github.com/larashero3-dotcom/lieflat-charts" target="_blank" rel="noreferrer">Lieflat Charts</a> · <a href="/licenses/lieflat-charts.txt">PolyForm Noncommercial 1.0.0</a></p>
  </div>;
}
