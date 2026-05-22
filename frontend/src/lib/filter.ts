import type { PaperFilterState, RelevanceLabel } from "@/types";
import { EMPTY_FILTER } from "@/types";

const LABEL_OPTIONS: RelevanceLabel[] = [
  "CORE_RELEVANT",
  "RELATED_RELEVANT",
  "ADJACENT",
  "UNCERTAIN",
  "EXCLUDE",
];

export { LABEL_OPTIONS };

/** Decode the filter state out of a URLSearchParams object. */
export function filterFromSearchParams(params: URLSearchParams): PaperFilterState {
  const labels = params.getAll("labels").filter((l) => LABEL_OPTIONS.includes(l as RelevanceLabel)) as RelevanceLabel[];
  return {
    yearFrom: params.get("year_from") ? Number(params.get("year_from")) : undefined,
    yearTo: params.get("year_to") ? Number(params.get("year_to")) : undefined,
    labels,
    institutionIds: params.getAll("institution_ids"),
    partnerOnly: params.get("partner_only") === "true",
    acAuthorOnly: params.get("ac_author_only") === "true",
    hasFulltext:
      params.get("has_fulltext") === null
        ? undefined
        : params.get("has_fulltext") === "true",
    hasReview:
      params.get("has_review") === null
        ? undefined
        : params.get("has_review") === "true",
    minConfidence: params.get("min_confidence")
      ? Number(params.get("min_confidence"))
      : undefined,
    maxConfidence: params.get("max_confidence")
      ? Number(params.get("max_confidence"))
      : undefined,
    search: params.get("search") || undefined,
  };
}

/** Encode the filter state into URLSearchParams ready for `fetch` or `setSearchParams`. */
export function filterToSearchParams(state: PaperFilterState): URLSearchParams {
  const p = new URLSearchParams();
  if (state.yearFrom != null) p.set("year_from", String(state.yearFrom));
  if (state.yearTo != null) p.set("year_to", String(state.yearTo));
  for (const l of state.labels) p.append("labels", l);
  for (const i of state.institutionIds) p.append("institution_ids", i);
  if (state.partnerOnly) p.set("partner_only", "true");
  if (state.acAuthorOnly) p.set("ac_author_only", "true");
  if (state.hasFulltext === true) p.set("has_fulltext", "true");
  if (state.hasFulltext === false) p.set("has_fulltext", "false");
  if (state.hasReview === true) p.set("has_review", "true");
  if (state.hasReview === false) p.set("has_review", "false");
  if (state.minConfidence != null)
    p.set("min_confidence", String(state.minConfidence));
  if (state.maxConfidence != null)
    p.set("max_confidence", String(state.maxConfidence));
  if (state.search) p.set("search", state.search);
  return p;
}

export function isFilterEmpty(state: PaperFilterState): boolean {
  return JSON.stringify(state) === JSON.stringify(EMPTY_FILTER);
}
