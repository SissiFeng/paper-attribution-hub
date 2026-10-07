import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts";
import Globe from "react-globe.gl";
import type { GlobeMethods } from "react-globe.gl";
import { useNavigate, useSearchParams } from "react-router-dom";
import { MeshPhongMaterial } from "three";

import { EChart } from "@/components/EChart";
import {
  getInstitutionAuthorshipOptions,
  getMetadataGeographic,
} from "@/lib/api";
import {
  countryName,
  metadataWorldGeography,
  type MetadataMapFeature,
} from "@/lib/metadataGeography";
import type {
  InstitutionAuthorshipOptions,
  MetadataGeographicCountry,
  MetadataGeographicOverview,
} from "@/types";
import styles from "./GeographicPage.module.css";

type MapView = "3d" | "2d";

interface GlobePoint {
  lat: number;
  lng: number;
  countryCode: string;
  name: string;
  paperCount: number;
  institutionCount: number;
  color: string;
  radius: number;
}

interface GlobeArc {
  startLat: number;
  startLng: number;
  endLat: number;
  endLng: number;
  source: string;
  target: string;
  paperCount: number;
  color: string;
}

const DATA_QUERY_KEYS = [
  "year_from",
  "year_to",
  "search",
  "min_affiliation_confidence",
] as const;

const GLOBE_MATERIAL = new MeshPhongMaterial({
  color: "#dce8ee",
  shininess: 7,
});

function dataQueryFrom(searchParams: URLSearchParams) {
  const dataParams = new URLSearchParams();
  for (const key of DATA_QUERY_KEYS) {
    const value = searchParams.get(key);
    if (value) dataParams.set(key, value);
  }
  return dataParams.toString();
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function fillFor(value: number, maximum: number) {
  const ratio = Math.sqrt(value / Math.max(maximum, 1));
  const alpha = 0.24 + ratio * 0.68;
  return `rgba(101, 148, 177, ${alpha.toFixed(3)})`;
}

function supportsWebGL() {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(
      window.WebGLRenderingContext
      && (canvas.getContext("webgl2") || canvas.getContext("webgl")),
    );
  } catch {
    return false;
  }
}

function MetadataFilters({
  options,
  searchParams,
  setSearchParams,
}: {
  options: InstitutionAuthorshipOptions | null;
  searchParams: URLSearchParams;
  setSearchParams: ReturnType<typeof useSearchParams>[1];
}) {
  const [searchDraft, setSearchDraft] = useState(searchParams.get("search") ?? "");
  const years = options?.years ?? [];

  useEffect(() => {
    setSearchDraft(searchParams.get("search") ?? "");
  }, [searchParams]);

  const update = (key: string, value: string, defaultValue?: string) => {
    const next = new URLSearchParams(searchParams);
    if (!value || value === defaultValue) next.delete(key);
    else next.set(key, value);
    setSearchParams(next, { replace: true });
  };

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    update("search", searchDraft.trim());
  };

  return (
    <section className={styles.filterPanel} aria-label="Metadata filters">
      <div className={styles.filterGrid}>
        <label>
          <span>From year</span>
          <select
            value={searchParams.get("year_from") ?? ""}
            onChange={(event) => update("year_from", event.target.value)}
          >
            <option value="">All years</option>
            {years.map((year) => <option key={year} value={year}>{year}</option>)}
          </select>
        </label>
        <label>
          <span>To year</span>
          <select
            value={searchParams.get("year_to") ?? ""}
            onChange={(event) => update("year_to", event.target.value)}
          >
            <option value="">All years</option>
            {years.map((year) => <option key={year} value={year}>{year}</option>)}
          </select>
        </label>
        <label>
          <span>Affiliation confidence</span>
          <select
            value={searchParams.get("min_affiliation_confidence") ?? "0.8"}
            onChange={(event) => update(
              "min_affiliation_confidence",
              event.target.value,
              "0.8",
            )}
          >
            <option value="0.7">≥ 0.70</option>
            <option value="0.8">≥ 0.80</option>
            <option value="0.9">≥ 0.90</option>
            <option value="0.95">≥ 0.95</option>
          </select>
        </label>
        <form onSubmit={submitSearch} className={styles.searchForm}>
          <label>
            <span>Title or abstract</span>
            <div className={styles.searchControl}>
              <input
                value={searchDraft}
                onChange={(event) => setSearchDraft(event.target.value)}
                placeholder="Search metadata…"
              />
              <button type="submit">Apply</button>
            </div>
          </label>
        </form>
      </div>
      <div className={styles.filterFooter}>
        <p>
          Filters apply only to bibliographic, authorship, and affiliation metadata
          in the pinned snapshot.
        </p>
        <button
          type="button"
          className="secondary"
          onClick={() => {
            const next = new URLSearchParams();
            const view = searchParams.get("view");
            if (view) next.set("view", view);
            setSearchParams(next, { replace: true });
          }}
        >
          Clear filters
        </button>
      </div>
    </section>
  );
}

export default function GeographicPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const [options, setOptions] = useState<InstitutionAuthorshipOptions | null>(null);
  const [report, setReport] = useState<MetadataGeographicOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const globeRef = useRef<GlobeMethods>();
  const globeContainerRef = useRef<HTMLDivElement>(null);
  const [globeSize, setGlobeSize] = useState({ width: 760, height: 590 });
  const webglAvailable = useMemo(supportsWebGL, []);
  const requestedView: MapView = searchParams.get("view") === "2d" ? "2d" : "3d";
  const view: MapView = requestedView === "3d" && !webglAvailable ? "2d" : requestedView;
  const dataQuery = dataQueryFrom(searchParams);

  useEffect(() => {
    if (!searchParams.has("geo_center_mode")) return;
    const next = new URLSearchParams(searchParams);
    next.delete("geo_center_mode");
    next.delete("center_type");
    next.delete("center_id");
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    let active = true;
    getInstitutionAuthorshipOptions()
      .then((value) => { if (active) setOptions(value); })
      .catch(() => { if (active) setOptions(null); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    getMetadataGeographic(new URLSearchParams(dataQuery))
      .then((value) => { if (active) setReport(value); })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "Unable to load geography.");
        }
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [dataQuery, retry]);

  useEffect(() => {
    const container = globeContainerRef.current;
    if (!container) return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) {
        setGlobeSize({ width: Math.floor(width), height: Math.floor(height) });
      }
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, [view]);

  useEffect(() => {
    if (view !== "3d") return;
    const globe = globeRef.current as {
      controls?: () => { autoRotate: boolean; autoRotateSpeed: number };
    } | null;
    const controls = globe?.controls?.();
    if (!controls) return;
    controls.autoRotate = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    controls.autoRotateSpeed = 0.32;
  }, [view, report]);

  const countryByCode = useMemo(
    () => new Map(report?.countries.map((country) => [country.country_code, country]) ?? []),
    [report],
  );
  const geography = useMemo(
    () => metadataWorldGeography(report?.countries.map((row) => row.country_code) ?? []),
    [report],
  );
  const maximumPapers = Math.max(
    ...(report?.countries.map((country) => country.paper_count) ?? [1]),
  );
  const globePoints = useMemo<GlobePoint[]>(() => (
    report?.countries.flatMap((country) => {
      const centroid = geography.centroidByCode.get(country.country_code);
      if (!centroid) return [];
      const [lng, lat] = centroid;
      return [{
        lat,
        lng,
        countryCode: country.country_code,
        name: countryName(country.country_code),
        paperCount: country.paper_count,
        institutionCount: country.institution_count,
        color: "#DDAED3",
        radius: 0.16 + Math.sqrt(country.paper_count / maximumPapers) * 0.38,
      }];
    }) ?? []
  ), [geography, maximumPapers, report]);
  const globeArcs = useMemo<GlobeArc[]>(() => (
    report?.collaborations.flatMap((collaboration) => {
      const source = geography.centroidByCode.get(collaboration.source);
      const target = geography.centroidByCode.get(collaboration.target);
      if (!source || !target) return [];
      return [{
        startLng: source[0],
        startLat: source[1],
        endLng: target[0],
        endLat: target[1],
        source: collaboration.source,
        target: collaboration.target,
        paperCount: collaboration.paper_count,
        color: "rgba(221, 174, 211, 0.72)",
      }];
    }) ?? []
  ), [geography, report]);

  const openCountry = (countryCode: string) => {
    const params = new URLSearchParams(searchParams);
    const qs = params.toString();
    navigate(`/geographic/country/${countryCode}${qs ? `?${qs}` : ""}`);
  };

  const mapName = "pas-metadata-world";
  const flatMapOption = useMemo(() => {
    echarts.registerMap(mapName, geography.geoJson as never);
    const regions = geography.geoJson.features.map((mapFeature) => {
      const code = mapFeature.properties.countryCode;
      const country = code ? countryByCode.get(code) : undefined;
      return {
        name: mapFeature.properties.name,
        itemStyle: {
          areaColor: country
            ? fillFor(country.paper_count, maximumPapers)
            : "#eef2f4",
          borderColor: "#ffffff",
          borderWidth: 0.7,
        },
        emphasis: {
          itemStyle: { areaColor: country ? "#DDAED3" : "#e7ecef" },
        },
      };
    });
    return {
      animationDuration: 260,
      tooltip: {
        trigger: "item",
        backgroundColor: "#ffffff",
        borderColor: "rgba(33,60,81,0.18)",
        textStyle: { color: "#213C51" },
        formatter: (item: { name?: string; data?: { countryCode?: string } }) => {
          const code = item.data?.countryCode
            ?? geography.codeByFeatureName.get(item.name ?? "");
          const country = code ? countryByCode.get(code) : undefined;
          return country
            ? `<strong>${countryName(country.country_code)}</strong><br/>${country.paper_count} papers<br/>${country.institution_count} institutions`
            : item.name ?? "No mapped metadata";
        },
      },
      geo: {
        map: mapName,
        roam: true,
        scaleLimit: { min: 1, max: 9 },
        regions,
        emphasis: { label: { show: false } },
      },
      series: [
        {
          name: "Country metadata",
          type: "scatter",
          coordinateSystem: "geo",
          data: globePoints.map((point) => ({
            name: point.name,
            countryCode: point.countryCode,
            value: [point.lng, point.lat, point.paperCount],
            symbolSize: 5 + point.radius * 12,
            itemStyle: { color: "#C783B7", borderColor: "#ffffff", borderWidth: 1 },
          })),
        },
        {
          name: "Cross-country papers",
          type: "lines",
          coordinateSystem: "geo",
          silent: true,
          data: globeArcs.map((arc) => ({
            coords: [[arc.startLng, arc.startLat], [arc.endLng, arc.endLat]],
            value: arc.paperCount,
          })),
          lineStyle: { color: "#C783B7", width: 1.2, opacity: 0.48, curveness: 0.2 },
        },
      ],
    };
  }, [countryByCode, geography, globeArcs, globePoints, maximumPapers]);

  const switchView = (nextView: MapView) => {
    const next = new URLSearchParams(searchParams);
    if (nextView === "3d") next.delete("view");
    else next.set("view", "2d");
    setSearchParams(next, { replace: true });
  };

  return (
    <div className={styles.page}>
      <header className={styles.hero}>
        <div>
          <div className={styles.eyebrow}>Tier 1 · independent metadata snapshot</div>
          <h1>Geographic research landscape</h1>
          <p>
            Countries and collaborations are computed directly from resolved
            authorship affiliations. This view does not intersect with the primary
            PAS paper database or full-text corpus.
          </p>
        </div>
        <div className={styles.snapshotBadge}>
          <span />
          {report?.audit.snapshot.snapshot_id ?? "Metadata snapshot"}
        </div>
      </header>

      <MetadataFilters
        options={options}
        searchParams={searchParams}
        setSearchParams={setSearchParams}
      />

      {loading && !report ? (
        <div className={styles.loading}><span />Loading geographic metadata…</div>
      ) : error ? (
        <div className={styles.notice} role="alert">
          <div><strong>Geographic metadata could not be loaded.</strong><p>{error}</p></div>
          <button type="button" onClick={() => setRetry((value) => value + 1)}>Retry</button>
        </div>
      ) : report && !report.available ? (
        <div className={styles.notice}>
          <div><strong>No countries match these filters.</strong><p>Try a wider year range or a lower affiliation confidence threshold.</p></div>
        </div>
      ) : report ? (
        <>
          <section className={styles.kpiGrid} aria-label="Geographic summary">
            <article className={styles.kpi}><span>Filtered papers</span><strong>{report.scope.corpus_papers.toLocaleString()}</strong><small>{report.scope.mapped_papers.toLocaleString()} mapped to countries</small></article>
            <article className={styles.kpi}><span>Countries</span><strong>{report.scope.country_count.toLocaleString()}</strong><small>{formatPercent(report.scope.paper_country_coverage)} paper coverage</small></article>
            <article className={styles.kpi}><span>Unique institutions with country data</span><strong>{report.scope.institution_count.toLocaleString()}</strong><small>deduplicated metadata identities</small></article>
            <article className={`${styles.kpi} ${styles.accentKpi}`}><span>Cross-country papers</span><strong>{report.scope.cross_country_papers.toLocaleString()}</strong><small>different-author country pairs</small></article>
          </section>

          <section className={styles.mapPanel}>
            <div className={styles.mapHeader}>
              <div>
                <span>Interactive overview</span>
                <h2>{view === "3d" ? "3D globe" : "2D world map"}</h2>
                <p>
                  {!webglAvailable && "3D requires WebGL, so this browser is showing 2D. "}
                  Select any colored country to open its institution comparison.
                </p>
              </div>
              <div className={styles.segmented} role="group" aria-label="Map view">
                <button
                  type="button"
                  aria-pressed={view === "3d"}
                  disabled={!webglAvailable}
                  title={webglAvailable ? undefined : "WebGL is unavailable in this browser"}
                  onClick={() => switchView("3d")}
                >
                  3D globe
                </button>
                <button type="button" aria-pressed={view === "2d"} onClick={() => switchView("2d")}>2D map</button>
              </div>
            </div>
            <div className={styles.mapLegend}>
              <span><i className={styles.countrySwatch} />Paper volume</span>
              <span><i className={styles.arcSwatch} />Cross-country papers</span>
              {geography.unmatchedCodes.length > 0 && (
                <span>{geography.unmatchedCodes.length} country code(s) listed below only</span>
              )}
            </div>
            <div className={styles.mapStage} ref={globeContainerRef}>
              {view === "3d" ? (
                <Globe
                  ref={globeRef}
                  width={globeSize.width}
                  height={globeSize.height}
                  backgroundColor="#f8fafb"
                  globeMaterial={GLOBE_MATERIAL}
                  showAtmosphere
                  atmosphereColor="#6594B1"
                  atmosphereAltitude={0.13}
                  polygonsData={geography.geoJson.features}
                  polygonCapColor={(value) => {
                    const mapFeature = value as MetadataMapFeature;
                    const country = mapFeature.properties.countryCode
                      ? countryByCode.get(mapFeature.properties.countryCode)
                      : undefined;
                    return country
                      ? fillFor(country.paper_count, maximumPapers)
                      : "rgba(224, 231, 235, 0.72)";
                  }}
                  polygonSideColor={() => "rgba(33, 60, 81, 0.08)"}
                  polygonStrokeColor={() => "rgba(255,255,255,0.72)"}
                  polygonAltitude={(value) => (
                    (value as MetadataMapFeature).properties.countryCode ? 0.008 : 0.002
                  )}
                  polygonLabel={(value) => {
                    const mapFeature = value as MetadataMapFeature;
                    const country = mapFeature.properties.countryCode
                      ? countryByCode.get(mapFeature.properties.countryCode)
                      : undefined;
                    return country
                      ? `<strong>${countryName(country.country_code)}</strong><br/>${country.paper_count} papers<br/>${country.institution_count} institutions<br/><em>Click to compare institutions</em>`
                      : mapFeature.properties.name;
                  }}
                  onPolygonClick={(value) => {
                    const code = (value as MetadataMapFeature).properties.countryCode;
                    if (code) openCountry(code);
                  }}
                  pointsData={globePoints}
                  pointLat="lat"
                  pointLng="lng"
                  pointColor="color"
                  pointRadius="radius"
                  pointAltitude={0.018}
                  pointLabel={(value) => {
                    const point = value as GlobePoint;
                    return `<strong>${point.name}</strong><br/>${point.paperCount} papers<br/>${point.institutionCount} institutions`;
                  }}
                  onPointClick={(value) => openCountry((value as GlobePoint).countryCode)}
                  arcsData={globeArcs}
                  arcStartLat="startLat"
                  arcStartLng="startLng"
                  arcEndLat="endLat"
                  arcEndLng="endLng"
                  arcColor="color"
                  arcStroke={(value) => 0.2 + Math.min((value as GlobeArc).paperCount, 8) * 0.025}
                  arcAltitudeAutoScale={0.28}
                  arcsTransitionDuration={0}
                />
              ) : (
                <EChart
                  option={flatMapOption}
                  style={{ height: globeSize.height, minHeight: 460 }}
                  onEvents={{
                    click: (value: unknown) => {
                      const event = value as { name?: string; data?: { countryCode?: string } };
                      const code = event.data?.countryCode
                        ?? geography.codeByFeatureName.get(event.name ?? "");
                      if (code) openCountry(code);
                    },
                  }}
                />
              )}
            </div>
          </section>

          <section className={styles.tablePanel}>
            <div className={styles.panelHeader}>
              <div><span>Accessible country index</span><h2>Countries in this snapshot</h2></div>
              <span>{report.scope.unmapped_papers.toLocaleString()} filtered papers have no eligible country mapping</span>
            </div>
            <div className={styles.tableWrap}>
              <table>
                <thead><tr><th>Country</th><th>Papers</th><th>Institutions</th><th>Authorships</th><th>Cross-country papers</th><th /></tr></thead>
                <tbody>
                  {report.countries.map((country: MetadataGeographicCountry) => (
                    <tr key={country.country_code}>
                      <td><strong>{countryName(country.country_code)}</strong><small>{country.country_code}</small></td>
                      <td>{country.paper_count.toLocaleString()}</td>
                      <td>{country.institution_count.toLocaleString()}</td>
                      <td>{country.authorship_count.toLocaleString()}</td>
                      <td>{country.cross_country_paper_count.toLocaleString()}</td>
                      <td><button type="button" className="secondary" onClick={() => openCountry(country.country_code)}>Open country</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className={styles.auditStrip}>
            <div><span>Data boundary</span><strong>Metadata-only S3 snapshot</strong></div>
            <div><span>Snapshot</span><strong>{report.audit.snapshot.snapshot_id ?? "not recorded"}</strong></div>
            <div><span>Algorithm</span><strong>{report.audit.algorithm}</strong></div>
            <div><span>Country coverage</span><strong>{formatPercent(report.scope.paper_country_coverage)}</strong></div>
          </section>
        </>
      ) : null}
    </div>
  );
}
