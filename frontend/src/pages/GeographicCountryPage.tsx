import { FormEvent, useEffect, useMemo, useState } from "react";
import { geoEquirectangular } from "d3-geo";
import * as echarts from "echarts";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { EChart } from "@/components/EChart";
import {
  getInstitutionAuthorshipOptions,
  getMetadataGeographicCountry,
} from "@/lib/api";
import {
  countryFeatureCollection,
  countryName,
  metadataWorldGeography,
} from "@/lib/metadataGeography";
import { escapeHtml } from "@/lib/html";
import type {
  InstitutionAuthorshipRow,
  InstitutionAuthorshipOptions,
  MetadataGeographicCountryDetail,
} from "@/types";
import styles from "./GeographicPage.module.css";

const FALLBACK_SCHEMES = [
  { value: "lead_balanced", label: "First/last balanced", description: "" },
  { value: "lead_heavy", label: "First/last heavy", description: "" },
  { value: "equal_fractional", label: "Equal fractional", description: "" },
  { value: "full_counting", label: "Full counting", description: "" },
];

const FALLBACK_ROLES = [
  { value: "all", label: "All authors", description: "" },
  { value: "first", label: "First author only", description: "" },
  { value: "corresponding", label: "Corresponding author only", description: "" },
  { value: "last", label: "Last author only", description: "" },
  { value: "middle", label: "Middle authors only", description: "" },
];

interface InstitutionLocation {
  latitude: number;
  longitude: number;
  city: string | null;
  region: string | null;
  country_code: string | null;
}

interface InstitutionLocationCatalog {
  schema_version: "pas.institution_locations.v1";
  snapshot_id: string;
  source: string;
  locations: Record<string, InstitutionLocation>;
}

interface InstitutionMapPoint {
  name: string;
  value: [number, number, number];
  symbolOffset: [number, number];
  papers: number;
  credit: number;
  city: string | null;
  region: string | null;
}

const LOCATION_CATALOGS: Record<string, string> = {
  "20260812T172752079667Z_58d807199ea4":
    "/data/institution-locations-20260812T172752079667Z_58d807199ea4.json",
};

function institutionLocation(
  row: InstitutionAuthorshipRow,
  catalog: InstitutionLocationCatalog | null,
  countryCode: string,
) {
  if (!row.openalex_id || !catalog) return null;
  const location = catalog.locations[row.openalex_id];
  return location?.country_code === countryCode ? location : null;
}

function institutionMapPoints(
  rows: InstitutionAuthorshipRow[],
  catalog: InstitutionLocationCatalog | null,
  countryCode: string,
) {
  const groups = new Map<string, InstitutionMapPoint[]>();
  for (const row of rows) {
    const location = institutionLocation(row, catalog, countryCode);
    if (!location) continue;
    const point: InstitutionMapPoint = {
      name: row.name,
      value: [location.longitude, location.latitude, row.paper_count],
      symbolOffset: [0, 0],
      papers: row.paper_count,
      credit: row.weighted_credit,
      city: location.city,
      region: location.region,
    };
    const key = `${location.longitude.toFixed(4)}|${location.latitude.toFixed(4)}`;
    const group = groups.get(key) ?? [];
    group.push(point);
    groups.set(key, group);
  }
  for (const group of groups.values()) {
    if (group.length === 1) continue;
    group.forEach((point, index) => {
      const angle = (Math.PI * 2 * index) / group.length;
      const radius = Math.min(12, 6 + group.length * 0.65);
      point.symbolOffset = [
        Math.round(Math.cos(angle) * radius),
        Math.round(Math.sin(angle) * radius),
      ];
    });
  }
  return [...groups.values()].flat();
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function formatCredit(value: number) {
  return value.toLocaleString(undefined, {
    minimumFractionDigits: value < 10 ? 2 : 1,
    maximumFractionDigits: 2,
  });
}

export default function GeographicCountryPage() {
  const { countryCode: rawCountryCode = "" } = useParams();
  const countryCode = rawCountryCode.toUpperCase();
  const [searchParams, setSearchParams] = useSearchParams();
  const [options, setOptions] = useState<InstitutionAuthorshipOptions | null>(null);
  const [detail, setDetail] = useState<MetadataGeographicCountryDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [locationCatalog, setLocationCatalog] = useState<InstitutionLocationCatalog | null>(null);
  const [locationCatalogLoading, setLocationCatalogLoading] = useState(false);
  const [retry, setRetry] = useState(0);
  const [searchDraft, setSearchDraft] = useState(searchParams.get("search") ?? "");
  const query = searchParams.toString();
  const displayName = countryName(countryCode);

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
    getMetadataGeographicCountry(countryCode, new URLSearchParams(query))
      .then((value) => { if (active) setDetail(value); })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "Unable to load this country.");
        }
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [countryCode, query, retry]);

  const snapshotId = detail?.audit.snapshot.snapshot_id ?? null;
  useEffect(() => {
    let active = true;
    const catalogUrl = snapshotId ? LOCATION_CATALOGS[snapshotId] : null;
    setLocationCatalog(null);
    if (!snapshotId || !catalogUrl) {
      setLocationCatalogLoading(false);
      return () => { active = false; };
    }
    setLocationCatalogLoading(true);
    fetch(catalogUrl)
      .then(async (response) => {
        if (!response.ok) throw new Error(`Location catalog returned ${response.status}`);
        return response.json() as Promise<InstitutionLocationCatalog>;
      })
      .then((catalog) => {
        if (
          active
          && catalog.schema_version === "pas.institution_locations.v1"
          && catalog.snapshot_id === snapshotId
        ) {
          setLocationCatalog(catalog);
        }
      })
      .catch(() => { if (active) setLocationCatalog(null); })
      .finally(() => { if (active) setLocationCatalogLoading(false); });
    return () => { active = false; };
  }, [snapshotId]);

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

  const overviewLink = useMemo(() => {
    const params = new URLSearchParams();
    for (const key of [
      "year_from",
      "year_to",
      "search",
      "min_affiliation_confidence",
      "view",
    ]) {
      const value = searchParams.get(key);
      if (value) params.set(key, value);
    }
    const qs = params.toString();
    return `/geographic${qs ? `?${qs}` : ""}`;
  }, [searchParams]);

  const geography = useMemo(
    () => metadataWorldGeography(countryCode ? [countryCode] : []),
    [countryCode],
  );
  const countryMapOption = useMemo(() => {
    const collection = countryFeatureCollection(geography, countryCode);
    if (!collection) return null;
    const mapName = `pas-country-${countryCode}`;
    echarts.registerMap(mapName, collection as never);
    const flatProjection = geoEquirectangular();
    const points = institutionMapPoints(
      detail?.institutions ?? [],
      locationCatalog,
      countryCode,
    );
    return {
      animationDuration: 280,
      aria: {
        enabled: true,
        description: `${displayName} map with ${points.length} institution locations. Institution details are also available in the table below.`,
      },
      tooltip: {
        trigger: "item",
        backgroundColor: "#ffffff",
        borderColor: "rgba(33,60,81,0.18)",
        textStyle: { color: "#213C51" },
        formatter: (item: { componentSubType?: string; data?: InstitutionMapPoint }) => {
          if (item.componentSubType !== "scatter" || !item.data) return displayName;
          const location = [item.data.city, item.data.region].filter(Boolean).join(", ");
          return `<strong>${escapeHtml(item.data.name)}</strong>${location ? `<br/>${escapeHtml(location)}` : ""}<br/>${item.data.papers} distinct papers<br/>${formatCredit(item.data.credit)} weighted credit`;
        },
      },
      geo: {
        map: mapName,
        roam: true,
        layoutCenter: ["50%", "51%"],
        layoutSize: "86%",
        scaleLimit: { min: 1, max: 12 },
        projection: {
          project: (point: [number, number]) => flatProjection(point) as [number, number],
          unproject: (point: [number, number]) => flatProjection.invert?.(point) ?? point,
        },
        itemStyle: {
          areaColor: "#6594B1",
          borderColor: "#ffffff",
          borderWidth: 1.2,
        },
        emphasis: { itemStyle: { areaColor: "#DDAED3" }, label: { show: false } },
      },
      series: [{
        name: "Institutions",
        type: "scatter",
        coordinateSystem: "geo",
        data: points,
        symbol: "circle",
        symbolSize: (value: [number, number, number]) => 8 + Math.min(8, Math.sqrt(value[2]) * 1.5),
        itemStyle: {
          color: "#C783B7",
          borderColor: "#ffffff",
          borderWidth: 1.5,
          shadowBlur: 5,
          shadowColor: "rgba(199,131,183,0.42)",
        },
        emphasis: {
          scale: 1.35,
          label: {
            show: true,
            position: "top",
            formatter: "{b}",
            color: "#213C51",
            backgroundColor: "rgba(255,255,255,0.94)",
            borderColor: "rgba(33,60,81,0.12)",
            borderWidth: 1,
            borderRadius: 4,
            padding: [4, 6],
            fontSize: 10,
          },
        },
        z: 4,
      }],
    };
  }, [countryCode, detail, displayName, geography, locationCatalog]);

  const mappedInstitutionCount = useMemo(
    () => institutionMapPoints(
      detail?.institutions ?? [],
      locationCatalog,
      countryCode,
    ).length,
    [countryCode, detail, locationCatalog],
  );

  const institutionOption = useMemo(() => {
    const rows = [...(detail?.institutions.slice(0, 14) ?? [])].reverse();
    return {
      animationDuration: 280,
      tooltip: {
        trigger: "item",
        backgroundColor: "#ffffff",
        borderColor: "rgba(33,60,81,0.18)",
        textStyle: { color: "#213C51" },
        formatter: (item: { data: { name: string; value: number; papers: number } }) =>
          `<strong>${item.data.name}</strong><br/>${formatCredit(item.data.value)} weighted credit<br/>${item.data.papers} distinct papers`,
      },
      grid: { left: 210, right: 48, top: 12, bottom: 30 },
      xAxis: {
        type: "value",
        axisLabel: { color: "#6594B1", fontSize: 10 },
        splitLine: { lineStyle: { color: "rgba(33,60,81,0.07)", type: "dashed" } },
      },
      yAxis: {
        type: "category",
        data: rows.map((row) => row.name),
        axisLabel: { color: "#213C51", fontSize: 10, width: 190, overflow: "truncate" },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      series: [{
        type: "bar",
        barMaxWidth: 18,
        data: rows.map((row) => ({
          name: row.name,
          value: row.weighted_credit,
          papers: row.paper_count,
          itemStyle: {
            color: row.contributes_to_focus ? "#DDAED3" : "#6594B1",
            borderRadius: [0, 4, 4, 0],
          },
        })),
        label: {
          show: true,
          position: "right",
          color: "#213C51",
          fontSize: 10,
          formatter: (item: { value: number }) => formatCredit(item.value),
        },
      }],
    };
  }, [detail]);

  const yearlyOption = useMemo(() => {
    const rows = detail?.country.yearly ?? [];
    return {
      animationDuration: 280,
      tooltip: { trigger: "axis" },
      grid: { left: 44, right: 18, top: 22, bottom: 34 },
      xAxis: {
        type: "category",
        data: rows.map((row) => row.year),
        axisLabel: { color: "#6594B1", fontSize: 10 },
        axisLine: { lineStyle: { color: "rgba(33,60,81,0.12)" } },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        minInterval: 1,
        axisLabel: { color: "#6594B1", fontSize: 10 },
        splitLine: { lineStyle: { color: "rgba(33,60,81,0.07)", type: "dashed" } },
      },
      series: [
        {
          name: "Papers",
          type: "line",
          smooth: true,
          data: rows.map((row) => row.paper_count),
          lineStyle: { color: "#6594B1", width: 2.5 },
          itemStyle: { color: "#6594B1" },
          areaStyle: { color: "rgba(101,148,177,0.12)" },
        },
        {
          name: "Cross-country",
          type: "line",
          data: rows.map((row) => row.cross_country_paper_count),
          lineStyle: { color: "#C783B7", width: 2 },
          itemStyle: { color: "#C783B7" },
        },
      ],
    };
  }, [detail]);

  const schemes = options?.credit_schemes ?? FALLBACK_SCHEMES;
  const roles = options?.author_roles ?? FALLBACK_ROLES;
  const years = options?.years ?? [];

  return (
    <div className={styles.page}>
      <nav className={styles.breadcrumb} aria-label="Breadcrumb">
        <Link to={overviewLink}>← Global geography</Link><span>/</span><span>{displayName}</span>
      </nav>
      <header className={styles.hero}>
        <div>
          <div className={styles.eyebrow}>Country detail · independent metadata snapshot</div>
          <h1>{displayName}</h1>
          <p>
            Institution contributions for authorships carrying the {countryCode} country
            code. Paper counts use any affiliated author; weighted credit follows the
            controls below.
          </p>
        </div>
        <div className={styles.snapshotBadge}><span />{detail?.audit.snapshot.snapshot_id ?? countryCode}</div>
      </header>

      <section className={styles.filterPanel} aria-label="Country comparison controls">
        <div className={`${styles.filterGrid} ${styles.countryFilterGrid}`}>
          <label><span>From year</span><select value={searchParams.get("year_from") ?? ""} onChange={(event) => update("year_from", event.target.value)}><option value="">All years</option>{years.map((year) => <option key={year} value={year}>{year}</option>)}</select></label>
          <label><span>To year</span><select value={searchParams.get("year_to") ?? ""} onChange={(event) => update("year_to", event.target.value)}><option value="">All years</option>{years.map((year) => <option key={year} value={year}>{year}</option>)}</select></label>
          <label><span>Credit model</span><select value={searchParams.get("credit_scheme") ?? "lead_balanced"} onChange={(event) => update("credit_scheme", event.target.value, "lead_balanced")}>{schemes.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
          <label><span>Author role</span><select value={searchParams.get("author_role") ?? "all"} onChange={(event) => update("author_role", event.target.value, "all")}>{roles.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
          <label><span>Affiliation allocation</span><select value={searchParams.get("affiliation_allocation") ?? "fractional"} onChange={(event) => update("affiliation_allocation", event.target.value, "fractional")}><option value="fractional">Fractional</option><option value="full">Full</option></select></label>
          <label><span>Affiliation confidence</span><select value={searchParams.get("min_affiliation_confidence") ?? "0.8"} onChange={(event) => update("min_affiliation_confidence", event.target.value, "0.8")}><option value="0.7">≥ 0.70</option><option value="0.8">≥ 0.80</option><option value="0.9">≥ 0.90</option><option value="0.95">≥ 0.95</option></select></label>
          <form onSubmit={submitSearch} className={styles.searchForm}><label><span>Title or abstract</span><div className={styles.searchControl}><input value={searchDraft} onChange={(event) => setSearchDraft(event.target.value)} placeholder="Search metadata…" /><button type="submit">Apply</button></div></label></form>
        </div>
        <div className={styles.filterFooter}><p>{detail?.configuration.credit_scheme_description ?? "The same pinned metadata snapshot is used for the map and institution comparison."}</p></div>
      </section>

      {loading && !detail ? (
        <div className={styles.loading}><span />Loading {displayName} metadata…</div>
      ) : error ? (
        <div className={styles.notice} role="alert"><div><strong>This country could not be loaded.</strong><p>{error}</p></div><button type="button" onClick={() => setRetry((value) => value + 1)}>Retry</button></div>
      ) : detail ? (
        <>
          <section className={styles.kpiGrid} aria-label={`${displayName} summary`}>
            <article className={styles.kpi}><span>Country papers</span><strong>{detail.scope.country_papers.toLocaleString()}</strong><small>any affiliated author</small></article>
            <article className={styles.kpi}><span>Institutions</span><strong>{detail.scope.country_institutions.toLocaleString()}</strong><small>resolved metadata identities</small></article>
            <article className={styles.kpi}><span>Authorships</span><strong>{detail.scope.country_authorships.toLocaleString()}</strong><small>distinct paper-author pairs</small></article>
            <article className={`${styles.kpi} ${styles.accentKpi}`}><span>Weighted credit</span><strong>{formatCredit(detail.scope.country_weighted_credit)}</strong><small>{detail.configuration.credit_scheme_label}</small></article>
          </section>

          <section className={styles.countryVisualGrid}>
            <article className={styles.panel}>
              <div className={styles.panelHeader}><div><span>Country outline</span><h2>{displayName}</h2></div><span>{locationCatalogLoading ? "Loading institution locations…" : `${mappedInstitutionCount} of ${detail.institutions.length} institutions · pink markers`}</span></div>
              {countryMapOption ? <EChart option={countryMapOption} style={{ height: 340 }} /> : <div className={styles.mapUnavailable}>A boundary shape is unavailable for {countryCode}; the institution data remains available below.</div>}
            </article>
            <article className={styles.panel}>
              <div className={styles.panelHeader}><div><span>Metadata timeline</span><h2>Papers by year</h2></div><span>{detail.country.cross_country_paper_count} cross-country</span></div>
              <EChart option={yearlyOption} style={{ height: 340 }} />
            </article>
          </section>

          <section className={styles.panel}>
            <div className={styles.panelHeader}><div><span>Weighted authorship allocation</span><h2>Institution comparison</h2></div><span>Top {Math.min(detail.institutions.length, 14)} shown</span></div>
            {detail.institutions.length ? <EChart option={institutionOption} style={{ height: Math.max(360, Math.min(detail.institutions.length, 14) * 30 + 90) }} /> : <div className={styles.mapUnavailable}>No institution credit remains under the selected author-role filter.</div>}
          </section>

          <section className={styles.tablePanel}>
            <div className={styles.panelHeader}><div><span>Replayable institution rows</span><h2>All returned institutions</h2></div><span>{detail.configuration.author_role_label}</span></div>
            <div className={styles.tableWrap}>
              <table>
                <thead><tr><th>Rank</th><th>Institution</th><th>Weighted credit</th><th>Country share</th><th>Papers</th><th>Authorships</th><th>First</th><th>Last</th><th>Corresponding</th></tr></thead>
                <tbody>{detail.institutions.map((row) => <tr key={row.id ?? row.name}><td>{row.rank}</td><td><strong>{row.name}</strong>{row.ror && <small>{row.ror}</small>}</td><td>{formatCredit(row.weighted_credit)}</td><td>{formatPercent(row.share_of_country_credit ?? 0)}</td><td>{row.paper_count}</td><td>{row.authorship_count}</td><td>{formatCredit(row.first_author_credit)}</td><td>{formatCredit(row.last_author_credit)}</td><td>{formatCredit(row.corresponding_author_credit)}</td></tr>)}</tbody>
              </table>
            </div>
          </section>

          <section className={styles.auditStrip}>
            <div><span>Data boundary</span><strong>Metadata-only S3 snapshot</strong></div>
            <div><span>Country paper set</span><strong>{detail.audit.country_paper_set_sha256?.slice(0, 16)}…</strong></div>
            <div><span>Credit model</span><strong>{detail.configuration.credit_scheme_label}</strong></div>
            <div><span>Role filter</span><strong>{detail.configuration.author_role_label}</strong></div>
          </section>
        </>
      ) : null}
    </div>
  );
}
