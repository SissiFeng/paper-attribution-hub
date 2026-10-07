import {createHash} from "node:crypto";
import {mkdtempSync, readFileSync, rmSync} from "node:fs";
import {tmpdir} from "node:os";
import {join, resolve} from "node:path";
import {fileURLToPath} from "node:url";
import {spawnSync} from "node:child_process";

import {readAndValidateStory} from "./story-validation.mjs";

const root = fileURLToPath(new URL("..", import.meta.url));
const inputFile = resolve(root, process.argv[2] ?? "data/visual-story.demo.json");
readAndValidateStory(inputFile);

const temp = mkdtempSync(join(tmpdir(), "pas-remotion-frame-"));
const cli = resolve(root, "node_modules/.bin/remotion");
const outputs = [join(temp, "checkpoint-a.png"), join(temp, "checkpoint-b.png")];

try {
  for (const output of outputs) {
    const result = spawnSync(
      cli,
      [
        "still",
        resolve(root, "src/index.ts"),
        "AttributionEvidenceStory",
        output,
        "--props",
        inputFile,
        "--frame",
        "840",
        "--overwrite",
      ],
      {cwd: root, stdio: "inherit"},
    );
    if (result.status !== 0) process.exit(result.status ?? 1);
  }

  const hash = (file) => createHash("sha256").update(readFileSync(file)).digest("hex");
  const [first, second] = outputs.map(hash);
  if (first !== second) throw new Error(`frame determinism mismatch: ${first} != ${second}`);
  console.log(`deterministic checkpoint frame 840: ${first}`);
} finally {
  rmSync(temp, {recursive: true, force: true});
}

