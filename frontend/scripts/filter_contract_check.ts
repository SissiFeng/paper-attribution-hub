import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  canonicalFilterSearchParams,
  filterFromSearchParams,
  filterToSearchParams,
  mergeFilterSearchParams,
  paperFilterPayloadFromSearchParams,
} from "../src/lib/filter";
import { escapeHtml } from "../src/lib/html";
import {
  geographicCenterFromSearchParams,
  geographicCenterToSearchParams,
  isGeographicGlobalMode,
} from "../src/lib/geographicUrl";
import {
  coauthorHeatmapTooltip,
  institutionTopicHeatmapTooltip,
  transferFlowTooltip,
} from "../src/lib/chartTooltips";
import {
  multiGraphProjectionFromSearchParams,
  multiGraphProjectionToSearchParams,
} from "../src/lib/multiGraphUrl";
import { isLatestRequest, resultForScope } from "../src/lib/scopedResult";

const fresh = filterFromSearchParams(new URLSearchParams());
assert.deepEqual(fresh.labels, ["CORE_RELEVANT", "RELATED_RELEVANT"]);
assert.deepEqual(
  canonicalFilterSearchParams().getAll("labels"),
  ["CORE_RELEVANT", "RELATED_RELEVANT"],
);

const showAllUrl = filterToSearchParams({ ...fresh, labels: [] });
assert.deepEqual(showAllUrl.getAll("labels"), ["all"]);
assert.deepEqual(filterFromSearchParams(showAllUrl).labels, []);
assert.equal(canonicalFilterSearchParams(showAllUrl).has("labels"), false);

const scoped = {
  ...fresh,
  yearFrom: 2021,
  yearTo: 2025,
  labels: [],
  countries: ["Canada", "United States"],
};
const roundTrip = filterFromSearchParams(filterToSearchParams(scoped));
assert.deepEqual(roundTrip, scoped);
const filterPayload = paperFilterPayloadFromSearchParams(filterToSearchParams(scoped));
assert.equal(filterPayload.year_from, 2021);
assert.equal(filterPayload.year_to, 2025);
assert.deepEqual(filterPayload.labels, []);
assert.deepEqual(filterPayload.countries, ["Canada", "United States"]);

assert.equal(
  escapeHtml('<img src=x onerror="alert(1)">'),
  "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;",
);

const hostile = '<img src=x onerror="alert(1)">';
for (const tooltip of [
  coauthorHeatmapTooltip(hostile, hostile, 3, false),
  transferFlowTooltip(hostile, hostile, 4),
  institutionTopicHeatmapTooltip(hostile, hostile, 5),
]) {
  assert.equal(tooltip.includes("<img"), false);
  assert.equal(tooltip.includes("onerror="), true);
  assert.equal(tooltip.includes("&lt;img"), true);
}

const graphProjection = {
  nodeTypes: ["country"],
  edgeTypes: ["country_collaboration"],
  groupBy: "by_country",
  centerId: "country:Canada",
  hopLimit: 3,
  similarityMin: 0.82,
  similarityTopK: 7,
  minEdgeWeight: 2,
  minPapers: 4,
  minDegree: 2,
  topN: 35,
  excludedNodeIds: ["author:one", "institution:two"],
};
const graphUrl = multiGraphProjectionToSearchParams(showAllUrl, graphProjection);
assert.deepEqual(multiGraphProjectionFromSearchParams(graphUrl), graphProjection);
assert.deepEqual(filterFromSearchParams(graphUrl).labels, []);
assert.equal(multiGraphProjectionFromSearchParams(new URLSearchParams()).hopLimit, 2);
assert.equal(multiGraphProjectionFromSearchParams(new URLSearchParams()).similarityMin, 0.7);
assert.equal(multiGraphProjectionFromSearchParams(new URLSearchParams()).topN, 100);
assert.deepEqual(
  multiGraphProjectionFromSearchParams(graphUrl).excludedNodeIds,
  ["author:one", "institution:two"],
);

const graphProjectionB = {
  ...graphProjection,
  nodeTypes: ["topic", "paper"],
  edgeTypes: ["belongs_to_topic"],
  centerId: null,
  hopLimit: 1,
};
const graphUrlB = multiGraphProjectionToSearchParams(showAllUrl, graphProjectionB);
const historyReplay = [graphUrl, graphUrlB, graphUrl, graphUrlB].map((location) =>
  multiGraphProjectionFromSearchParams(new URLSearchParams(location))
);
assert.deepEqual(historyReplay, [
  graphProjection,
  graphProjectionB,
  graphProjection,
  graphProjectionB,
]);

const chinaCenterUrl = geographicCenterToSearchParams(showAllUrl, {
  type: "country",
  id: "China",
});
const uoftCenterUrl = geographicCenterToSearchParams(chinaCenterUrl, {
  type: "institution",
  id: "uoft/id & reserved",
});
assert.deepEqual(
  geographicCenterFromSearchParams(chinaCenterUrl),
  { type: "country", id: "China" },
);
assert.deepEqual(
  geographicCenterFromSearchParams(uoftCenterUrl),
  { type: "institution", id: "uoft/id & reserved" },
);
assert.deepEqual(filterFromSearchParams(uoftCenterUrl).labels, []);
assert.equal(uoftCenterUrl.has("geo_center"), false);
const globalCenterUrl = geographicCenterToSearchParams(uoftCenterUrl, null);
assert.equal(geographicCenterFromSearchParams(globalCenterUrl), null);
assert.equal(isGeographicGlobalMode(globalCenterUrl), true);
assert.deepEqual(
  geographicCenterFromSearchParams(new URLSearchParams("geo_center=China")),
  { type: "country", id: "China" },
);
assert.deepEqual(
  [chinaCenterUrl, uoftCenterUrl, chinaCenterUrl].map((location) =>
    geographicCenterFromSearchParams(new URLSearchParams(location))
  ),
  [
    { type: "country", id: "China" },
    { type: "institution", id: "uoft/id & reserved" },
    { type: "country", id: "China" },
  ],
);

const completedA = {
  scopeKey: graphUrl.toString(),
  payload: { id: "payload-a" },
};
assert.deepEqual(
  resultForScope(completedA, graphUrl.toString()),
  completedA.payload,
);
assert.equal(
  resultForScope(completedA, graphUrlB.toString()),
  null,
);
assert.equal(resultForScope(null, graphUrlB.toString()), null);

const timelineA = JSON.stringify([graphUrl.toString(), "label"]);
const timelineB = JSON.stringify([graphUrl.toString(), "country"]);
const networkA = JSON.stringify([graphUrl.toString(), 1, 50]);
const networkB = JSON.stringify([graphUrl.toString(), 2, 25]);
assert.notEqual(timelineA, timelineB);
assert.notEqual(networkA, networkB);
assert.equal(resultForScope({ scopeKey: timelineA, payload: "A" }, timelineB), null);
assert.equal(resultForScope({ scopeKey: networkA, payload: "A" }, networkB), null);
assert.equal(
  resultForScope({ scopeKey: timelineB, payload: "B" }, timelineB),
  "B",
);
assert.equal(isLatestRequest(2, 2), true);
assert.equal(isLatestRequest(1, 2), false);

const mergedFilter = mergeFilterSearchParams(graphUrl, {
  ...fresh,
  labels: ["EXCLUDE"],
});
assert.deepEqual(mergedFilter.getAll("node_types"), graphProjection.nodeTypes);
assert.deepEqual(mergedFilter.getAll("labels"), ["EXCLUDE"]);

for (const page of [
  "src/pages/MultiGraphPage.tsx",
  "src/pages/MultiGraphEmbed.tsx",
]) {
  const source = readFileSync(page, "utf8");
  assert.equal(source.includes("initialProjection"), false);
  assert.equal(source.includes("multiGraphProjectionFromSearchParams"), true);
  assert.equal(source.includes("resultForScope"), true);
  assert.equal(source.includes("setPayloadResult(null)"), true);
  assert.match(source, /[Rr]equestGeneration/);
}

for (const page of [
  "src/pages/GeographicPage.tsx",
  "src/pages/TimelinePage.tsx",
  "src/pages/NetworkPage.tsx",
  "src/pages/SankeyPage.tsx",
  "src/pages/ImpactPage.tsx",
  "src/pages/DriftPage.tsx",
  "src/pages/CoauthorNetworkPage.tsx",
  "src/pages/ReportPage.tsx",
  "src/pages/PaperReviewPage.tsx",
]) {
  const source = readFileSync(page, "utf8");
  assert.equal(source.includes("resultForScope"), true);
  assert.match(source, /[Rr]equestGeneration/);
  assert.match(
    source,
    /set(?:Data|Payload|Report|Author|Institution|Papers)Result\(null\)/,
  );
  assert.match(source, /set(?:Error|AuthorError|InstitutionError)\(null\)/);
}

const timelineSource = readFileSync("src/pages/TimelinePage.tsx", "utf8");
assert.equal(timelineSource.includes("JSON.stringify([searchKey, by, topN])"), true);
assert.equal(timelineSource.includes('"field"'), true);
assert.equal(timelineSource.includes('"timeline_top_n"'), true);
const networkSource = readFileSync("src/pages/NetworkPage.tsx", "utf8");
assert.equal(
  networkSource.includes("JSON.stringify([searchKey, minPapers, topN])"),
  true,
);
const driftSource = readFileSync("src/pages/DriftPage.tsx", "utf8");
assert.equal(
  driftSource.includes("JSON.stringify([searchKey, threshold, topNPerYear])"),
  true,
);
assert.equal(driftSource.includes('setProjectionParam("drift_threshold"'), true);
assert.equal(driftSource.includes('setProjectionParam("top_n_per_year"'), true);
assert.equal(
  driftSource.includes("Higher threshold = stricter stability requirement"),
  true,
);
assert.equal(
  driftSource.includes("No adjacent-year cosine similarity fell below"),
  true,
);
assert.equal(driftSource.includes("No drift events above"), false);
const apiSource = readFileSync("src/lib/api.ts", "utf8");
assert.equal(apiSource.includes('params.set("drift_threshold"'), true);
assert.equal(apiSource.includes('params.set("top_n_per_year"'), true);
const filterBarSource = readFileSync("src/components/FilterBar.tsx", "utf8");
assert.equal(filterBarSource.includes("Strict SDL only"), true);
assert.equal(filterBarSource.includes("CONFIRMED_SDL"), true);
assert.equal(filterBarSource.includes("PROBABLE_SDL"), true);
assert.equal(filterBarSource.includes("AC reporting scope"), true);
const reviewQueueSource = readFileSync("src/pages/ReviewQueuePage.tsx", "utf8");
assert.equal(reviewQueueSource.includes("Assigned to me"), true);
assert.equal(reviewQueueSource.includes("Unassigned"), true);
assert.equal(reviewQueueSource.includes("Claim for me"), true);
assert.equal(apiSource.includes("updateReviewAssignment"), true);
const geographicSource = readFileSync("src/pages/GeographicPage.tsx", "utf8");
assert.equal(geographicSource.includes("geographicCenterFromSearchParams"), true);
assert.equal(geographicSource.includes("geographicCenterToSearchParams"), true);
assert.equal(geographicSource.includes("university of toronto"), true);
assert.equal(geographicSource.includes("collaboration growth"), true);
assert.equal(geographicSource.includes("causal influence or citation impact"), true);
assert.equal(geographicSource.includes("Year-by-year values"), true);
assert.equal(geographicSource.includes("Cumulative collaboration papers"), true);
assert.equal(geographicSource.includes("prefers-reduced-motion: reduce"), true);
const multiGraphSource = readFileSync("src/pages/MultiGraphPage.tsx", "utf8");
assert.equal(multiGraphSource.includes("Search visible names"), true);
assert.equal(multiGraphSource.includes("How to read the graph"), true);
assert.equal(multiGraphSource.includes("Hidden node IDs are retained in the URL and audit"), true);
const reportSource = readFileSync("src/pages/ReportPage.tsx", "utf8");
assert.equal(
  reportSource.includes("JSON.stringify([searchKey, enabledSections, backend, policyState])"),
  reportSource.includes("report_entity"),
  reportSource.includes("university_of_toronto"),
  reportSource.includes("toronto"),
  reportSource.includes("ac_sdl_overlap"),
  reportSource.includes("report_evidence_mode"),
  reportSource.includes("report_evidence_confidence_threshold"),
  reportSource.includes("report_evidence_allow_needs_fulltext"),
  reportSource.includes("report_evidence_allow_abstract_only"),
  reportSource.includes("report_evidence_exclude_unreviewed_broad"),
  reportSource.includes("Evidence scope"),
  true,
);
const coauthorSource = readFileSync(
  "src/pages/CoauthorNetworkPage.tsx",
  "utf8",
);
assert.equal(coauthorSource.includes("setAuthorResult(null)"), true);
assert.equal(coauthorSource.includes("setInstitutionResult(null)"), true);
assert.equal(coauthorSource.includes('"coauthor_author_min_papers"'), true);
assert.equal(coauthorSource.includes('"coauthor_selected_institutions"'), true);
assert.equal(coauthorSource.includes('"coauthor_importance_profile"'), true);
assert.equal(coauthorSource.includes('"coauthor_importance_weights"'), true);
assert.equal(coauthorSource.includes("People from selected institutions only"), true);
assert.equal(coauthorSource.includes("complete filtered network"), true);
assert.equal(coauthorSource.includes("PAS corpus papers"), true);
assert.equal(coauthorSource.includes("this is not an attribution decision"), true);
assert.equal(coauthorSource.includes("AC Influence Score"), false);
const paperReviewSource = readFileSync("src/pages/PaperReviewPage.tsx", "utf8");
assert.equal(
  paperReviewSource.includes("JSON.stringify([searchKey, offset, PAGE_SIZE])"),
  true,
);
