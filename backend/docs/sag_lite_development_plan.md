# SAG-lite Development Plan

This plan tracks the remaining work after the first no-migration SAG-lite slice.

## Completed slice

- Derived event trail from existing `PaperEntity`, `PaperChunk`, `Paper`, and `PaperLabLink` rows.
- KB entity pages now expose `events` in `/kb/entities/{entity_type}/{name}`.
- KB Markdown export renders a `SAG-lite Event Trail` section for entity pages.
- Tests cover derived events, KB API serialization, and Markdown export output.

## Remaining work

1. Persist event nodes.
   - Add `paper_events` with `paper_id`, `event_type`, `stage`, `source_chunk_id`, `snippet`, and confidence.
   - Add `paper_event_entities` for event-to-entity links.
   - Migration risk: low to medium; keep derived service as fallback during rollout.

2. Add event extraction.
   - Promote high-confidence `PaperEntity.usage_snippet` rows into events.
   - Use `PaperProposition` rows for explicit events such as `uses_method`, `funded_by`, `cites`, and `belongs_to_topic`.
   - Deduplicate repeated event text within the same paper.

3. Add SAG-style retrieval.
   - Query path: text query -> matching entities/propositions -> events -> related papers/chunks.
   - Return a trace showing entity matches, event hops, and source chunks.
   - Keep this parallel to `HybridIndex.search()` until evaluation shows better recall.

4. Add API endpoints.
   - `GET /kb/entities/{type}/{name}/events`
   - `GET /retrieval/sag?q=...`
   - Include pagination before exposing corpus-wide event listings.

5. Add frontend views.
   - Entity page event timeline.
   - Retrieval trace panel showing `chunk -> event -> entity -> paper` hops.
   - Lab profile section for top event types by stage.

6. Evaluate before replacing ranking.
   - Add recall tests for cross-paper method transfer questions.
   - Compare SAG-lite retrieval against current BM25/cosine/RRF retrieval.
   - Only blend SAG scores into ranking after measurable improvement.

## Explicit non-goals for the first slice

- No dependency on the external SAG codebase.
- No database migration.
- No replacement of the existing RAG index.
- No frontend change until the event API shape is stable.
