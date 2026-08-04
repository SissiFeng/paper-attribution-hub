import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import Globe from "react-globe.gl";

import { AnalysisScopePanel } from "@/components/AnalysisScopePanel";
import { EChart } from "@/components/EChart";
import { FilterBar } from "@/components/FilterBar";
import { TimeSlider } from "@/components/TimeSlider";
import { getFilterOptions, getGeographic } from "@/lib/api";
import {
  geographicCenterFromSearchParams,
  geographicCenterToSearchParams,
  isGeographicGlobalMode,
  type GeographicCenterType,
} from "@/lib/geographicUrl";
import { escapeHtml } from "@/lib/html";
import {
  isLatestRequest,
  resultForScope,
  type ScopedResult,
} from "@/lib/scopedResult";
import type {
  FilterOptions,
  GeoCountry,
  GeoInstitution,
  GeographicReport,
} from "@/types";

// Country centroid lat/lng
const CENTROIDS: Record<string, [number, number]> = {
  Canada:              [56.13,  -106.35],
  "United States":     [37.09,   -95.71],
  "United Kingdom":    [55.38,    -3.44],
  Germany:             [51.17,    10.45],
  Switzerland:         [46.82,     8.23],
  France:              [46.23,     2.21],
  Italy:               [41.87,    12.57],
  Spain:               [40.46,    -3.75],
  Sweden:              [60.13,    18.64],
  Norway:              [60.47,     8.47],
  Netherlands:         [52.13,     5.29],
  Japan:               [36.20,   138.25],
  China:               [35.86,   104.20],
  "South Korea":       [35.91,   127.77],
  India:               [20.59,    78.96],
  Singapore:           [ 1.35,   103.82],
  Australia:           [-25.27,  133.78],
  "New Zealand":       [-40.90,  174.89],
  Brazil:              [-14.24,  -51.93],
  "South Africa":      [-30.56,   22.94],
  Israel:              [31.05,    34.85],
  "Saudi Arabia":      [23.89,    45.08],
};

function latLng(country: string): [number, number] | null {
  return CENTROIDS[country] ?? null;
}

interface GlobePoint {
  lat: number;
  lng: number;
  country: string;
  paper_count: number;
  institution_count: number;
  is_partner: boolean;
  color: string;
  radius: number;
  altitude: number;
  labelAlt: number;
}

interface GlobeArc {
  startLat: number;
  startLng: number;
  endLat: number;
  endLng: number;
  weight: number;
  color: string;
}

function buildPoints(countries: GeoCountry[]): GlobePoint[] {
  const maxPapers = Math.max(...countries.map(c => c.paper_count), 1);
  return countries.flatMap(c => {
    const coordinates = latLng(c.country);
    if (!coordinates) return [];
    const [lat, lng] = coordinates;
    const frac = c.paper_count / maxPapers;
    return [{
      lat, lng,
      country: c.country,
      paper_count: c.paper_count,
      institution_count: c.institution_count,
      is_partner: c.is_partner,
      color: c.is_partner ? "#DDAED3" : `rgba(101,148,177,${0.55 + frac * 0.45})`,
      radius: 0.35 + frac * 0.55,
      altitude: 0.01,
      labelAlt: 0.12,
    }];
  });
}

function buildArcs(arcs: GeographicReport["arcs"]): GlobeArc[] {
  return arcs.flatMap(a => {
    const start = latLng(a.from);
    const end = latLng(a.to);
    if (!start || !end) return [];
    const [sLat, sLng] = start;
    const [eLat, eLng] = end;
    return [{
      startLat: sLat, startLng: sLng,
      endLat: eLat, endLng: eLng,
      weight: a.weight,
      color: "rgba(101,148,177,0.55)",
    }];
  });
}

function buildCenterGrowthOption(data: GeographicReport) {
  const years = data.growth.map((point) => String(point.year));
  return {
    animationDuration: 240,
    tooltip: { trigger: "axis" },
    legend: {
      top: 0,
      data: [
        "Center papers",
        "Collaboration papers",
        "Active partners",
        "Cumulative partners",
      ],
    },
    grid: { left: 48, right: 24, top: 54, bottom: 42 },
    xAxis: { type: "category", data: years, name: "Year" },
    yAxis: { type: "value", minInterval: 1, name: "Distinct count" },
    series: [
      {
        name: "Center papers",
        type: "line",
        data: data.growth.map((point) => point.center_papers),
        itemStyle: { color: "#6594B1" },
        lineStyle: { color: "#6594B1", width: 2.5 },
        symbol: "circle",
        symbolSize: 7,
      },
      {
        name: "Collaboration papers",
        type: "line",
        data: data.growth.map((point) => point.collaboration_papers),
        itemStyle: { color: "#DDAED3" },
        lineStyle: { color: "#DDAED3", width: 2.5 },
        symbol: "diamond",
        symbolSize: 8,
      },
      {
        name: "Active partners",
        type: "bar",
        data: data.growth.map((point) => point.active_partners),
        itemStyle: { color: "rgba(33,60,81,0.35)" },
        barMaxWidth: 24,
      },
      {
        name: "Cumulative partners",
        type: "line",
        data: data.growth.map((point) => point.cumulative_partners),
        itemStyle: { color: "#213C51" },
        lineStyle: { color: "#213C51", width: 2, type: "dashed" },
        symbol: "none",
      },
    ],
  };
}

export default function GeographicPage() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const globeRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [globeSize, setGlobeSize] = useState({ w: 700, h: 560 });

  const [searchParams, setSearchParams] = useSearchParams();
  const searchKey = searchParams.toString();
  const [dataResult, setDataResult] = useState<
    ScopedResult<GeographicReport> | null
  >(null);
  const data = resultForScope(dataResult, searchKey);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [centerOptions, setCenterOptions] = useState<FilterOptions | null>(null);
  const [centerOptionsError, setCenterOptionsError] = useState<string | null>(null);
  const requestGeneration = useRef(0);
  const currentYear = new Date().getFullYear();
  const yearFrom = Number(searchParams.get("year_from")) || 2020;
  const yearTo = Number(searchParams.get("year_to")) || currentYear;
  const centerRequest = useMemo(
    () => geographicCenterFromSearchParams(searchParams),
    [searchKey, searchParams],
  );
  const centerType = centerRequest?.type ?? null;
  const centerId = centerRequest?.id ?? null;
  const globalCenterMode = isGeographicGlobalMode(searchParams);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    if (searchParams.has("year_from") && searchParams.has("year_to")) return;
    const next = new URLSearchParams(searchParams);
    if (!next.has("year_from")) next.set("year_from", "2020");
    if (!next.has("year_to")) next.set("year_to", String(currentYear));
    setSearchParams(next, { replace: true });
  }, [currentYear, searchKey, searchParams, setSearchParams]);

  useEffect(() => {
    let cancelled = false;
    setCenterOptionsError(null);
    getFilterOptions()
      .then((options) => {
        if (!cancelled) setCenterOptions(options);
      })
      .catch((reason) => {
        if (!cancelled) {
          setCenterOptionsError(reason instanceof Error ? reason.message : String(reason));
        }
      });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!centerOptions || centerRequest || globalCenterMode) return;
    const uoft = centerOptions.institutions.find((institution) => {
      const normalized = institution.name.toLocaleLowerCase();
      return institution.id.toLocaleLowerCase() === "uoft"
        || normalized === "university of toronto"
        || normalized.includes("university of toronto");
    });
    if (uoft) {
      setSearchParams(geographicCenterToSearchParams(searchParams, {
        type: "institution",
        id: uoft.id,
      }), { replace: true });
    } else if (centerOptions.countries.includes("Canada")) {
      setSearchParams(geographicCenterToSearchParams(searchParams, {
        type: "country",
        id: "Canada",
      }), { replace: true });
    } else {
      setSearchParams(
        geographicCenterToSearchParams(searchParams, null),
        { replace: true },
      );
    }
  }, [centerOptions, centerRequest, globalCenterMode, searchParams, setSearchParams]);

  // Track container size for the globe
  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect;
      if (width > 0 && height > 0) setGlobeSize({ w: Math.floor(width), h: Math.floor(height) });
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  // Auto-rotation setup
  useEffect(() => {
    const ctrl = globeRef.current?.controls();
    if (!ctrl) return;
    ctrl.autoRotate = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    ctrl.autoRotateSpeed = 0.4;
  }, []);

  const load = useCallback(async () => {
    const requestParams = new URLSearchParams(searchKey);
    if (!requestParams.has("year_from") || !requestParams.has("year_to")) return;
    const generation = ++requestGeneration.current;
    setLoading(true);
    setError(null);
    try {
      const out = await getGeographic(requestParams, centerRequest);
      if (isLatestRequest(generation, requestGeneration.current)) {
        setDataResult({ scopeKey: searchKey, payload: out });
      }
    } catch (err) {
      if (isLatestRequest(generation, requestGeneration.current)) {
        setError(err instanceof Error ? err.message : String(err));
        setDataResult(null);
      }
    } finally {
      if (isLatestRequest(generation, requestGeneration.current)) setLoading(false);
    }
  }, [centerRequest, searchKey]);

  const setYearRange = (nextYearFrom: number, nextYearTo: number) => {
    const next = new URLSearchParams(searchParams);
    next.set("year_from", String(nextYearFrom));
    next.set("year_to", String(nextYearTo));
    setSearchParams(next, { replace: true });
  };

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { setSelected(null); }, [searchKey]);

  const points = useMemo(() => buildPoints(data?.countries ?? []), [data]);
  const arcs   = useMemo(() => buildArcs(data?.arcs ?? []),       [data]);
  const growthOption = useMemo(
    () => data?.center && data.growth.length > 0 ? buildCenterGrowthOption(data) : null,
    [data],
  );

  const selectedCountry: GeoCountry | null = useMemo(
    () => data?.countries.find(c => c.country === selected) ?? null,
    [data, selected]
  );

  const filteredInstitutions: GeoInstitution[] = useMemo(
    () => selected
      ? (data?.institutions ?? []).filter(i => i.country === selected)
      : (data?.institutions ?? []),
    [data, selected]
  );

  const maxPapers = useMemo(
    () => data?.countries.reduce((m, c) => Math.max(m, c.paper_count), 0) ?? 0,
    [data]
  );

  const handlePointClick = useCallback((point: object) => {
    const p = point as GlobePoint;
    setSelected(prev => prev === p.country ? null : p.country);
  }, []);

  const setCenter = useCallback((type: GeographicCenterType | null, id?: string) => {
    setSearchParams(geographicCenterToSearchParams(
      searchParams,
      type && id ? { type, id } : null,
    ));
  }, [searchParams, setSearchParams]);

  const pauseRotation = useCallback(() => {
    const ctrl = globeRef.current?.controls();
    if (ctrl) ctrl.autoRotate = false;
  }, []);

  const resumeRotation = useCallback(() => {
    const ctrl = globeRef.current?.controls();
    if (ctrl && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      ctrl.autoRotate = true;
    }
  }, []);

  return (
    <div className="v7-page">
      <FilterBar />
      <div className="v7-hero">
        <div>
          <h1>Geographic Collaboration</h1>
          <p>
            Rotate the globe to explore international partnerships.
            Click a country to inspect its institutions; set it as the center to
            retain only collaboration arcs incident to that country.
            Pink markers = AC partner countries.
          </p>
        </div>
        <div className="v7-hero-actions">
          {selected && (
            <button className="v7-btn" onClick={() => setSelected(null)}>
              Clear selection: {selected}
            </button>
          )}
          {centerRequest && (
            <button className="v7-btn" onClick={() => setCenter(null)}>
              Show global AC-partner view
            </button>
          )}
          <button className="v7-btn" onClick={() => void load()} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>

      <section className="geo-center-controls" aria-label="Collaboration growth center">
        <div>
          <div className="section-kicker">Center entity</div>
          <h2>{data?.center?.name ?? "Global AC-partner view"}</h2>
          <p>
            Choose a country or institution. The globe shows that center's incident
            collaborations; the trend below counts distinct papers and partners by year.
          </p>
        </div>
        <label>
          Center type
          <select
            value={centerType ?? "global"}
            onChange={(event) => {
              const nextType = event.target.value;
              if (nextType === "global") {
                setCenter(null);
              } else if (nextType === "country") {
                const nextCountry = centerOptions?.countries.includes("Canada")
                  ? "Canada"
                  : centerOptions?.countries[0];
                if (nextCountry) setCenter("country", nextCountry);
              } else {
                const nextInstitution = centerOptions?.institutions.find(
                  (institution) => institution.name.toLocaleLowerCase().includes("university of toronto"),
                ) ?? centerOptions?.institutions[0];
                if (nextInstitution) setCenter("institution", nextInstitution.id);
              }
            }}
          >
            <option value="institution">Institution</option>
            <option value="country">Country</option>
            <option value="global">Global AC-partner view</option>
          </select>
        </label>
        <label>
          {centerType === "country"
            ? "Country"
            : centerType === "institution"
              ? "Institution"
              : "Entity"}
          <select
            value={centerId ?? ""}
            disabled={!centerType || !centerOptions}
            onChange={(event) => {
              if (centerType && event.target.value) setCenter(centerType, event.target.value);
            }}
          >
            {!centerType && <option value="">Choose a center type</option>}
            {centerType === "country" && centerOptions?.countries.map((country) => (
              <option key={country} value={country}>{country}</option>
            ))}
            {centerType === "institution" && centerOptions?.institutions.map((institution) => (
              <option key={institution.id} value={institution.id}>
                {institution.name}{institution.country ? ` — ${institution.country}` : ""}
              </option>
            ))}
          </select>
        </label>
      </section>
      {centerOptionsError && (
        <div role="alert" className="geo-control-error">
          Center options could not be loaded: {centerOptionsError}
        </div>
      )}

      <TimeSlider
        minYear={Math.min(2020, ...(centerOptions?.years ?? [2020]))} maxYear={currentYear}
        yearFrom={yearFrom} yearTo={yearTo}
        onChange={setYearRange}
      />

      {error && <div style={{ color: "var(--uncertain)" }}>Backend error: {error}</div>}

      <div className="v7-stat-grid">
        <div className="v7-stat">
          <div className="label">Countries in filtered set</div>
          <div className="value">{data?.countries.length ?? 0}</div>
          <div className="delta">{points.length} mapped · unresolved omitted</div>
        </div>
        <div className="v7-stat">
          <div className="label">Mapped collaboration arcs</div>
          <div className="value">{arcs.length}</div>
          <div className="delta">{arcs.length} of {data?.arcs.length ?? 0} total</div>
        </div>
        <div className="v7-stat">
          <div className="label">Institutions in filtered set</div>
          <div className="value">{data?.institutions.length ?? 0}</div>
          <div className="delta">contributing</div>
        </div>
        <div className="v7-stat">
          <div className="label">Papers</div>
          <div className="value">{data?.total_papers ?? 0}</div>
          <div className="delta">in window</div>
        </div>
      </div>

      {loading && !data && (
        <div className="geo-loading" role="status">Loading the selected collaboration scope…</div>
      )}

      {data?.center && (
        <section className="geo-growth-section" aria-labelledby="geo-growth-title">
          <header>
            <div>
              <div className="section-kicker">Yearly center evidence</div>
              <h2 id="geo-growth-title">{data.center.name} collaboration growth</h2>
              <p>
                Collaboration means a distinct filtered center paper with at least one
                other {data.center.type === "country" ? "country" : "institution"}.
                It does not measure causal influence or citation impact.
              </p>
            </div>
            <div className="geo-growth-metrics">
              <div><strong>{data.center.paper_count}</strong><span>center papers</span></div>
              <div><strong>{data.center.collaboration_paper_count}</strong><span>collaboration papers</span></div>
              <div><strong>{data.center.partner_count}</strong><span>distinct partners</span></div>
            </div>
          </header>

          {growthOption ? (
            <div className="geo-growth-grid">
              <div className="v7-chart-frame geo-growth-chart">
                <EChart option={growthOption} style={{ height: "100%", width: "100%" }} />
              </div>
              <div className="v7-card geo-partner-list">
                <h2>Partners in selected window</h2>
                {data.partners.length > 0 ? (
                  <ol>
                    {data.partners.slice(0, 20).map((partner) => (
                      <li key={`${data.center?.type}:${partner.id}`}>
                        <span>
                          <strong>{partner.name}</strong>
                          {partner.country && partner.country !== partner.name
                            ? <small>{partner.country}</small>
                            : null}
                        </span>
                        <span>{partner.paper_count} joint paper{partner.paper_count === 1 ? "" : "s"}</span>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p>No cross-entity collaboration papers match the current filter.</p>
                )}
              </div>
            </div>
          ) : (
            <div className="empty">No year-resolved center papers match the current filter.</div>
          )}

          {data.growth.length > 0 && (
            <details className="geo-growth-table">
              <summary>Year-by-year values</summary>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Year</th>
                      <th>Center papers</th>
                      <th>Collaboration papers</th>
                      <th>Active partners</th>
                      <th>Cumulative partners</th>
                      <th>Cumulative collaboration papers</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.growth.map((point) => (
                      <tr key={point.year}>
                        <td>{point.year}</td>
                        <td>{point.center_papers}</td>
                        <td>{point.collaboration_papers}</td>
                        <td>{point.active_partners}</td>
                        <td>{point.cumulative_partners}</td>
                        <td>{point.cumulative_collaboration_papers}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
          {data.center.missing_year_paper_count > 0 && (
            <p className="geo-year-warning">
              {data.center.missing_year_paper_count} center paper(s) lack a year and are excluded from the trend.
            </p>
          )}
        </section>
      )}

      {data && <AnalysisScopePanel audit={data.audit} title="Geographic evidence scope" />}

      <div className="geo-map-layout">

        {/* Globe */}
        <div
          ref={containerRef}
          style={{
            height: 560,
            borderRadius: 14,
            overflow: "hidden",
            background: "radial-gradient(ellipse at 40% 35%, #0d1b2a 0%, #060d14 100%)",
            boxShadow: "0 4px 24px rgba(0,0,0,0.18)",
            cursor: "grab",
          }}
          onMouseEnter={pauseRotation}
          onMouseLeave={resumeRotation}
        >
          <Globe
            ref={globeRef}
            width={globeSize.w}
            height={globeSize.h}
            globeImageUrl="/earth-blue-marble.jpg"
            backgroundColor="rgba(0,0,0,0)"
            atmosphereColor="rgba(101,148,177,0.6)"
            atmosphereAltitude={0.25}
            // Points (countries)
            pointsData={points}
            pointLat="lat"
            pointLng="lng"
            pointColor="color"
            pointAltitude="altitude"
            pointRadius="radius"
            pointLabel={(d: object) => {
              const p = d as GlobePoint;
              return `<div style="font-family:'JetBrains Mono',monospace;font-size:12px;background:#213C51;color:#fff;padding:6px 10px;border-radius:8px;line-height:1.6">
                <b>${escapeHtml(p.country)}</b><br>
                ${p.paper_count} papers · ${p.institution_count} institution${p.institution_count !== 1 ? "s" : ""}
                ${p.is_partner ? "<br><span style='color:#DDAED3'>AC partner</span>" : ""}
              </div>`;
            }}
            pointResolution={8}
            onPointClick={handlePointClick}
            // Floating number chips above each country
            htmlElementsData={points}
            htmlLat="lat"
            htmlLng="lng"
            htmlAltitude={0.14}
            htmlElement={(d: object) => {
              const p = d as GlobePoint;
              const color = p.is_partner ? "#DDAED3" : "rgba(200,220,235,0.92)";
              const bg = p.is_partner
                ? "rgba(221,174,211,0.18)"
                : "rgba(13,27,42,0.55)";
              const border = p.is_partner
                ? "1px solid rgba(221,174,211,0.55)"
                : "1px solid rgba(101,148,177,0.35)";
              const el = document.createElement("div");
              Object.assign(el.style, {
                fontFamily: "'JetBrains Mono', monospace",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: "1px",
                cursor: "pointer",
                transform: "translate(-50%, -100%)",
                pointerEvents: "auto",
              });
              const chip = document.createElement("div");
              Object.assign(chip.style, {
                background: bg,
                border,
                borderRadius: "8px",
                padding: "3px 9px 2px",
                backdropFilter: "blur(4px)",
              });
              const count = document.createElement("span");
              count.textContent = String(p.paper_count);
              Object.assign(count.style, {
                display: "block",
                color,
                fontSize: "15px",
                fontWeight: "700",
                lineHeight: "1",
                textAlign: "center",
                textShadow: "0 1px 4px rgba(0,0,0,0.7)",
              });
              const country = document.createElement("span");
              country.textContent = p.country;
              Object.assign(country.style, {
                display: "block",
                maxWidth: "80px",
                overflow: "hidden",
                color,
                opacity: "0.72",
                fontSize: "8.5px",
                fontWeight: "500",
                textAlign: "center",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              });
              const stem = document.createElement("div");
              Object.assign(stem.style, {
                width: "1px",
                height: "8px",
                background: color,
                opacity: "0.4",
              });
              chip.append(count, country);
              el.append(chip, stem);
              el.addEventListener("click", () => {
                setSelected(prev => prev === p.country ? null : p.country);
              });
              return el;
            }}
            // Selection ring
            ringsData={selected ? points.filter(p => p.country === selected) : []}
            ringLat="lat"
            ringLng="lng"
            ringColor={() => ["rgba(221,174,211,0.9)", "rgba(221,174,211,0)"]}
            ringMaxRadius={4}
            ringPropagationSpeed={2}
            ringRepeatPeriod={900}
            // Arcs (collaborations)
            arcsData={arcs}
            arcStartLat="startLat"
            arcStartLng="startLng"
            arcEndLat="endLat"
            arcEndLng="endLng"
            arcColor={(_d: object) => [`rgba(221,174,211,0.85)`, `rgba(101,148,177,0.85)`]}
            arcStroke={(d: object) => Math.log1p((d as GlobeArc).weight) * 0.6 + 0.3}
            arcDashLength={0.35}
            arcDashGap={0.15}
            arcDashAnimateTime={2200}
            arcAltitudeAutoScale={0.35}
          />
        </div>

        {/* Sidebar */}
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>

          {/* Selected country info */}
          {selectedCountry ? (
            <div className="v7-card" style={{ borderColor: selectedCountry.is_partner ? "rgba(221,174,211,0.5)" : "var(--border)" }}>
              <h2 style={{ marginBottom: 8 }}>
                {selectedCountry.is_partner && (
                  <span style={{
                    display: "inline-block", padding: "1px 7px", borderRadius: 20,
                    background: "rgba(221,174,211,0.15)", color: "#8e6a84",
                    fontSize: "0.7rem", fontWeight: 600, marginRight: 8, verticalAlign: "middle",
                  }}>PARTNER</span>
                )}
                {selectedCountry.country}
              </h2>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                <div style={{ background: "var(--bg-3)", borderRadius: 8, padding: "8px 12px" }}>
                  <div style={{ fontSize: "0.72rem", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>Papers</div>
                  <div style={{ fontSize: "1.4rem", fontWeight: 700, color: "var(--text)" }}>{selectedCountry.paper_count}</div>
                </div>
                <div style={{ background: "var(--bg-3)", borderRadius: 8, padding: "8px 12px" }}>
                  <div style={{ fontSize: "0.72rem", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>Institutions</div>
                  <div style={{ fontSize: "1.4rem", fontWeight: 700, color: "var(--text)" }}>{selectedCountry.institution_count}</div>
                </div>
              </div>
              <button
                type="button"
                className="v7-btn"
                style={{ marginTop: 10, width: "100%" }}
                aria-pressed={data?.center?.type === "country" && data.center.id === selectedCountry.country}
                onClick={() => setCenter(
                  data?.center?.type === "country" && data.center.id === selectedCountry.country
                    ? null
                    : "country",
                  selectedCountry.country,
                )}
              >
                {data?.center?.type === "country" && data.center.id === selectedCountry.country
                  ? "Show global AC-partner view"
                  : `Show ${selectedCountry.country} collaboration growth`}
              </button>
            </div>
          ) : (
            <div className="v7-card" style={{ textAlign: "center", color: "var(--muted)", padding: "20px 16px", fontSize: "0.85rem" }}>
              Click a country on the globe to filter
            </div>
          )}

          {/* Institutions list */}
          <div className="v7-card" style={{ flex: 1, maxHeight: 420, overflowY: "auto" }}>
            <h2 style={{ marginBottom: 10 }}>
              <span className="accent-dot" />
              {selected ? `${selected} — institutions` : "All institutions"}
              <span style={{ float: "right", fontWeight: 400, color: "var(--muted)", fontSize: "0.8rem" }}>
                {filteredInstitutions.length}
              </span>
            </h2>
            {filteredInstitutions.length === 0 ? (
              <div style={{ color: "var(--muted)", fontSize: "0.85rem" }}>No institutions found.</div>
            ) : (
              <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 4 }}>
                {filteredInstitutions.map(inst => (
                  <li key={inst.id} style={{
                    display: "flex", alignItems: "center", gap: 8,
                    padding: "6px 0", borderBottom: "1px solid var(--border)",
                    fontSize: "0.82rem",
                  }}>
                    {inst.is_partner && (
                      <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#DDAED3", flexShrink: 0 }} />
                    )}
                    <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--text)" }}>
                      {inst.name}
                    </span>
                    <span style={{ color: "var(--muted)", fontSize: "0.75rem", flexShrink: 0 }}>
                      {inst.paper_count}p
                    </span>
                    {inst.institution_id && (
                      <button
                        type="button"
                        className="geo-center-inline"
                        aria-label={`Show collaboration growth centered on ${inst.name}`}
                        aria-pressed={data?.center?.type === "institution" && data.center.id === inst.institution_id}
                        onClick={() => setCenter("institution", inst.institution_id)}
                      >
                        Center
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Country ranking */}
          <div className="v7-card">
            <h2 style={{ marginBottom: 10 }}>
              <span className="accent-dot" /> All countries
            </h2>
            <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 3 }}>
              {[...(data?.countries ?? [])].sort((a, b) => b.paper_count - a.paper_count).map(c => (
                <li
                  key={c.country}
                  onClick={() => setSelected(prev => prev === c.country ? null : c.country)}
                  style={{
                    display: "flex", alignItems: "center", gap: 8,
                    padding: "4px 6px", borderRadius: 6, cursor: "pointer",
                    background: selected === c.country ? "rgba(101,148,177,0.10)" : "transparent",
                    transition: "background 100ms",
                  }}
                >
                  {c.is_partner && (
                    <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#DDAED3", flexShrink: 0 }} />
                  )}
                  {!c.is_partner && <span style={{ width: 6 }} />}
                  <span style={{
                    flex: 1, fontSize: "0.8rem",
                    color: selected === c.country ? "var(--text)" : "var(--muted)",
                    fontWeight: selected === c.country ? 600 : 400,
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                  }}>
                    {c.country}
                  </span>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <div style={{
                      width: 60, height: 4, background: "var(--bg-3)", borderRadius: 2, overflow: "hidden",
                    }}>
                      <div style={{
                        width: `${(c.paper_count / Math.max(1, maxPapers)) * 100}%`,
                        height: "100%",
                        background: c.is_partner ? "#DDAED3" : "#6594B1",
                        borderRadius: 2,
                      }} />
                    </div>
                    <span style={{ color: "var(--muted)", fontSize: "0.75rem", minWidth: 16, textAlign: "right" }}>
                      {c.paper_count}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
