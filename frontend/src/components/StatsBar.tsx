import { useEffect, useState } from "react";
import { getOverview, getStage1Readiness } from "@/lib/api";
import type { AnalyticsOverview, Stage1Readiness } from "@/types";
import { AnimatedNumber } from "@/components/AnimatedNumber";
import { TiltCard } from "@/components/TiltCard";
import css from "./StatsBar.module.css";

export function StatsBar() {
  const [data, setData] = useState<AnalyticsOverview | null>(null);
  const [readiness, setReadiness] = useState<Stage1Readiness | null>(null);

  useEffect(() => {
    Promise.all([getOverview(), getStage1Readiness()])
      .then(([overview, stage1]) => {
        setData(overview);
        setReadiness(stage1);
      })
      .catch(() => {});
  }, []);

  if (!data) return null;

  const core    = data.label_breakdown["CORE_RELEVANT"]    ?? 0;
  const related = data.label_breakdown["RELATED_RELEVANT"] ?? 0;
  const total   = data.total_papers;
  const pct     = total > 0 ? Math.round(((core + related) / total) * 100) : 0;
  const yearSpan = data.years.length > 0
    ? `${Math.min(...data.years)}–${Math.max(...data.years)}`
    : "—";

  const stats = readiness?.stage1_only ? [
    {
      label: "Tier 1 Papers",
      value: total,
      accent: "navy",
      badge: { text: "ZOTERO", cls: "core" },
      delay: 0,
    },
    {
      label: "SDL Field Relevant",
      value: data.label_breakdown["SDL_FIELD_RELEVANT"] ?? 0,
      accent: "steel",
      badge: { text: "PILOT", cls: "core" },
      delay: 120,
    },
    {
      label: "Adjacent",
      value: data.label_breakdown["ADJACENT"] ?? 0,
      accent: "pink",
      badge: { text: "REVIEW", cls: "related" },
      delay: 240,
    },
    {
      label: "Full-text Coverage",
      value: readiness.metadata_papers > 0
        ? Math.round(
            (readiness.fulltexts_imported / readiness.metadata_papers) * 100,
          )
        : 0,
      suffix: "%",
      accent: "green",
      badge: { text: yearSpan, cls: "years" },
      delay: 360,
    },
  ] : [
    {
      label: "Total Papers",
      value: total,
      accent: "navy",
      badge: { text: "corpus", cls: "core" },
      delay: 0,
    },
    {
      label: "Core Relevant",
      value: core,
      accent: "steel",
      badge: { text: "CORE", cls: "core" },
      delay: 120,
    },
    {
      label: "Related Relevant",
      value: related,
      accent: "pink",
      badge: { text: "RELATED", cls: "related" },
      delay: 240,
    },
    {
      label: "AC Coverage",
      value: pct,
      suffix: "%",
      accent: "green",
      badge: { text: yearSpan, cls: "years" },
      delay: 360,
    },
  ];

  return (
    <div className={css.bar}>
      {stats.map((s) => (
        <TiltCard key={s.label} className={`${css.card} ${css[s.accent]}`}>
          <div className={css.label}>{s.label}</div>
          <div className={css.value}>
            <AnimatedNumber
              value={s.value}
              suffix={"suffix" in s ? s.suffix : ""}
              duration={1200}
              delay={s.delay}
            />
          </div>
          <div>
            <span className={`${css.badge} ${css[s.badge.cls]}`}>
              {s.badge.text}
            </span>
          </div>
        </TiltCard>
      ))}
    </div>
  );
}
