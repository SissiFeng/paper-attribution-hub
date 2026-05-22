import { lazy, Suspense, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

const PeopleGridPage = lazy(() => import("@/pages/PeopleGridPage"));
const MultiGraphPage = lazy(() => import("@/pages/MultiGraphPage"));
const GeographicPage = lazy(() => import("@/pages/GeographicPage"));
const SankeyPage = lazy(() => import("@/pages/SankeyPage"));
const NetworkPage = lazy(() => import("@/pages/NetworkPage"));
const TimelinePage = lazy(() => import("@/pages/TimelinePage"));
const DriftPage = lazy(() => import("@/pages/DriftPage"));
const ImpactPage = lazy(() => import("@/pages/ImpactPage"));

const TABS = [
  {
    key: "people",
    label: "People",
    icon: "🧪",
    desc: "Periodic table of AC members — symbol from surname, atomic number = paper count, color = top topic.",
    component: PeopleGridPage,
  },
  {
    key: "network",
    label: "Multi-Graph",
    icon: "🕸",
    desc: "Authors + institutions + papers + topics + ac_core in one force graph. Click any node to focus.",
    component: MultiGraphPage,
  },
  {
    key: "geographic",
    label: "Geographic",
    icon: "🌐",
    desc: "International collaboration network — partner countries highlighted, animated arcs for cross-border ties.",
    component: GeographicPage,
  },
  {
    key: "impact",
    label: "Impact",
    icon: "📈",
    desc: "YoY paper growth, citation impact, emerging collaborators, fastest-growing themes.",
    component: ImpactPage,
  },
  {
    key: "sankey",
    label: "Sankey",
    icon: "🌊",
    desc: "Institution → Topic → Classification flow.",
    component: SankeyPage,
  },
  {
    key: "timeline",
    label: "Timeline",
    icon: "⏱",
    desc: "Topic / label trend over years.",
    component: TimelinePage,
  },
  {
    key: "coauthors",
    label: "Co-authors",
    icon: "👥",
    desc: "Pure author-author co-authorship network.",
    component: NetworkPage,
  },
  {
    key: "drift",
    label: "Drift",
    icon: "🌀",
    desc: "Topic drift detection — when does the research mix shift?",
    component: DriftPage,
  },
] as const;

type TabKey = (typeof TABS)[number]["key"];

export default function InsightsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = (searchParams.get("tab") as TabKey | null) ?? "people";
  const [active, setActive] = useState<TabKey>(
    TABS.some((t) => t.key === initialTab) ? initialTab : "people"
  );

  useEffect(() => {
    const sp = new URLSearchParams(searchParams);
    sp.set("tab", active);
    setSearchParams(sp, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  const activeTab = TABS.find((t) => t.key === active)!;
  const Component = activeTab.component;

  return (
    <div className="v7-page">
      <div className="v7-hero">
        <div>
          <h1>Research Insights</h1>
          <p>
            Structured analytics across the AC-attributed corpus. Charts come
            from SQL aggregations; the evidence/RAG layer is reachable from
            each paper card.
          </p>
        </div>
      </div>

      <div className="v7-tabs" style={{ width: "auto" }}>
        {TABS.map((t) => (
          <button
            key={t.key}
            className={active === t.key ? "active" : ""}
            onClick={() => setActive(t.key)}
          >
            <span style={{ fontSize: "1rem" }}>{t.icon}</span>
            {t.label}
          </button>
        ))}
      </div>

      <div
        style={{
          color: "var(--muted)",
          fontSize: "0.86rem",
          marginTop: "-0.6rem",
        }}
      >
        {activeTab.desc}
      </div>

      <Suspense
        fallback={
          <div className="v7-card">
            <div className="v7-skel line medium" />
            <div className="v7-skel line short" />
            <div className="v7-skel card" style={{ height: 360, marginTop: 12 }} />
          </div>
        }
      >
        <Component />
      </Suspense>
    </div>
  );
}
