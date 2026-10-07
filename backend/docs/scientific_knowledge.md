# Scientific Paper Knowledge and Domain Adaptation

This subsystem compiles full-text papers into paper-scoped scientific knowledge and a reproducible domain-training corpus. It is intentionally independent of attribution and relevance classification.

## Scope

Each compiled paper contains exactly four entity collections:

- `method`
- `material`
- `instrument`
- `software`

Every entity is linked to a paper section, chunk ID, evidence excerpt, and extraction confidence. Institution and affiliation entities are not part of this ontology. References and acknowledgements are excluded from entity compilation and training-text export.

The current compiler is a deterministic vocabulary matcher over `data/sdl_entities.yaml`. It is auditable and reproducible, but it does not discover terminology missing from that vocabulary. An empty entity list means "no vocabulary-backed match," not proof that the paper contains no entity of that type.

The only assertion currently emitted is:

```text
paper --reports_scientific_entity--> method|material|instrument|software
```

This conservative relation is deliberate. Two entities appearing in one paper do not prove that a method uses a material, instrument, or software package. Those richer relations require an explicit relation extractor with sentence-level evidence and are not inferred from co-occurrence.

## Classification wall

The builder and exporter read only these tables:

- `papers`
- `paper_chunks`
- `scientific_knowledge_records`

They do not read `paper_classifications`, `human_reviews`, `institutions`, lab links, or attribution scores. The generated records and corpus therefore contain no classification labels or institution entities.

The exported paper text is intentionally not redacted. A body-text chunk may naturally mention an institution; the exclusion applies to the structured entity ontology and to classification-derived metadata, not to alteration of the scientific source text.

## Build lifecycle

Apply the migration, import Markdown full text, then compile scientific knowledge:

```bash
cd backend
alembic upgrade head

# Classification remains disabled unless --postprocess is explicitly supplied.
python -m app.scripts.run_zotero_markdown_etl \
  --manifest-key path/to/manifest.json

python -m app.scripts.build_scientific_knowledge --json
```

The compiler is content-addressed. It hashes the paper title, abstract, year, and eligible chunks. An unchanged paper is reported as `unchanged` and its compiled timestamp is preserved.

Restrict a run when validating a small sample:

```bash
python -m app.scripts.build_scientific_knowledge \
  --paper-id PAPER_ID --limit 10 --json
```

Read a compiled record through the API:

```text
GET /kb/papers/{paper_id}/scientific-knowledge
```

The endpoint is read-only and returns `404` until the paper has been compiled. It never compiles on request.

## Domain training corpus

Export compiled papers as deterministic JSONL:

```bash
python -m app.scripts.export_domain_training_corpus \
  --output-dir ../outputs/domain-training-corpus --json
```

The export writes:

- `domain_corpus.jsonl`: one provenance-bearing record per unique eligible chunk;
- `manifest.json`: schema version, paper and record counts, exact-duplicate count, section distribution, and corpus SHA-256.

The exporter deduplicates exact chunk content and only rewrites files whose bytes changed. Each text record carries its paper ID, title, year, section, chunk ID, content hash, and the compiled knowledge-record hash.

Export fails closed if paper text, the scientific vocabulary, the schema, or the compiler version changed after knowledge compilation. Re-run `build_scientific_knowledge` before exporting rather than pairing current source text with stale knowledge provenance.

This is domain-adaptive pretraining material, not a classification dataset and not an instruction-tuning dataset. A separate, evidence-reviewed task generator would be required for supervised extraction or question-answer training.

## Tokenizer fragmentation audit

Retrieval tokenization and model tokenizer adaptation are separate decisions. PAS `DomainTokenizer` protects phrases for retrieval; it does not change a model vocabulary or embedding matrix.

Audit the exported text before changing a pretrained tokenizer:

```bash
# Pipeline smoke check; this is not a model-tokenizer measurement.
python -m app.scripts.audit_scientific_tokenizer \
  --corpus ../outputs/domain-training-corpus/domain_corpus.jsonl \
  --tokenizer domain-retrieval

# Real pretrained tokenizer. Local files are required by default.
python -m app.scripts.audit_scientific_tokenizer \
  --corpus ../outputs/domain-training-corpus/domain_corpus.jsonl \
  --tokenizer huggingface \
  --model path/to/local/model-tokenizer \
  --output ../outputs/domain-training-corpus/tokenizer-audit.json
```

Use `--allow-download` only when network retrieval is intended. The audit separates:

- multi-token domain phrases, which can be normal for multi-word terminology;
- subword fragmentation, where a term uses more tokenizer pieces than lexical words.

Domain terms are measured with a leading-space, mid-text context because many pretrained tokenizers encode a word differently at the beginning of a document.

Tokenizer extension should only follow a material, repeated fragmentation result on representative corpus terms. Adding tokens also requires resizing and training their embeddings, continued pretraining, checkpoint/version isolation, and evaluation against the unchanged base tokenizer. The audit does not automatically recommend or perform those model changes.

## Recommended model path

For the current corpus size, use the assets in this order:

1. evidence-linked KB and RAG over compiled records;
2. tokenizer fragmentation audit on the chosen base SLM;
3. domain-adaptive continued pretraining or parameter-efficient adaptation on `domain_corpus.jsonl`;
4. evidence-grounded supervised tasks only after their answers and citations are reviewed;
5. tokenizer vocabulary changes only if the measured benefit justifies incompatibility with the base tokenizer.

The repository builds and audits the knowledge and corpus layers. It does not claim to train or validate a production SLM yet.
