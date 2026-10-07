import {writeFileSync} from "node:fs";
import {resolve} from "node:path";

import {buildStoryFromAnalytics} from "./capture-story-lib.mjs";

const apiBase = (process.env.PAS_STORY_API_BASE ?? "http://localhost:8000").replace(/\/$/, "");
const filterQuery = process.env.PAS_STORY_FILTER_QUERY ?? "";
const outputFile = resolve(process.argv[2] ?? "data/visual-story.snapshot.json");

const withQuery = (path, ownQuery = "") => {
  const query = new URLSearchParams(ownQuery);
  const filters = new URLSearchParams(filterQuery);
  for (const [key, value] of filters) query.append(key, value);
  const encoded = query.toString();
  return `${path}${encoded ? `?${encoded}` : ""}`;
};

const timelinePath = withQuery("/analytics/timeline", "by=label&top_n=5");
const sankeyPath = withQuery("/analytics/sankey", "top_institutions=5&top_topics=4");
const reportPath = withQuery("/analytics/report");

async function requestJson(path, init) {
  const response = await fetch(`${apiBase}${path}`, init);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${path} returned ${response.status}: ${detail.slice(0, 400)}`);
  }
  return response.json();
}

const [timeline, sankey, report] = await Promise.all([
  requestJson(timelinePath),
  requestJson(sankeyPath),
  requestJson(reportPath, {
    method: "POST",
    headers: {"content-type": "application/json"},
    body: JSON.stringify({sections: ["overview", "growth"], backend: "template"}),
  }),
]);

const story = buildStoryFromAnalytics({
  timeline,
  sankey,
  report,
  filterQuery,
  timelinePath,
  sankeyPath,
  reportPath,
});

writeFileSync(outputFile, `${JSON.stringify(story, null, 2)}\n`);
console.log(`captured ${story.data_status}: ${story.story_id} -> ${outputFile}`);
