# Lieflat Charts integration

Entry: Research Insights → Data Stories (`/insights?tab=editorial`). This is an
additive React adaptation of the requested skill, inside the existing Stage 1
derived-data gate. Existing views and backend contracts are preserved.

The existing Impact view (`/insights?tab=impact`, also `/impact`) now uses the same
chart family for its two original yearly charts. Paper counts use F2 Hairline Line;
corpus citation edges use F3 Hairline Area, with one stem per observed publication
year and the original values. They share a reusable time-series component with
metric-specific table headers, tooltips, accessible names and source captions.

For citation volume, candidates were L3 Barcode Lollipop (dense daily series with
an accompanying text column), F2 (already used by paper counts), and F3 (selected
for baseline-to-value stems and an unfilled contour). Source: basics-gallery.html,
“Concurrent users, filled with days”, B3 rendering block. Preserve its vertical
hairlines, peak emphasis and thin contour; substitute years for days, keep gaps
disconnected and remove the template's simulated density and opacity variation.

The old final-year heuristic is retained as a coverage-check prompt, with a hollow
point and dashed segment only for consecutive years. A drop below 60% is not proof
of incomplete ingestion. The headline now correctly says all years are included;
the original code displayed “excl. partial” despite summing every year. No counts,
queries, filter behavior or audit contracts were changed. Existing normalized
citation and collaborator panels remain in place.

## Template selection

Source: https://github.com/larashero3-dotcom/lieflat-charts
Local source: `lieflat-charts/templates/basics-gallery.html`.

| Question | Candidates reviewed | Selected source and adaptation |
| --- | --- | --- |
| When were the selected papers published? | L3 Barcode Lollipop expects a dense daily series; F3 Hairline Area emphasizes continuous volume and could obscure gaps; F2 Hairline Line retains individual readings and a calendar baseline. | F2, “Thirty days of sign-ups”, B2 rendering block. Preserve thin path, period floor ticks, individual dots and peak annotation. Replace days with numeric publication years; disconnect absent years, use a zero baseline, remove the weekend encoding. |
| Which themes have the most dated papers? | L2 Dot Cascade requires short vertical labels; F1 Rung Bars has limited room for long topic names; F5 Tick Rows supports horizontal text and countable units. | F5, “Six teams, shipped and counted”, C1 rendering block. Preserve tick queues, every-fifth markers, guides and exact counts. Move full topic labels above queues; cap at eight rows. |

No Glance, Maps or backup templates are needed. These two charts answer different
questions. Per the user's color correction, all charts now share the application's
existing custom palette: white/light-gray panels, navy-gray text, steel-blue data
and pink peak accents. The scoped `--lf-*` roles reference global CSS variables;
there is no separate Mono palette. Pink marks the peak (with a dark outline), while
position and count remain the quantitative encodings. Muted text and secondary
stems mix existing navy and steel tokens for readable contrast, without new hues.
Typography, 24px cards, SVG structure, reveal and replay derive from Mono tokens.
The components need no additional chart dependency or external font request.

## Data boundaries

- Existing `getTimeline` fetches exclusive labels (top 100, including unclassified)
  for annual totals and the top eight topics for rankings. Only dated papers enter
  either projection. Topic counts overlap and must not be summed into a corpus size.
- Numeric year spacing is retained; absent years are not synthesized as zeros.
- A tick represents `max(1, ceil(maxCount / 45))` papers. A partial final tick has
  proportionate height; exact counts are always visible and available in a table.
- Both projection audit panels remain available. Filter changes immediately hide
  previous results; cancelled requests cannot populate the current selection.
- Loading, empty, failure/retry and reduced-motion states are supported. Development
  mock mode is explicitly labeled. No bundled example dataset is used in this page.
- The existing Stage 1 gate still applies. This change does not promote data or
  enable an unavailable derived view.

## License and verification

Adapted template code is under PolyForm Noncommercial 1.0.0. Its full license is
distributed at `frontend/public/licenses/lieflat-charts.txt` and linked from the
page; it is not relicensed under the application's own terms.

From `frontend`, run:

```sh
./node_modules/.bin/esbuild scripts/editorial_contract_check.tsx --bundle --platform=node --format=cjs --loader:.css=empty --outfile=/tmp/pas-editorial-contract.cjs
node /tmp/pas-editorial-contract.cjs
npm run build
```

Contract checks cover nonconsecutive years, inclusion of unclassified counts,
rejection of overlapping groups for annual totals, large-count tick scaling,
empty/single-year rendering and escaping topic labels.

Validation on 2026-09-07: production compilation and the new chart contracts pass.
The two chart components were visually inspected in an isolated static rendering
at desktop and 390px widths using explicitly labeled synthetic QA data. This does
not verify React replay, fetching or the application gate end-to-end. No local
backend was listening and the root SQLite database contained zero papers.
The existing `check:filter` command fails on its default-label assertion (expected
CORE_RELEVANT/RELATED_RELEVANT, received an empty list); this integration does not
modify that filter logic. No deployment was performed.

2026-09-09 follow-up: the existing Impact charts pass production compilation and
the expanded chart contract checks (citation units, F3 stems, retention of flagged
values, gap-safe annotations). An isolated React rendering with labeled synthetic
data was inspected at narrow and desktop widths; expanding the citation table and
replaying its chart retained the visible values. This verifies the chart components,
not live backend data or the full application's filter/gate flow. No deployment.

Color-unification follow-up: both Data Stories and the existing Impact charts use
these shared roles, including hollow marker backgrounds, table text, buttons and
focus indicators. Layout and data behavior are unchanged.
