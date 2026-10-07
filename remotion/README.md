# PAS Remotion evidence story

An isolated proof of concept for turning a frozen PAS analytics snapshot into a
45-second, auditable video. It does not replace the interactive ECharts pages
and it does not write to the PAS database.

The bundled `data/visual-story.demo.json` is explicitly marked
`illustrative_poc`; its values are not production metrics. Replace it with a
frozen API snapshot that follows `visual_story.v1` before publishing a video.

## Commands

```bash
npm install
npm run capture
npm run validate
npm run typecheck
npm run studio
npm run render
npm run verify:frames
```

`npm run capture` reads the current PAS API without mutating it and writes the
ignored `data/visual-story.snapshot.json`. Configure it with
`PAS_STORY_API_BASE` (default `http://localhost:8000`) and an optional encoded
`PAS_STORY_FILTER_QUERY`. It fails closed if Timeline and Sankey return
different filter or paper-set fingerprints. A captured file is marked
`local_snapshot`; promotion to `verified_snapshot` remains an explicit human
decision.

`npm run render` creates an ignored `out/attribution-evidence-story.mp4` plus an
audit manifest containing the input JSON hash, output video hash, story scope,
and paper-set hash. `npm run verify:frames` renders the same checkpoint twice
and fails if the frame hashes differ.

## Data boundary

The renderer accepts one immutable JSON object as composition props. Numeric
claims should be sourced from existing PAS analytics endpoints, while the
snapshot must retain:

- `filter_fingerprint`
- `paper_set_sha256`
- algorithm and metric definitions
- source endpoint links
- generation timestamp and explicit data status

Remotion publishes its source code but uses a special license rather than an
ordinary MIT/Apache open-source license. Confirm eligibility before production
or automated use: <https://github.com/remotion-dev/remotion/blob/main/LICENSE.md>.

