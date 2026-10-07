import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";

import {buildStoryFromAnalytics} from "./capture-story-lib.mjs";

const demo = JSON.parse(readFileSync(new URL("../data/visual-story.demo.json", import.meta.url), "utf8"));
const sharedAudit = {
  filter_fingerprint: demo.audit.filter_fingerprint,
  paper_set_sha256: demo.audit.paper_set_sha256,
  included_papers: demo.scope.included_papers,
  reviewed_papers: demo.scope.reviewed_papers,
  fulltext_papers: demo.scope.fulltext_papers,
  classified_papers: demo.scope.classified_papers,
  generated_at: demo.generated_at,
  metric_definitions: {value: "Distinct frozen papers."},
};
const timeline = {
  years: demo.timeline.years,
  series: demo.timeline.series.map((series) => ({
    name: series.name.replaceAll(" ", "_").toUpperCase(),
    data: demo.timeline.years.map((year, index) => [year, series.values[index]]),
  })),
  audit: sharedAudit,
};
const sankey = {
  nodes: demo.flow.nodes.map(({color: _color, ...node}) => node),
  links: demo.flow.links,
  audit: {...sharedAudit},
};
const report = {
  sections: [
    {
      metrics: [
        {key: "overview.reviewed_papers", source_link: "/analytics/report-metric?metric_key=overview.reviewed_papers"},
      ],
    },
  ],
};
const paths = {
  timelinePath: "/analytics/timeline?by=label&top_n=5",
  sankeyPath: "/analytics/sankey?top_institutions=5&top_topics=4",
  reportPath: "/analytics/report",
};

test("builds a validated local snapshot from aligned analytics payloads", () => {
  const story = buildStoryFromAnalytics({timeline, sankey, report, filterQuery: "year_from=2019", ...paths});
  assert.equal(story.contract_version, "visual_story.v1");
  assert.equal(story.data_status, "local_snapshot");
  assert.equal(story.timeline.series[0].values.length, story.timeline.years.length);
  assert.equal(story.flow.nodes.length, demo.flow.nodes.length);
  assert.equal(story.evidence_cards[1].source_link, report.sections[0].metrics[0].source_link);
});

test("rejects analytics payloads with different paper sets", () => {
  const mismatchedSankey = {
    ...sankey,
    audit: {...sankey.audit, paper_set_sha256: "0".repeat(64)},
  };
  assert.throws(
    () => buildStoryFromAnalytics({timeline, sankey: mismatchedSankey, report, filterQuery: "", ...paths}),
    /paper-set hashes differ/,
  );
});

