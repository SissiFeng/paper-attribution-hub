import { geoCentroid } from "d3-geo";
import type { Feature, FeatureCollection, Geometry } from "geojson";
import { feature } from "topojson-client";
import type {
  GeometryCollection,
  Topology,
} from "topojson-specification";
import worldAtlas from "world-atlas/countries-50m.json";

export interface MetadataMapProperties {
  name: string;
  countryCode?: string;
}

export type MetadataMapFeature = Feature<Geometry, MetadataMapProperties>;

const NAME_ALIASES: Record<string, string> = {
  BO: "Bolivia",
  BN: "Brunei",
  CD: "Democratic Republic of the Congo",
  CG: "Republic of the Congo",
  CI: "Ivory Coast",
  CZ: "Czechia",
  FM: "Micronesia",
  HK: "Hong Kong",
  IR: "Iran",
  KP: "North Korea",
  KR: "South Korea",
  LA: "Laos",
  MD: "Moldova",
  MK: "Macedonia",
  MO: "Macao",
  PS: "Palestine",
  RU: "Russia",
  SY: "Syria",
  TZ: "United Republic of Tanzania",
  TR: "Turkey",
  US: "United States of America",
  VA: "Vatican",
  VE: "Venezuela",
  VN: "Vietnam",
};

const topology = worldAtlas as unknown as Topology<{
  countries: GeometryCollection<MetadataMapProperties>;
}>;
const atlasCollection = feature(
  topology,
  topology.objects.countries,
) as FeatureCollection<Geometry, MetadataMapProperties>;

const regionNames = new Intl.DisplayNames(["en"], { type: "region" });

function normalizedName(value: string) {
  return value
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]/gi, "")
    .toLocaleLowerCase();
}

export function countryName(countryCode: string) {
  try {
    return regionNames.of(countryCode.toUpperCase()) ?? countryCode.toUpperCase();
  } catch {
    return countryCode.toUpperCase();
  }
}

export interface MetadataWorldGeography {
  geoJson: FeatureCollection<Geometry, MetadataMapProperties>;
  featureByCode: Map<string, MetadataMapFeature>;
  codeByFeatureName: Map<string, string>;
  centroidByCode: Map<string, [number, number]>;
  unmatchedCodes: string[];
}

export function metadataWorldGeography(
  countryCodes: string[],
): MetadataWorldGeography {
  const desiredNames = new Map<string, string>();
  for (const rawCode of countryCodes) {
    const code = rawCode.toUpperCase();
    desiredNames.set(
      normalizedName(NAME_ALIASES[code] ?? countryName(code)),
      code,
    );
  }

  const featureByCode = new Map<string, MetadataMapFeature>();
  const codeByFeatureName = new Map<string, string>();
  const centroidByCode = new Map<string, [number, number]>();
  const features = atlasCollection.features.map((atlasFeature) => {
    const name = atlasFeature.properties?.name ?? "Unknown";
    const code = desiredNames.get(normalizedName(name));
    const mappedFeature: MetadataMapFeature = {
      ...atlasFeature,
      properties: { name, ...(code ? { countryCode: code } : {}) },
    };
    if (code) {
      featureByCode.set(code, mappedFeature);
      codeByFeatureName.set(name, code);
      centroidByCode.set(code, geoCentroid(mappedFeature));
    }
    return mappedFeature;
  });

  return {
    geoJson: { type: "FeatureCollection", features },
    featureByCode,
    codeByFeatureName,
    centroidByCode,
    unmatchedCodes: countryCodes
      .map((code) => code.toUpperCase())
      .filter((code) => !featureByCode.has(code)),
  };
}

export function countryFeatureCollection(
  geography: MetadataWorldGeography,
  countryCode: string,
): FeatureCollection<Geometry, MetadataMapProperties> | null {
  const featureForCountry = geography.featureByCode.get(countryCode.toUpperCase());
  return featureForCountry
    ? { type: "FeatureCollection", features: [featureForCountry] }
    : null;
}
