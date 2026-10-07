import type { PaperFilterState, RelevanceLabel } from "@/types";
import { DEFAULT_FILTER, EMPTY_FILTER } from "@/types";

const LABEL_OPTIONS: RelevanceLabel[] = [
  "CORE_RELEVANT",
  "RELATED_RELEVANT",
  "SDL_FIELD_RELEVANT",
  "ADJACENT",
  "UNCERTAIN",
  "EXCLUDE",
];

export { LABEL_OPTIONS };

const FILTER_QUERY_KEYS = [
  "year_from",
  "year_to",
  "labels",
  "institution_ids",
  "topic_ids",
  "fields",
  "countries",
  "corpus_sources",
  "sdl_judgements",
  "ac_relevance_judgements",
  "ai_for_science_judgements",
  "review_statuses",
  "partner_only",
  "ac_author_only",
  "has_fulltext",
  "has_review",
  "min_confidence",
  "max_confidence",
  "search",
] as const;

/** Decode the filter state out of a URLSearchParams object.
 *  When no labels are present in the URL (fresh page load), defaults to
 *  DEFAULT_FILTER.labels (all Stage 1 classifications).
 */
export function filterFromSearchParams(params: URLSearchParams): PaperFilterState {
  const rawLabels = params.getAll("labels");
  // Distinguish "user explicitly set labels=[]" (all param removed) from "no params yet".
  // We use a sentinel: "all" means show everything; empty param list means use default.
  const showAll = rawLabels.includes("all");
  const labels = showAll
    ? []
    : rawLabels.length > 0
      ? rawLabels.filter((l) => LABEL_OPTIONS.includes(l as RelevanceLabel)) as RelevanceLabel[]
      : DEFAULT_FILTER.labels;
  return {
    yearFrom: params.get("year_from") ? Number(params.get("year_from")) : undefined,
    yearTo: params.get("year_to") ? Number(params.get("year_to")) : undefined,
    labels,
    institutionIds: params.getAll("institution_ids"),
    topicIds: params.getAll("topic_ids"),
    fields: params.getAll("fields"),
    countries: params.getAll("countries"),
    corpusSources: params.getAll("corpus_sources"),
    sdlJudgements: params.getAll("sdl_judgements"),
    acRelevanceJudgements: params.getAll("ac_relevance_judgements"),
    aiForScienceJudgements: params.getAll("ai_for_science_judgements"),
    reviewStatuses: params.getAll("review_statuses"),
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
  if (state.labels.length === 0) p.append("labels", "all");
  else for (const l of state.labels) p.append("labels", l);
  for (const i of state.institutionIds) p.append("institution_ids", i);
  for (const topic of state.topicIds) p.append("topic_ids", topic);
  for (const field of state.fields) p.append("fields", field);
  for (const country of state.countries) p.append("countries", country);
  for (const source of state.corpusSources) p.append("corpus_sources", source);
  for (const judgement of state.sdlJudgements) p.append("sdl_judgements", judgement);
  for (const judgement of state.acRelevanceJudgements)
    p.append("ac_relevance_judgements", judgement);
  for (const judgement of state.aiForScienceJudgements)
    p.append("ai_for_science_judgements", judgement);
  for (const status of state.reviewStatuses) p.append("review_statuses", status);
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

/** Replace shared filter keys while preserving route-specific URL state. */
export function mergeFilterSearchParams(
  base: URLSearchParams,
  state: PaperFilterState,
): URLSearchParams {
  const merged = new URLSearchParams(base);
  FILTER_QUERY_KEYS.forEach((key) => merged.delete(key));
  filterToSearchParams(state).forEach((value, key) => merged.append(key, value));
  return merged;
}

/** Canonicalize filters before an API request so rendered and queried scope match. */
export function canonicalFilterSearchParams(params?: URLSearchParams): URLSearchParams {
  const state = filterFromSearchParams(new URLSearchParams(params));
  const canonical = filterToSearchParams(state);
  if (state.labels.length === 0) canonical.delete("labels");
  return canonical;
}

/** JSON payload for APIs that accept the same shared filter in a request body. */
export function paperFilterPayloadFromSearchParams(params?: URLSearchParams) {
  const state = filterFromSearchParams(new URLSearchParams(params));
  return {
    year_from: state.yearFrom,
    year_to: state.yearTo,
    labels: state.labels,
    institution_ids: state.institutionIds,
    topic_ids: state.topicIds,
    fields: state.fields,
    countries: state.countries,
    corpus_sources: state.corpusSources,
    sdl_judgements: state.sdlJudgements,
    ac_relevance_judgements: state.acRelevanceJudgements,
    ai_for_science_judgements: state.aiForScienceJudgements,
    review_statuses: state.reviewStatuses,
    partner_only: state.partnerOnly,
    ac_author_only: state.acAuthorOnly,
    has_fulltext: state.hasFulltext,
    has_review: state.hasReview,
    min_confidence: state.minConfidence,
    max_confidence: state.maxConfidence,
    search: state.search,
  };
}

export function isFilterEmpty(state: PaperFilterState): boolean {
  return JSON.stringify(state) === JSON.stringify(EMPTY_FILTER);
}
