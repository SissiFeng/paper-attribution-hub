import {mkdirSync} from "node:fs";
import {resolve} from "node:path";
import {fileURLToPath} from "node:url";
import {spawnSync} from "node:child_process";

import {readAndValidateStory} from "./story-validation.mjs";

const root = fileURLToPath(new URL("..", import.meta.url));
const inputFile = resolve(root, process.argv[2] ?? "data/visual-story.demo.json");
const outputDir = resolve(root, process.argv[3] ?? "out/checkpoints");
readAndValidateStory(inputFile);
mkdirSync(outputDir, {recursive: true});

const checkpoints = [
  ["intro", 90],
  ["timeline", 300],
  ["flow", 600],
  ["evidence", 900],
  ["audit", 1200],
];
const cli = resolve(root, "node_modules/.bin/remotion");

for (const [name, frame] of checkpoints) {
  const result = spawnSync(
    cli,
    [
      "still",
      resolve(root, "src/index.ts"),
      "AttributionEvidenceStory",
      resolve(outputDir, `${name}.png`),
      "--props",
      inputFile,
      "--frame",
      String(frame),
      "--overwrite",
    ],
    {cwd: root, stdio: "inherit"},
  );
  if (result.status !== 0) process.exit(result.status ?? 1);
}

console.log(`checkpoint frames: ${outputDir}`);
