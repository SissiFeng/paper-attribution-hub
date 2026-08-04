export type GeographicCenterType = "country" | "institution";

export interface GeographicCenterSelection {
  type: GeographicCenterType;
  id: string;
}

export function geographicCenterFromSearchParams(
  params: URLSearchParams,
): GeographicCenterSelection | null {
  const type = params.get("geo_center_type");
  const id = params.get("geo_center_id");
  if ((type === "country" || type === "institution") && id) {
    return { type, id };
  }
  const legacyCountry = params.get("geo_center");
  return legacyCountry ? { type: "country", id: legacyCountry } : null;
}

export function isGeographicGlobalMode(params: URLSearchParams): boolean {
  return params.get("geo_center_mode") === "global";
}

export function geographicCenterToSearchParams(
  base: URLSearchParams,
  center: GeographicCenterSelection | null,
): URLSearchParams {
  const params = new URLSearchParams(base);
  params.delete("geo_center");
  if (center) {
    params.set("geo_center_type", center.type);
    params.set("geo_center_id", center.id);
    params.delete("geo_center_mode");
  } else {
    params.delete("geo_center_type");
    params.delete("geo_center_id");
    params.set("geo_center_mode", "global");
  }
  return params;
}
