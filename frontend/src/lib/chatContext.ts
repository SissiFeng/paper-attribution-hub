const CHAT_FILTER_KEYS = new Set([
  "year_from", "year_to", "labels", "topic_ids", "fields",
  "institution_ids", "countries", "corpus_sources", "sdl_judgements",
  "ac_relevance_judgements", "partner_only", "ac_author_only",
  "has_fulltext", "has_review", "timeline_by", "timeline_top_n",
  "geo_center", "node_types", "edge_types", "group_by",
]);

export function numericSearchParam(
  params: URLSearchParams,
  key: string,
): number | null {
  const raw = params.get(key);
  if (raw == null || raw.trim() === "") return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

export function chatPageContext(pathname: string, search: string): string {
  const visible = new URLSearchParams();
  new URLSearchParams(search).forEach((value, key) => {
    if (CHAT_FILTER_KEYS.has(key)) visible.append(key, value);
  });
  const scope = visible.toString();
  return `Dashboard route: ${pathname}${scope ? `?${scope}` : ""}`.slice(0, 1000);
}

export function scopedEvidencePaperId(pathname: string): string | null {
  const match = pathname.match(/^\/papers\/([^/]+)\/evidence-map$/);
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return null;
  }
}
