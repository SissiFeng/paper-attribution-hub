import { useEffect, useState } from "react";
import { getOverview } from "@/lib/api";
import type { AnalyticsOverview } from "@/types";
import { AnimatedNumber } from "@/components/AnimatedNumber";
import css from "./StatsBar.module.css";

export function StatsBar() {
  const [data, setData] = useState<AnalyticsOverview | null>(null);

  useEffect(() => {
    getOverview().then(setData).catch(() => {});
  }, []);

  if (!data) return null;

  const core    = data.label_breakdown["CORE_RELEVANT"]    ?? 0;
  const related = data.label_breakdown["RELATED_RELEVANT"] ?? 0;
  const total   = data.total_papers;
  const pct     = total > 0 ? Math.round(((core + related) / total) * 100) : 0;
  const yearSpan = data.years.length > 0
    ? `${Math.min(...data.years)}–${Math.max(...data.years)}`
    : "—";

  const stats = [
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
  ] as const;

  return (
    <div className={css.bar}>
      {stats.map((s) => (
        <div key={s.label} className={`${css.card} ${css[s.accent]}`}>
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
        </div>
      ))}
    </div>
  );
}
