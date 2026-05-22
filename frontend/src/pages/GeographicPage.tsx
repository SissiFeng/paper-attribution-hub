import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import Globe from "react-globe.gl";

import { TimeSlider } from "@/components/TimeSlider";
import { getGeographic } from "@/lib/api";
import type { GeoCountry, GeoInstitution, GeographicReport } from "@/types";

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

function latLng(country: string): [number, number] {
  return CENTROIDS[country] ?? [0, 0];
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
  return countries.map(c => {
    const [lat, lng] = latLng(c.country);
    const frac = c.paper_count / maxPapers;
    return {
      lat, lng,
      country: c.country,
      paper_count: c.paper_count,
      institution_count: c.institution_count,
      is_partner: c.is_partner,
      color: c.is_partner ? "#DDAED3" : `rgba(101,148,177,${0.5 + frac * 0.5})`,
      radius: 0.4 + frac * 1.2,
      altitude: 0.005 + frac * 0.04,
    };
  });
}

function buildArcs(arcs: GeographicReport["arcs"]): GlobeArc[] {
  return arcs.map(a => {
    const [sLat, sLng] = latLng(a.from);
    const [eLat, eLng] = latLng(a.to);
    return {
      startLat: sLat, startLng: sLng,
      endLat: eLat, endLng: eLng,
      weight: a.weight,
      color: "rgba(101,148,177,0.55)",
    };
  });
}

export default function GeographicPage() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const globeRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [globeSize, setGlobeSize] = useState({ w: 700, h: 560 });

  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState<GeographicReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [yearFrom, setYearFrom] = useState(Number(searchParams.get("year_from")) || 2021);
  const [yearTo,   setYearTo]   = useState(Number(searchParams.get("year_to"))   || 2025);
  const [selected, setSelected] = useState<string | null>(null);

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
    ctrl.autoRotate = true;
    ctrl.autoRotateSpeed = 0.4;
  });

  useEffect(() => {
    const sp = new URLSearchParams(searchParams);
    sp.set("year_from", String(yearFrom));
    sp.set("year_to",   String(yearTo));
    setSearchParams(sp, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [yearFrom, yearTo]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const out = await getGeographic({ year_from: yearFrom, year_to: yearTo });
      setData(out);
    } finally {
      setLoading(false);
    }
  }, [yearFrom, yearTo]);

  useEffect(() => { void load(); }, [load]);

  const points = useMemo(() => buildPoints(data?.countries ?? []), [data]);
  const arcs   = useMemo(() => buildArcs(data?.arcs ?? []),       [data]);

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

  const pauseRotation = useCallback(() => {
    const ctrl = globeRef.current?.controls();
    if (ctrl) ctrl.autoRotate = false;
  }, []);

  const resumeRotation = useCallback(() => {
    const ctrl = globeRef.current?.controls();
    if (ctrl) ctrl.autoRotate = true;
  }, []);

  return (
    <div className="v7-page">
      <div className="v7-hero">
        <div>
          <h1>Geographic Collaboration</h1>
          <p>
            Rotate the globe to explore international partnerships.
            Click a country to filter institutions and people by location.
            Pink markers = AC partner countries.
          </p>
        </div>
        <div className="v7-hero-actions">
          {selected && (
            <button className="v7-btn" onClick={() => setSelected(null)}>
              ✕ {selected}
            </button>
          )}
          <button className="v7-btn" onClick={() => void load()} disabled={loading}>
            ↻ Refresh
          </button>
        </div>
      </div>

      <TimeSlider
        minYear={2021} maxYear={2026}
        yearFrom={yearFrom} yearTo={yearTo}
        onChange={(yf, yt) => { setYearFrom(yf); setYearTo(yt); }}
      />

      <div className="v7-stat-grid">
        <div className="v7-stat">
          <div className="label">Countries</div>
          <div className="value">{data?.countries.length ?? 0}</div>
          <div className="delta">in network</div>
        </div>
        <div className="v7-stat">
          <div className="label">Collaboration arcs</div>
          <div className="value">{data?.arcs.length ?? 0}</div>
          <div className="delta">cross-border</div>
        </div>
        <div className="v7-stat">
          <div className="label">Institutions</div>
          <div className="value">{data?.institutions.length ?? 0}</div>
          <div className="delta">contributing</div>
        </div>
        <div className="v7-stat">
          <div className="label">Papers</div>
          <div className="value">{data?.total_papers ?? 0}</div>
          <div className="delta">in window</div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 360px", gap: "1rem", alignItems: "start" }}>

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
            globeImageUrl="//unpkg.com/three-globe/example/img/earth-blue-marble.jpg"
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
                <b>${p.country}</b><br>
                ${p.paper_count} papers · ${p.institution_count} institution${p.institution_count !== 1 ? "s" : ""}
                ${p.is_partner ? "<br><span style='color:#DDAED3'>AC partner</span>" : ""}
              </div>`;
            }}
            pointResolution={8}
            onPointClick={handlePointClick}
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
              {(data?.countries ?? []).sort((a, b) => b.paper_count - a.paper_count).map(c => (
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
