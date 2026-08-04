# RAG Autoresearch Program

## Goal

The current RAG task is attribution evidence retrieval: when a paper has known
funding, methodology, or SDL figure evidence, search should retrieve the exact
fulltext chunk that supports that attribution. This program is also the base
for future agentic QA RAG because it separates data coverage, task creation,
retrieval ranking, and accept/reject gates.

## Inputs

- `paper_chunks`: fulltext chunks with `indexed_text`, embeddings, section
  type, and paper metadata.
- `paper_evidence`: evidence rows linked to `chunk_id`.
- `HybridIndex.search`: BM25/cosine hybrid retrieval with configurable `alpha`,
  `top_k`, and `section_types`.

## Fixed Tasks

For each evidence row with a `chunk_id`, the evaluator creates one retrieval
task:

- `funding_acknowledgement`: query for AC funding and acknowledgements.
- `sdl_methodology`: query for self-driving lab and closed-loop methods.
- `figure_caption_sdl`: query for SDL platform figure captions.

The expected answer is the linked evidence chunk. The evaluator records whether
that chunk appears in top-k and at which rank.

## Metrics

- `recall_at_k`: fraction of tasks where the known evidence chunk appears in
  top-k.
- `mrr`: mean reciprocal rank for hit tasks.
- `average_rank`: average hit rank.
- `coverage.fulltext_paper_rate`: fraction of papers with fulltext.
- `coverage.non_abstract_chunks`: confirms retrieval is using fulltext chunks,
  not just abstracts.

## Command

```bash
cd backend
uv run python -m app.scripts.run_rag_autoresearch --k 5 --alpha 0.5 --json
```

Useful variants:

```bash
cd backend
uv run python -m app.scripts.run_rag_autoresearch --k 10 --alpha 1.0 --json
uv run python -m app.scripts.run_rag_autoresearch --section-type acknowledgements --json
```

## Iteration Loop

1. Fetch and ingest fulltexts.
2. Extract evidence and build embeddings.
3. Run the RAG autoresearch command.
4. If coverage fails, fix fulltext ingestion first.
5. If coverage passes but recall fails, inspect `task_results` misses and tune
   query templates, chunk prefixes, section filters, `alpha`, or reranking.

## Path To Agentic QA RAG

The same harness can be extended by replacing fixed evidence queries with QA
tasks:

- question
- expected supporting chunk IDs
- expected answer facts
- answer-level grading

The retrieval gates should remain separate from answer-generation gates so a
QA miss can be traced to retrieval, synthesis, or citation grounding.
