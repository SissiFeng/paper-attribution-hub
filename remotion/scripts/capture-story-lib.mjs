import {validateStory} from "./story-validation.mjs";

const labelColors = new Map([
  ["CORE_RELEVANT", "#f0c76a"],
  ["RELATED_RELEVANT", "#65c8bf"],
  ["ADJACENT", "#d99aad"],
  ["UNCERTAIN", "#e89062"],
  ["EXCLUDE", "#718083"],
]);
const fallbackColors = ["#f0c76a", "#65c8bf", "#d99aad", "#9fc7e0", "#e89062"];
const layerColors = {
  institution: "#6594b1",
  topic: "#65c8bf",
  label: "#f0c76a",
};
const normalizedLabel = (name) => name.replaceAll(" ", "_").toUpperCase();

export function buildStoryFromAnalytics({
  timeline,
  sankey,
  report,
  filterQuery,
  timelinePath,
  sankeyPath,
  reportPath,
}) {
  if (timeline.audit?.filter_fingerprint !== sankey.audit?.filter_fingerprint) {
    throw new Error("Timeline and Sankey filter fingerprints differ; snapshot rejected");
  }
  if (timeline.audit?.paper_set_sha256 !== sankey.audit?.paper_set_sha256) {
    throw new Error("Timeline and Sankey paper-set hashes differ; snapshot rejected");
  }

  const audit = timeline.audit;
  const years = timeline.years ?? [];
  const reportMetricSources = new Map(
    (report.sections ?? [])
      .flatMap((section) => section.metrics ?? [])
      .map((metric) => [metric.key, metric.source_link]),
  );
  const evidenceSource = (key, fallback) => reportMetricSources.get(key) ?? fallback;

  return validateStory({
    contract_version: "visual_story.v1",
    story_id: `pas-attribution-${audit.filter_fingerprint.slice(0, 12)}`,
    title: "Attribution, made inspectable",
    subtitle: "A frozen PAS analytics snapshot rendered as an evidence-led scientific story",
    period_label: years.length > 0 ? `${years[0]}–${years.at(-1)} publication window` : "No publication years in scope",
    generated_at: audit.generated_at,
    data_status: "local_snapshot",
    scope: {
      label: filterQuery || "All papers in the current API scope",
      included_papers: audit.included_papers,
      reviewed_papers: audit.reviewed_papers,
      fulltext_papers: audit.fulltext_papers,
      classified_papers: audit.classified_papers,
    },
    timeline: {
      years,
      series: (timeline.series ?? []).slice(0, 5).map((series, index) => ({
        name: series.name.replaceAll("_", " ").toLowerCase().replace(/^./, (letter) => letter.toUpperCase()),
        color: labelColors.get(normalizedLabel(series.name)) ?? fallbackColors[index],
        values: years.map((year) => new Map(series.data).get(year) ?? 0),
      })),
      annotation: "The timeline is a descriptive replay of a frozen PAS snapshot, not a causal claim.",
    },
    flow: {
      nodes: (sankey.nodes ?? []).map((node) => ({
        ...node,
        color: node.layer === "label"
          ? labelColors.get(normalizedLabel(node.name)) ?? layerColors.label
          : layerColors[node.layer],
      })),
      links: sankey.links ?? [],
      annotation: "Each ribbon counts distinct-paper support under the same frozen evidence scope.",
    },
    evidence_cards: [
      {
        eyebrow: "Scope",
        value: String(audit.included_papers),
        label: "distinct papers",
        detail: "Every count is tied to one frozen filter fingerprint.",
        source_link: timelinePath,
        tone: "gold",
      },
      {
        eyebrow: "Human review",
        value: String(audit.reviewed_papers),
        label: "papers reviewed",
        detail: "Model output remains distinguishable from human confirmation.",
        source_link: evidenceSource("overview.reviewed_papers", timelinePath),
        tone: "teal",
      },
      {
        eyebrow: "Evidence depth",
        value: String(audit.fulltext_papers),
        label: "full-text records",
        detail: "Abstract-only and missing-fulltext states stay visible.",
        source_link: evidenceSource("overview.fulltext_papers", timelinePath),
        tone: "rose",
      },
    ],
    audit: {
      filter_fingerprint: audit.filter_fingerprint,
      paper_set_sha256: audit.paper_set_sha256,
      algorithm: "pas_remotion_evidence_story.v1",
      metric_definitions: {
        ...Object.fromEntries(
          Object.entries(timeline.audit.metric_definitions ?? {}).map(([key, value]) => [`timeline.${key}`, value]),
        ),
        ...Object.fromEntries(
          Object.entries(sankey.audit.metric_definitions ?? {}).map(([key, value]) => [`flow.${key}`, value]),
        ),
      },
      source_endpoints: [timelinePath, sankeyPath, reportPath],
    },
  });
}

