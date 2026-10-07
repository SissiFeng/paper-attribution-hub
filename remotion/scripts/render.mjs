import {createHash} from "node:crypto";
import {mkdirSync, readFileSync, statSync, writeFileSync} from "node:fs";
import {dirname, resolve} from "node:path";
import {fileURLToPath} from "node:url";
import {spawnSync} from "node:child_process";

import {readAndValidateStory} from "./story-validation.mjs";

const root = fileURLToPath(new URL("..", import.meta.url));
const inputFile = resolve(root, process.argv[2] ?? "data/visual-story.demo.json");
const outputFile = resolve(root, process.argv[3] ?? "out/attribution-evidence-story.mp4");
const {story, raw} = readAndValidateStory(inputFile);

mkdirSync(dirname(outputFile), {recursive: true});
const cli = resolve(root, "node_modules/.bin/remotion");
const result = spawnSync(
  cli,
  [
    "render",
    resolve(root, "src/index.ts"),
    "AttributionEvidenceStory",
    outputFile,
    "--props",
    inputFile,
    "--codec",
    "h264",
    "--crf",
    "20",
    "--overwrite",
  ],
  {cwd: root, stdio: "inherit"},
);

if (result.status !== 0) process.exit(result.status ?? 1);

const sha256 = (value) => createHash("sha256").update(value).digest("hex");
const manifestFile = outputFile.replace(/\.[^.]+$/, ".manifest.json");
const manifest = {
  manifest_version: "visual_story_render_manifest.v1",
  composition_id: "AttributionEvidenceStory",
  story_id: story.story_id,
  contract_version: story.contract_version,
  data_status: story.data_status,
  rendered_at: new Date().toISOString(),
  input_path: inputFile,
  input_sha256: sha256(raw),
  output_path: outputFile,
  output_bytes: statSync(outputFile).size,
  output_sha256: sha256(readFileSync(outputFile)),
  filter_fingerprint: story.audit.filter_fingerprint,
  paper_set_sha256: story.audit.paper_set_sha256,
  algorithm: story.audit.algorithm,
  source_endpoints: story.audit.source_endpoints,
};

writeFileSync(manifestFile, `${JSON.stringify(manifest, null, 2)}\n`);
console.log(`render manifest: ${manifestFile}`);

