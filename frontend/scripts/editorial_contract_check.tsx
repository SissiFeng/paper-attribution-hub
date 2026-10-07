import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { AnnualChart, TopicsChart, TimeSeriesChart } from "../src/components/editorial/EditorialCharts";
import { annualPapers, rankedTopics, tickUnit } from "../src/components/editorial/data";
import type { TimelinePayload } from "../src/types";

const payload = {
  by: "label", years: [2025, 2022], top_n: 100,
  series: [
    { name: "CORE", data: [[2022, 3], [2025, 2]] },
    { name: "UNCLASSIFIED", data: [[2025, 4]] },
  ],
} as TimelinePayload;
const annual = annualPapers(payload);
assert.deepEqual(annual, [{ label: "2022", value: 3 }, { label: "2025", value: 6 }]);
assert.throws(() => annualPapers({ ...payload, by: "topic" }), /exclusive/);
const sparse = renderToStaticMarkup(<AnnualChart points={annual} />);
assert.match(sparse, /d="M48,149 M472,60"/); // Missing years are not interpolated.
assert.doesNotMatch(sparse, /NaN|Infinity/);
for (const points of [[], [{ label: "2026", value: 0 }]]) {
  assert.doesNotMatch(renderToStaticMarkup(<AnnualChart points={points} />), /NaN|Infinity/);
}
const topics = rankedTopics({ ...payload, by: "topic", series: [
  { name: "A & <B>", data: [[2022, 11], [2025, 12]] },
  { name: "Shared", data: [[2022, 12]] },
] });
assert.equal(topics[0].value, 23); // No normalization across overlapping topics.
assert.equal(tickUnit([{ label: "large", value: 10001 }]), 223);
assert.equal(tickUnit([]), 1);
const rendered = renderToStaticMarkup(<TopicsChart points={topics} />);
assert.match(rendered, /A &amp; &lt;B&gt;/);
assert.match(rendered, /View exact values/);
assert.doesNotMatch(rendered, /NaN|Infinity/);
console.log("Editorial chart contracts passed: sparse years, exclusive totals, overlap, scale, empty states, escaped labels.");

const citationPoints = [{ label: "2025", value: 2 }, { label: "2024", value: 10 }];
const citations = renderToStaticMarkup(<TimeSeriesChart title="Citations" points={citationPoints}
  valueLabel="Citation edges" source="test" variant="hairline-area" flaggedYear="2025" />);
assert.match(citations, /<th scope="col">Citation edges<\/th>/);
assert.match(citations, /2025: 2 citation edges/);
assert.match(citations, /not confirmed missing data/);
assert.match(citations, /stroke-dasharray="4 4"/);
assert.match(citations, /y1="238" y2="60"/); // F3 stems reach the original, untransformed value.
assert.match(citations, /<td>2<\/td>/); // The flagged year's count is never removed.
const gap = renderToStaticMarkup(<TimeSeriesChart title="Gap" points={annual}
  source="test" flaggedYear="2025" />);
assert.doesNotMatch(gap, /stroke-dasharray="4 4"/); // Do not bridge unobserved years.
console.log("Existing Impact chart contracts passed: citation units, F3 stems, retained flagged values, gap-safe annotations.");
