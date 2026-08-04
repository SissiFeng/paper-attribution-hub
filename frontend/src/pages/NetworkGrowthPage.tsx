import { useCallback, useEffect, useMemo, useState } from "react";
import { EChart } from "@/components/EChart";
import { institutionTopicHeatmapTooltip } from "@/lib/chartTooltips";
import { TimeSlider } from "@/components/TimeSlider";
import {
  getNetworkGrowth,
  getTopicStream,
  getInstTopicHeatmap,
  getHubScore,
} from "@/lib/api";
import type {
  NetworkGrowthPayload,
  TopicStreamPayload,
  InstTopicHeatmapPayload,
  HubScorePayload,
  GrowthPoint,
} from "@/types";

// ── Palette ───────────────────────────────────────────────────────────────────
const PALETTE = {
  navy:     "#213C51",
  steel:    "#6594B1",
  pink:     "#DDAED3",
  green:    "#22c55e",
  amber:    "#f59e0b",
  pinkDim:  "rgba(221,174,211,0.18)",
  steelDim: "rgba(101,148,177,0.12)",
};

const GROWTH_SERIES = [
  { key: "papers",        label: "Papers",        color: PALETTE.pink  },
  { key: "authors",       label: "Authors",       color: PALETTE.steel },
  { key: "institutions",  label: "Institutions",  color: PALETTE.navy  },
  { key: "countries",     label: "Countries",     color: PALETTE.green },
  { key: "collaborations",label: "Collaborations",color: PALETTE.amber },
] as const;

const TOPIC_COLORS = [
  PALETTE.navy,
  PALETTE.steel,
  PALETTE.pink,
  PALETTE.green,
  PALETTE.amber,
];

type GrowthMode = "cumulative" | "yearly" | "growth_rate";
type ActiveTab = "growth" | "topics" | "heatmap" | "hub";

const BASE_ECHARTS_STYLE: React.CSSProperties = {
  height: "100%",
  width: "100%",
};

// ── Chart option builders ─────────────────────────────────────────────────────

function buildGrowthOption(
  data: NetworkGrowthPayload,
  mode: GrowthMode,
  activeLines: Set<string>
) {
  const rows = mode === "cumulative" ? data.cumulative : data.yearly;
  const years = rows.map((r) => String(r.year));

  const pct = (curr: number, prev: number) =>
    prev === 0 ? 0 : Math.round(((curr - prev) / prev) * 100);

  const series = GROWTH_SERIES.filter((s) => activeLines.has(s.key)).map((s) => {
    const rawVals = rows.map((r) => r[s.key as keyof GrowthPoint] as number);
    const vals =
      mode === "growth_rate"
        ? rawVals.map((v, i) => (i === 0 ? 0 : pct(v, rawVals[i - 1])))
        : rawVals;

    return {
      name: s.label,
      type: "line" as const,
      smooth: true,
      data: vals,
      lineStyle: { color: s.color, width: 2.5 },
      itemStyle: { color: s.color },
      areaStyle: {
        color: {
          type: "linear",
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: s.color + "28" },
            { offset: 1, color: s.color + "00" },
          ],
        },
      },
      symbol: "circle",
      symbolSize: 5,
      emphasis: { scale: 1.6 },
    };
  });

  return {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross", lineStyle: { color: PALETTE.steelDim } },
      backgroundColor: "#fff",
      borderColor: "rgba(33,60,81,0.12)",
      textStyle: { color: PALETTE.navy, fontFamily: "'JetBrains Mono',monospace", fontSize: 12 },
      formatter: (params: unknown[]) => {
        const p = params as Array<{ seriesName: string; value: number; color: string }>;
        const year = rows[0]?.year != null ? years[0] : "";
        const header = `<div style="font-weight:600;margin-bottom:6px;color:${PALETTE.navy}">${(params as unknown[])[0] ? (params as {axisValueLabel?: string}[])[0]?.axisValueLabel ?? year : year}</div>`;
        const rows2 = p.map(
          (item) =>
            `<div style="display:flex;justify-content:space-between;gap:16px">
               <span><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${item.color};margin-right:5px"></span>${item.seriesName}</span>
               <b>${mode === "growth_rate" ? item.value + "%" : item.value.toLocaleString()}</b>
             </div>`
        );
        return `<div style="font-family:'JetBrains Mono',monospace;font-size:12px;padding:4px">${header}${rows2.join("")}</div>`;
      },
    },
    legend: {
      top: 0,
      right: 0,
      textStyle: { color: PALETTE.navy, fontFamily: "'JetBrains Mono',monospace", fontSize: 11 },
      inactiveColor: "#ccc",
    },
    grid: { top: 44, right: 20, bottom: 32, left: 50, containLabel: false },
    xAxis: {
      type: "category",
      data: years,
      axisLine: { lineStyle: { color: "rgba(33,60,81,0.12)" } },
      axisTick: { show: false },
      axisLabel: { color: PALETTE.steel, fontFamily: "'JetBrains Mono',monospace", fontSize: 11 },
    },
    yAxis: {
      type: "value",
      splitLine: { lineStyle: { color: "rgba(33,60,81,0.06)", type: "dashed" } },
      axisLabel: {
        color: PALETTE.steel,
        fontFamily: "'JetBrains Mono',monospace",
        fontSize: 11,
        formatter: (v: number) =>
          mode === "growth_rate" ? `${v}%` : v >= 1000 ? `${v / 1000}k` : String(v),
      },
    },
    series,
  };
}

function buildStreamOption(data: TopicStreamPayload) {
  return {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line" },
      backgroundColor: "#fff",
      borderColor: "rgba(33,60,81,0.12)",
      textStyle: { color: PALETTE.navy, fontFamily: "'JetBrains Mono',monospace", fontSize: 12 },
    },
    color: TOPIC_COLORS,
    legend: {
      data: data.topics,
      bottom: 4,
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { color: PALETTE.steel, fontFamily: "'JetBrains Mono',monospace", fontSize: 10 },
    },
    grid: { top: 20, right: 20, bottom: 52, left: 20 },
    xAxis: {
      type: "time",
      axisLine: { lineStyle: { color: "rgba(33,60,81,0.12)" } },
      axisTick: { show: false },
      axisLabel: {
        color: PALETTE.steel,
        fontFamily: "'JetBrains Mono',monospace",
        fontSize: 11,
        formatter: (v: number) => String(new Date(v).getFullYear()),
      },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      show: false,
    },
    singleAxis: {
      top: 50,
      bottom: 50,
      axisTick: {},
      axisLabel: {},
      type: "time",
      axisPointer: { animation: true, label: { show: true } },
      splitLine: { show: true, lineStyle: { type: "dashed", opacity: 0.2 } },
    },
    series: [
      {
        type: "themeRiver",
        data: data.data,
        label: { show: false },
        emphasis: {
          focus: "series",
          itemStyle: { opacity: 0.85 },
        },
      },
    ],
  };
}

function buildHeatmapOption(data: InstTopicHeatmapPayload) {
  const { institutions, topics, cells } = data;
  const maxVal = Math.max(...cells.map((c) => c.count));

  const chartData = cells.map((c) => [
    topics.indexOf(c.topic),
    institutions.indexOf(c.institution),
    c.count,
  ]);

  return {
    backgroundColor: "transparent",
    tooltip: {
      position: "top",
      backgroundColor: "#fff",
      borderColor: "rgba(33,60,81,0.12)",
      textStyle: { color: PALETTE.navy, fontFamily: "'JetBrains Mono',monospace", fontSize: 12 },
      formatter: (p: unknown) => {
        const { value } = p as { value: [number, number, number]; name: string };
        return institutionTopicHeatmapTooltip(
          institutions[value[1]],
          topics[value[0]],
          value[2],
        );
      },
    },
    grid: { top: 20, right: 10, bottom: 80, left: 120, containLabel: false },
    xAxis: {
      type: "category",
      data: topics,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: PALETTE.navy,
        fontFamily: "'JetBrains Mono',monospace",
        fontSize: 10.5,
        rotate: 20,
        interval: 0,
      },
      splitArea: { show: false },
    },
    yAxis: {
      type: "category",
      data: institutions,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: PALETTE.navy, fontFamily: "'JetBrains Mono',monospace", fontSize: 11 },
      splitArea: { show: true, areaStyle: { color: ["rgba(248,250,252,0.6)", "rgba(241,244,248,0.6)"] } },
    },
    visualMap: {
      min: 0,
      max: maxVal,
      calculable: true,
      orient: "horizontal",
      left: "center",
      bottom: 0,
      textStyle: { color: PALETTE.navy, fontFamily: "'JetBrains Mono',monospace", fontSize: 10 },
      inRange: {
        color: [
          "rgba(248,250,252,0.4)",
          PALETTE.pinkDim.replace("0.18","0.5"),
          PALETTE.pink,
          "#a86899",
          PALETTE.navy,
        ],
      },
      itemWidth: 16,
      itemHeight: 120,
    },
    series: [
      {
        type: "heatmap",
        data: chartData,
        label: {
          show: true,
          fontFamily: "'JetBrains Mono',monospace",
          fontSize: 11,
          fontWeight: 600,
          color: (p: unknown) => ((p as {value:[number,number,number]}).value[2] > maxVal * 0.55 ? "#fff" : PALETTE.navy),
        },
        emphasis: { scale: true, itemStyle: { shadowBlur: 10, shadowColor: "rgba(33,60,81,0.2)" } },
      },
    ],
  };
}

function buildHubOption(data: HubScorePayload) {
  const years = data.data.map((d) => String(d.year));
  return {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      backgroundColor: "#fff",
      borderColor: "rgba(33,60,81,0.12)",
      textStyle: { color: PALETTE.navy, fontFamily: "'JetBrains Mono',monospace", fontSize: 12 },
    },
    legend: {
      top: 0,
      right: 0,
      textStyle: { color: PALETTE.navy, fontFamily: "'JetBrains Mono',monospace", fontSize: 11 },
    },
    grid: { top: 44, right: 20, bottom: 32, left: 50, containLabel: false },
    xAxis: {
      type: "category",
      data: years,
      axisLine: { lineStyle: { color: "rgba(33,60,81,0.12)" } },
      axisTick: { show: false },
      axisLabel: { color: PALETTE.steel, fontFamily: "'JetBrains Mono',monospace", fontSize: 11 },
    },
    yAxis: [
      {
        type: "value",
        name: "Count",
        nameTextStyle: { color: PALETTE.steel, fontSize: 10, fontFamily: "'JetBrains Mono',monospace" },
        splitLine: { lineStyle: { color: "rgba(33,60,81,0.06)", type: "dashed" } },
        axisLabel: { color: PALETTE.steel, fontFamily: "'JetBrains Mono',monospace", fontSize: 11 },
      },
      {
        type: "value",
        name: "Hub Score",
        min: 0,
        max: 1,
        nameTextStyle: { color: PALETTE.pink, fontSize: 10, fontFamily: "'JetBrains Mono',monospace" },
        axisLabel: {
          color: PALETTE.pink,
          fontFamily: "'JetBrains Mono',monospace",
          fontSize: 11,
          formatter: (v: number) => v.toFixed(1),
        },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: "Partner Institutions",
        type: "bar",
        barMaxWidth: 32,
        data: data.data.map((d) => d.partner_count),
        itemStyle: { color: PALETTE.steelDim.replace("0.12", "0.55"), borderRadius: [3, 3, 0, 0] },
        emphasis: { itemStyle: { color: PALETTE.steel } },
      },
      {
        name: "Intl. Collaborations",
        type: "bar",
        barMaxWidth: 32,
        data: data.data.map((d) => d.intl_collab_count),
        itemStyle: { color: PALETTE.pinkDim.replace("0.18", "0.55"), borderRadius: [3, 3, 0, 0] },
        emphasis: { itemStyle: { color: PALETTE.pink } },
      },
      {
        name: "Hub Score",
        type: "line",
        yAxisIndex: 1,
        smooth: true,
        data: data.data.map((d) => d.hub_score),
        lineStyle: { color: PALETTE.pink, width: 3 },
        itemStyle: { color: PALETTE.pink, borderWidth: 2 },
        symbol: "circle",
        symbolSize: 8,
        areaStyle: {
          color: {
            type: "linear", x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: PALETTE.pink + "30" },
              { offset: 1, color: PALETTE.pink + "00" },
            ],
          },
        },
        label: {
          show: true,
          position: "top",
          formatter: ({ value }: { value: number }) => value.toFixed(2),
          color: PALETTE.pink,
          fontFamily: "'JetBrains Mono',monospace",
          fontSize: 11,
          fontWeight: 600,
        },
      },
    ],
  };
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function NetworkGrowthPage() {
  const currentYear = new Date().getFullYear();
  const [yearFrom, setYearFrom] = useState(2021);
  const [yearTo,   setYearTo]   = useState(currentYear);
  const [activeTab, setActiveTab] = useState<ActiveTab>("growth");
  const [growthMode, setGrowthMode] = useState<GrowthMode>("cumulative");
  const [activeLines, setActiveLines] = useState<Set<string>>(
    new Set(GROWTH_SERIES.map((s) => s.key))
  );

  const [growth,  setGrowth]  = useState<NetworkGrowthPayload | null>(null);
  const [stream,  setStream]  = useState<TopicStreamPayload | null>(null);
  const [heatmap, setHeatmap] = useState<InstTopicHeatmapPayload | null>(null);
  const [hub,     setHub]     = useState<HubScorePayload | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [g, s, h, hs] = await Promise.all([
        getNetworkGrowth({ year_from: yearFrom, year_to: yearTo }),
        getTopicStream({ year_from: yearFrom, year_to: yearTo }),
        getInstTopicHeatmap({}),
        getHubScore("uoft"),
      ]);
      setGrowth(g);
      setStream(s);
      setHeatmap(h);
      setHub(hs);
    } finally {
      setLoading(false);
    }
  }, [yearFrom, yearTo]);

  useEffect(() => { void load(); }, [load]);

  // Filter growth data by year range
  const filteredGrowth = useMemo((): NetworkGrowthPayload | null => {
    if (!growth) return null;
    return {
      yearly:     growth.yearly.filter((r) => r.year >= yearFrom && r.year <= yearTo),
      cumulative: growth.cumulative.filter((r) => r.year >= yearFrom && r.year <= yearTo),
    };
  }, [growth, yearFrom, yearTo]);

  const latestCumulative = useMemo(() => {
    if (!filteredGrowth || filteredGrowth.cumulative.length === 0) return null;
    return filteredGrowth.cumulative[filteredGrowth.cumulative.length - 1];
  }, [filteredGrowth]);

  const latestHub = useMemo(() => {
    if (!hub) return null;
    const filtered = hub.data.filter((d) => d.year <= yearTo);
    return filtered[filtered.length - 1] ?? null;
  }, [hub, yearTo]);

  const sliderBounds = useMemo(() => {
    const years = [
      ...(growth?.yearly.map((r) => r.year) ?? []),
      yearFrom,
      yearTo,
    ];
    return {
      min: Math.min(...years),
      max: Math.max(...years, currentYear),
    };
  }, [growth, yearFrom, yearTo, currentYear]);

  const growthOption  = useMemo(() => filteredGrowth ? buildGrowthOption(filteredGrowth, growthMode, activeLines) : null, [filteredGrowth, growthMode, activeLines]);
  const streamOption  = useMemo(() => stream  ? buildStreamOption(stream)  : null, [stream]);
  const heatmapOption = useMemo(() => heatmap ? buildHeatmapOption(heatmap) : null, [heatmap]);
  const hubOption     = useMemo(() => hub     ? buildHubOption(hub)         : null, [hub]);

  const toggleLine = (key: string) => {
    setActiveLines((prev) => {
      const next = new Set(prev);
      if (next.has(key) && next.size > 1) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const TABS: { key: ActiveTab; label: string }[] = [
    { key: "growth",  label: "Cumulative Growth" },
    { key: "topics",  label: "Topic Streamgraph" },
    { key: "heatmap", label: "Institution × Topic" },
    { key: "hub",     label: "UofT Hub Score" },
  ];

  return (
    <div className="v7-page">
      {/* ── Hero ─────────────────────────────────────────────────── */}
      <div className="v7-hero">
        <div>
          <h1>Research Network Growth</h1>
          <p>
            How the SDL research network expands over time — growth curves, topic streams,
            institution-topic coverage, and UofT's emerging hub position.
          </p>
        </div>
        <div className="v7-hero-actions">
          <button className="v7-btn" onClick={() => void load()} disabled={loading}>
            ↻ Refresh
          </button>
        </div>
      </div>

      {/* ── Year slider ──────────────────────────────────────────── */}
      <TimeSlider
        minYear={sliderBounds.min} maxYear={sliderBounds.max}
        yearFrom={yearFrom} yearTo={yearTo}
        onChange={(yf, yt) => { setYearFrom(yf); setYearTo(yt); }}
      />

      {/* ── KPI cards ────────────────────────────────────────────── */}
      <div className="v7-stat-grid">
        <div className="v7-stat">
          <div className="label">AC-Relevant Papers</div>
          <div className="value">{latestCumulative?.papers ?? "—"}</div>
          <div className="delta">{yearFrom}–{yearTo} cumulative</div>
        </div>
        <div className="v7-stat">
          <div className="label">Active Authors</div>
          <div className="value">{latestCumulative?.authors ?? "—"}</div>
          <div className="delta">unique contributors</div>
        </div>
        <div className="v7-stat">
          <div className="label">Partner Institutions</div>
          <div className="value">{latestCumulative?.institutions ?? "—"}</div>
          <div className="delta">organizations</div>
        </div>
        <div className="v7-stat">
          <div className="label">Countries</div>
          <div className="value">{latestCumulative?.countries ?? "—"}</div>
          <div className="delta">geographic reach</div>
        </div>
        <div className="v7-stat">
          <div className="label">UofT Hub Score</div>
          <div className="value" style={{ color: "#DDAED3" }}>
            {latestHub ? latestHub.hub_score.toFixed(2) : "—"}
          </div>
          <div className="delta up">
            {latestHub ? `↑ ${Math.round(latestHub.degree_centrality * 100)}% centrality` : "composite score"}
          </div>
        </div>
      </div>

      {/* ── Tabs ─────────────────────────────────────────────────── */}
      <div className="v7-tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={activeTab === t.key ? "active" : ""}
            onClick={() => setActiveTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ── Growth chart ─────────────────────────────────────────── */}
      {activeTab === "growth" && (
        <div className="v7-card" style={{ padding: "16px 20px" }}>
          {/* mode + line toggles */}
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 14 }}>
            {/* Mode toggle */}
            <div style={{ display: "flex", border: "1px solid var(--border)", borderRadius: 6, overflow: "hidden" }}>
              {(["cumulative", "yearly", "growth_rate"] as GrowthMode[]).map((m) => (
                <button
                  key={m}
                  onClick={() => setGrowthMode(m)}
                  style={{
                    background: growthMode === m ? "var(--color-navy)" : "transparent",
                    color:      growthMode === m ? "#fff" : "var(--muted)",
                    border: "none",
                    borderRadius: 0,
                    padding: "4px 11px",
                    fontSize: "11px",
                    fontWeight: growthMode === m ? 600 : 400,
                    cursor: "pointer",
                    transition: "all 120ms",
                    borderRight: m !== "growth_rate" ? "1px solid var(--border)" : "none",
                  }}
                >
                  {m === "cumulative" ? "Cumulative" : m === "yearly" ? "Yearly" : "Growth %"}
                </button>
              ))}
            </div>

            {/* Line toggles */}
            <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
              {GROWTH_SERIES.map((s) => {
                const on = activeLines.has(s.key);
                return (
                  <button
                    key={s.key}
                    onClick={() => toggleLine(s.key)}
                    style={{
                      display: "inline-flex", alignItems: "center", gap: 5,
                      padding: "3px 10px", borderRadius: 20, fontSize: "11px",
                      fontFamily: "'JetBrains Mono',monospace", cursor: "pointer",
                      border: `1.5px solid ${on ? s.color : "rgba(33,60,81,0.12)"}`,
                      background: on ? `${s.color}18` : "transparent",
                      color: on ? s.color : "#9ab1c4",
                      fontWeight: on ? 600 : 400, transition: "all 120ms",
                    }}
                  >
                    <span style={{ width: 7, height: 7, borderRadius: "50%", background: on ? s.color : "#d1d9e0" }} />
                    {s.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="v7-chart-frame" style={{ height: 380 }}>
            {loading && !growthOption ? (
              <div style={{ padding: 16 }}><div className="v7-skel card" style={{ height: 340 }} /></div>
            ) : growthOption ? (
              <EChart option={growthOption} style={BASE_ECHARTS_STYLE} />
            ) : null}
          </div>
        </div>
      )}

      {/* ── Streamgraph ──────────────────────────────────────────── */}
      {activeTab === "topics" && (
        <div className="v7-card" style={{ padding: "16px 20px" }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12, flexWrap: "wrap" }}>
            <span style={{ fontSize: 12, color: "var(--muted)", fontStyle: "italic" }}>
              River width = paper count per year. Hover to explore each topic.
            </span>
          </div>
          <div className="v7-chart-frame" style={{ height: 400 }}>
            {loading && !streamOption ? (
              <div style={{ padding: 16 }}><div className="v7-skel card" style={{ height: 360 }} /></div>
            ) : streamOption ? (
              <EChart option={streamOption} style={BASE_ECHARTS_STYLE} />
            ) : null}
          </div>
          {/* Topic legend */}
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 10 }}>
            {stream?.topics.map((t, i) => (
              <span key={t} style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11, color: "var(--text)" }}>
                <span style={{ width: 10, height: 10, borderRadius: 2, background: TOPIC_COLORS[i] }} />
                {t}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* ── Heatmap ──────────────────────────────────────────────── */}
      {activeTab === "heatmap" && (
        <div className="v7-card" style={{ padding: "16px 20px" }}>
          <div style={{ marginBottom: 10, fontSize: 12, color: "var(--muted)", fontStyle: "italic" }}>
            Cumulative paper count per institution × topic. Darker = more papers.
          </div>
          <div className="v7-chart-frame" style={{ height: 440 }}>
            {loading && !heatmapOption ? (
              <div style={{ padding: 16 }}><div className="v7-skel card" style={{ height: 400 }} /></div>
            ) : heatmapOption ? (
              <EChart option={heatmapOption} style={BASE_ECHARTS_STYLE} />
            ) : null}
          </div>
        </div>
      )}

      {/* ── Hub score ────────────────────────────────────────────── */}
      {activeTab === "hub" && (
        <div className="v7-card" style={{ padding: "16px 20px" }}>
          <div style={{ marginBottom: 4, fontSize: 12, color: "var(--muted)", fontStyle: "italic" }}>
            Composite Hub Score = 0.3 × degree centrality + 0.3 × betweenness centrality
            + 0.2 × partner count (normalized) + 0.2 × international collaborations (normalized).
            Bars show raw partner / intl-collab counts.
          </div>
          <div style={{ marginBottom: 10 }}>
            {hub && (
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                {hub.data.filter((d) => d.year <= yearTo).slice(-1).map((d) => (
                  <>
                    <span style={{ fontSize: 11, color: "var(--muted)" }}>
                      Degree centrality <b style={{ color: "var(--text)" }}>{(d.degree_centrality * 100).toFixed(0)}%</b>
                    </span>
                    <span style={{ fontSize: 11, color: "var(--muted)" }}>
                      Betweenness <b style={{ color: "var(--text)" }}>{(d.betweenness_centrality * 100).toFixed(0)}%</b>
                    </span>
                    <span style={{ fontSize: 11, color: "var(--muted)" }}>
                      Partner institutions <b style={{ color: "var(--text)" }}>{d.partner_count}</b>
                    </span>
                    <span style={{ fontSize: 11, color: "var(--muted)" }}>
                      Intl. collaborations <b style={{ color: "var(--text)" }}>{d.intl_collab_count}</b>
                    </span>
                  </>
                ))}
              </div>
            )}
          </div>
          <div className="v7-chart-frame" style={{ height: 380 }}>
            {loading && !hubOption ? (
              <div style={{ padding: 16 }}><div className="v7-skel card" style={{ height: 340 }} /></div>
            ) : hubOption ? (
              <EChart option={hubOption} style={BASE_ECHARTS_STYLE} />
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
