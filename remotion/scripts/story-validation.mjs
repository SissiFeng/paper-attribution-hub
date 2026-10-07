import {readFileSync} from "node:fs";
import {resolve} from "node:path";

const SHA256 = /^[a-f0-9]{64}$/;
const DATA_STATUSES = new Set(["illustrative_poc", "local_snapshot", "verified_snapshot"]);
const LAYERS = new Set(["institution", "topic", "label"]);
const TONES = new Set(["gold", "teal", "rose"]);

function assert(condition, message) {
  if (!condition) throw new Error(`visual_story.v1 validation failed: ${message}`);
}

function nonNegativeNumber(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

export function validateStory(story) {
  assert(story && typeof story === "object", "root must be an object");
  assert(story.contract_version === "visual_story.v1", "contract_version must be visual_story.v1");
  assert(typeof story.story_id === "string" && story.story_id.length > 0, "story_id is required");
  assert(DATA_STATUSES.has(story.data_status), "data_status is unsupported");
  assert(!Number.isNaN(Date.parse(story.generated_at)), "generated_at must be an ISO timestamp");

  for (const field of ["included_papers", "reviewed_papers", "fulltext_papers", "classified_papers"]) {
    assert(nonNegativeNumber(story.scope?.[field]), `scope.${field} must be non-negative`);
  }
  assert(story.scope.reviewed_papers <= story.scope.included_papers, "reviewed papers exceed included papers");
  assert(story.scope.fulltext_papers <= story.scope.included_papers, "fulltext papers exceed included papers");

  assert(Array.isArray(story.timeline?.years) && story.timeline.years.length >= 2, "timeline needs at least two years");
  assert(Array.isArray(story.timeline?.series) && story.timeline.series.length > 0, "timeline series are required");
  for (const series of story.timeline.series) {
    assert(series.values.length === story.timeline.years.length, `timeline series ${series.name} length mismatch`);
    assert(series.values.every(nonNegativeNumber), `timeline series ${series.name} contains invalid values`);
  }

  assert(Array.isArray(story.flow?.nodes) && story.flow.nodes.length > 0, "flow nodes are required");
  assert(Array.isArray(story.flow?.links) && story.flow.links.length > 0, "flow links are required");
  const nodeIds = new Set();
  for (const node of story.flow.nodes) {
    assert(typeof node.id === "string" && !nodeIds.has(node.id), `flow node id ${node.id} is missing or duplicated`);
    assert(LAYERS.has(node.layer), `flow node ${node.id} has invalid layer`);
    nodeIds.add(node.id);
  }
  for (const link of story.flow.links) {
    assert(nodeIds.has(link.source) && nodeIds.has(link.target), `flow link ${link.source} -> ${link.target} has unknown node`);
    assert(nonNegativeNumber(link.value), `flow link ${link.source} -> ${link.target} has invalid value`);
  }

  assert(Array.isArray(story.evidence_cards) && story.evidence_cards.length === 3, "exactly three evidence cards are required");
  for (const card of story.evidence_cards) {
    assert(TONES.has(card.tone), `evidence card ${card.eyebrow} has invalid tone`);
    assert(typeof card.source_link === "string" && card.source_link.startsWith("/"), `evidence card ${card.eyebrow} needs an API source link`);
  }

  assert(SHA256.test(story.audit?.filter_fingerprint), "audit.filter_fingerprint must be a lowercase SHA-256");
  assert(SHA256.test(story.audit?.paper_set_sha256), "audit.paper_set_sha256 must be a lowercase SHA-256");
  assert(typeof story.audit.algorithm === "string" && story.audit.algorithm.length > 0, "audit.algorithm is required");
  assert(Object.keys(story.audit.metric_definitions ?? {}).length > 0, "audit.metric_definitions are required");
  assert(Array.isArray(story.audit.source_endpoints) && story.audit.source_endpoints.every((item) => item.startsWith("/")), "audit.source_endpoints must be API paths");

  return story;
}

export function readAndValidateStory(file) {
  const resolved = resolve(file);
  const raw = readFileSync(resolved, "utf8");
  return {story: validateStory(JSON.parse(raw)), raw, resolved};
}

