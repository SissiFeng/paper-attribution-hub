# llm-wiki — Cross-SDL Knowledge Base (schema layer)

You read it; the LLM writes it. This vault is generated from the
paper-attribution database — edit upstream (data/*.yaml, the DB, the
exporter), then regenerate. Hand edits to wiki/ pages are overwritten.

## Three layers

1. **Raw sources** — `backend/paper_attribution.db` (papers, paper→lab links,
   typed entities) plus `data/sdl_labs.yaml`, `data/sdl_entities.yaml`,
   `data/method_stages.yaml`.
2. **Wiki** — this folder: interlinked Markdown pages under `wiki/`,
   cataloged in `index.md`, visualized in `graph.html`.
3. **Schema** — this file: layout, naming, front-matter contract, operations.

## Layout

    index.md          catalog: every wiki page, one-liner each, by category
    log.md            append-only ops log; entries are `## [YYYY-MM-DD] <op> | <Title>`
    graph.html        standalone interactive graph (data embedded; open in a browser)
    graph.json        the same nodes+edges data, for programmatic use
    wiki/overview.md  synthesis page: corpus totals, top labs, fastest spreaders
    wiki/labs/        one page per SDL lab
    wiki/methods/     fine-grained methods (grouped by category in index.md)
    wiki/materials/   wiki/instruments/  wiki/software/
    wiki/concepts/    one page per coarse method category (family)

## Naming & links

- Filenames are slugs: lowercase, `-` separators (see `slugify`).
- All intra-wiki references are Obsidian path-style wikilinks relative to the
  vault root, e.g. `[[wiki/labs/matter-lab|Matter Lab]]`,
  `[[wiki/methods/bayesian-optimization|bayesian optimization]]`.
- Graph node ids equal these wikilink paths.

## Front-matter contract

Every wiki page starts with YAML front-matter containing at least `type`
(lab | method | material | instrument | software | concept | overview),
`name`, and `generated`. Typed relations:

- labs: `uses_methods`, `uses_materials`, `uses_instruments`,
  `uses_software`, `collaborates_with`, `paper_count`
- methods: `category` (when known), `aliases`, `used_by_labs`,
  `paper_count`, `stages` ({stage id: mentions}, when stage data exists)
- other entities: `aliases`, `used_by_labs`, `paper_count`
- concepts: `methods` (member fine-grained methods)

## Operations

- **ingest** — rebuild the vault after new papers / extraction runs:
  run the pipeline (entity extraction, lab mapping), then
  `cd backend && python -m app.scripts.export_llm_wiki`.
  Each run appends one `ingest` entry to log.md; wiki pages are regenerated
  in place.
- **query** — answering questions from this vault: read `index.md` first to
  find the right page(s); follow wikilinks; `wiki/overview.md` has the
  headline numbers. Grep is reliable: pages are plain Markdown.
- **lint** — consistency checks: every `[[target]]` should resolve to
  `<target>.md` under the vault root; every wiki page should be listed in
  `index.md`; front-matter must parse as YAML. The exporter regenerates a
  consistent state, so a failing lint means hand edits or a stale export —
  re-run ingest.
