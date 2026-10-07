# Zotero Tier 1 SDL Cutover Runbook

## Stage 1 authority boundary

Stage 1 uses only the `SDL keywords (tier 1)` collection in the AC SDL papers
Zotero group. Zotero is the sole paper authority for the backend.

- Group ID: `6631056`
- Tier 1 collection key: `ZYENR62J`
- Corpus source: `STRICT_SDL_KEYWORD`
- Tier 2: disabled
- AC-member publication collection: excluded
- External discovery: disabled as a paper-ingestion route
- AC author, partner-institution, funding, citation-network, and AC attribution
  signals: disabled for classification and learning
- Legacy `data/eval_labels.csv`: not used because its scope is `AC_REPORTING`,
  not strict SDL ground truth

The live Zotero audit on 2026-08-06 observed 885 collection items and 829
deduplicated bibliography records. Stage 1 excludes the 431 records that have
no stored PDF attachment. The remaining 444 PDF attachment records map to 427
raw parent items and 398 papers after exact DOI deduplication. The cutover
command must fail if the PDF-backed unique count is no longer 398; a count
change requires a new audit and a newly frozen split manifest.

A PDF attachment record is not proof that Zotero currently stores the file
bytes. Before production replacement, every one of the 398 papers must have a
complete Markdown document and checksum manifest in S3. Records that have only
attachment metadata must not be exposed as the active application corpus.

## RDS snapshot provenance

`paper-attribution-dev-pre-zotero-20260805` is a snapshot of
`paper-attribution-dev-db`. A read-only audit found 10,715 legacy papers:

- 9,283 Scopus / `scopus_batch` Tier 2 rows
- 1,026 Scopus / `scopus_batch` Tier 1 rows
- 406 `ac_gold` rows
- 0 Zotero-source rows

This snapshot is a full rollback artifact only. It is not a Stage 1 data source
and must never be restored into an active Stage 1 database unless the entire
Zotero cutover is being rolled back together with the application version.

## Required configuration

Use a read-only Zotero API key and the immutable Tier 1 collection key:

```bash
export PAS_ZOTERO_API_KEY=...
export PAS_ZOTERO_GROUP_ID=6631056
export PAS_ZOTERO_TIER1_COLLECTION=ZYENR62J
export PAS_ZOTERO_TIER2_COLLECTION=
export PAS_ZOTERO_SOURCE_ONLY=true
export PAS_SDL_STAGE1_ONLY=true
export PAS_SDL_STAGE1_TRAINING_THROUGH_ROUND=0
export PAS_SDL_STAGE1_DERIVED_VIEWS_ENABLED=false
export PAS_SDL_STAGE1_DESCRIPTIVE_ANALYTICS_ENABLED=false
export PAS_ACTIVE_LEARNING=0
export PAS_LEARNED_CLASSIFIER=0
```

The API key is supplied to ECS from AWS Systems Manager Parameter Store. It
must not be committed to the repository or included in logs.

## Full-text data path

The worker downloads each Zotero PDF to Fargate ephemeral storage, converts it
to Markdown with `pdf-inspector`, and deletes the temporary directory when the
task ends. PDF bytes are never uploaded to S3.

- `raw/zotero/.../document.md` is the only durable raw full text.
- `manifests/zotero/.../document-manifest.json` records Zotero versions,
  source/Markdown checksums, conversion provenance, and the idempotency key.
- `manifests/zotero/runs/.../batch-manifest.json` is written last as an
  acquisition record. It does not trigger ETL.
- Only an explicitly promoted
  `manifests/zotero/etl-ready/.../batch-manifest.json` starts Markdown ETL.
- ETL verifies checksums, persists sections/chunks, extracts SDL evidence and
  entities, rebuilds embeddings, and classifies only the Tier 1 corpus.
- Stage 1 ETL does not load AC rosters, partner institutions, or SDL lab-member
  mappings.

For PDFs downloaded by the Zotero desktop app, use the same S3 contract
without uploading source PDF bytes. `pdf-inspector` remains the fast path;
Docling/RapidOCR is invoked only when the inspector rejects a PDF as requiring
OCR:

```bash
python -m app.scripts.export_local_zotero \
  --storage-root /path/to/Zotero/storage \
  --all-tier1 \
  --ocr-backend docling
```

Install `backend/requirements-ocr.txt` in a dedicated OCR worker environment.
Every OCR page must contain substantive text, conversion must complete without
errors, and the output must contain no replacement characters before Markdown
can be persisted.

## Frozen review and classifier protocol

Run this only after all 398 PDF-backed, deduplicated Tier 1 papers have verified
Markdown in S3 and the same corpus is in RDS:

```bash
python -m app.scripts.prepare_sdl_stage1_batches --expected-total 398 --publish --json
```

The default manifest assigns every paper exactly once:

| Role | Batch size | Use |
|---|---:|---|
| Fixed validation | 60 | Evaluate after every training round |
| Frozen final test | 80 | Open once, after model selection |
| Training round 1 | 60 | First human-labelled training batch |
| Training round 2 | 60 | Added to round 1 labels, then retrain from scratch |
| Training round 3 | 60 | Added to rounds 1-2, then retrain from scratch |
| Unlabelled reserve pool | 78 | Not placed in the current review queue |

All 320 selected papers receive strict SDL human review. Accepted judgements
map to classifier labels as follows:

- `CONFIRMED_SDL` and `PROBABLE_SDL` -> `SDL_FIELD_RELEVANT`
- `SDL_ADJACENT` -> `ADJACENT`
- `NOT_SDL` -> `EXCLUDE`
- `INSUFFICIENT_EVIDENCE` -> no training/evaluation label; obtain full text and
  review again

Each conclusive Stage 1 review must use `judgement_basis=STRICT_SDL`.
`human_label`, AC relevance, and AI-for-science judgements are rejected in this
stage. Training reads only completed labels assigned to training rounds.
Validation reads only the fixed 60-paper validation split. The 80-paper final
test endpoint stays sealed unless `release_frozen_test=true` is explicitly
provided.

At each planned boundary, train a separate candidate with an explicit round
limit; the default value `0` exposes no training labels:

```bash
python -m app.scripts.train_learned_classifier --stage1-through-round 1
python -m app.scripts.train_learned_classifier --stage1-through-round 2
python -m app.scripts.train_learned_classifier --stage1-through-round 3
```

These commands retrain from scratch on cumulative batches of 60, 120, and 180
labels and write separate candidate artifacts. Compare each on the same fixed
60-paper validation set. Do not promote a candidate or open the final test set
automatically.

Review Queue and People Insights remain quarantined while
`PAS_SDL_STAGE1_DERIVED_VIEWS_ENABLED=false`. Network Growth may expose the
separate full-text-backed descriptive preview when
`PAS_SDL_STAGE1_DESCRIPTIVE_ANALYTICS_ENABLED=true`. That preview uses
front-matter affiliation mentions only; it does not use classifications,
reviews, AC-member seeds, or author-level institution assignments.

## Safe cutover sequence

1. Temporarily set the ECS autoscaling target minimum to zero, then stop the
   backend and verify both desired and running counts are zero. Merely setting
   the service desired count to zero is insufficient while its autoscaling
   minimum remains one: the old task definition can be relaunched and re-seed
   the legacy corpus during cutover.
2. Verify the rollback snapshot is `available` and record its exact identifier.
3. Dry-run Tier 1 retrieval without changing RDS:

   ```bash
   python -m app.scripts.sync_zotero --dry-run --tier tier1 --json
   ```

   Require `seen_items=885`, `bibliographic_papers=829`,
   `pdf_backed_papers=398`, `pdf_backed_raw_items=427`,
   `pdf_attachment_rows=444`, `papers_without_pdf=431`, and
   `unique_papers=398`, or stop and re-audit the changed Zotero collection.

4. Acquire and convert PDFs outside the production database. Process Zotero
   Web API files and local Zotero storage incrementally, with classification
   disabled. The complete training corpus still requires 398 unique
   `document.md` objects. A descriptive preview may use the currently verified
   manifest-backed subset if its partial scope is shown explicitly.
5. For the 177-paper descriptive preview, replace all application data with
   unique ready S3 manifests only and publish one replay batch. Do not use
   `--limit`, Tier 2, classification, or AC-member data:

   ```bash
   python -m app.scripts.sync_zotero \
     --tier tier1 \
     --manifest-backed-only \
     --publish-replay-batch \
     --replace-corpus \
     --backup-reference rds-snapshot:<fresh-pre-preview-snapshot> \
     --json
   ```

6. Replay the emitted 177-document Markdown batch into the replacement
   database without `--postprocess`, then verify all 177 papers have full text
   and the institution extraction audit is populated.
7. Continue local/API acquisition toward 398. Only after the complete corpus
   exists should the fixed split be regenerated and the Tier 1 corpus be
   classified with the AC-independent Stage 1 rules.
8. After controlled training and validation, refresh the review queue. Keep
   automatic model evolution disabled; retrain only at the planned round
   boundaries.
9. Register the Stage 1 task definition while the service remains at zero,
   explicitly point the stopped service at that revision, and re-run the
   fail-closed corpus audit. Start exactly one new-revision task only after the
   audit passes. Restore the autoscaling minimum to one only after live API
   provenance and count checks pass. The backend refuses to start if RDS is
   empty, mixed, legacy, Tier 2, or contains AC-derived
   seed/classification state.

## Acceptance checks

For the 177-paper descriptive preview, the RDS audit must show:

- total papers and full texts: 177
- `source=zotero`: 177
- `provenance=zotero_group`: 177
- `retrieval_tier=tier1`: 177
- `corpus_sources=[STRICT_SDL_KEYWORD]`: 177
- selected unique S3 Markdown manifests: 177
- Tier 2, Scopus, `ac_gold`, and `AC_MEMBER_CORPUS`: 0
- AC-core rows, AC-member flags, partner institutions, SDL lab-roster links,
  and AC attribution classifications: 0
- classifications and review-queue rows: 0
- readiness phase: `analysis_preview`

Also verify `/health`, the paper/full-text count, one Markdown artifact
checksum, one ETL result, the institution-comparison audit, and that
classification-derived routes remain sealed.

## PDF-to-Markdown pilot result

The 2026-08-06 acquisition audit found 177 unique Tier 1 papers with verified
Markdown in S3. Of 178 document-manifest versions, 168 were acquired from local
Zotero storage and 10 from the Zotero Web API; all durable source objects are
Markdown, not PDF. The converters were `pdf-inspector` for 156 versions and
Docling/RapidOCR for 22 OCR versions.

The remaining 221 deduplicated papers all have Zotero attachment metadata, but
their authenticated `GET /groups/6631056/items/{attachment}/file` requests
return HTTP 404. A `HEAD` response of 200 is not a valid availability check.
The local Zotero database marks 268 attachment rows as pending download, while
only 190 raw Tier 1 attachment files (177 deduplicated papers) exist under the
configured local storage root. Opening one missing attachment did not create a
local file.

The original publisher URLs retained by `imported_url` attachments are not a
reliable fallback; an audited Wiley sample returned HTTP 403. Expanding the
corpus therefore requires the actual files to be downloaded into local Zotero
storage or uploaded to Zotero group file storage. Adding attachment records or
URLs alone is insufficient. The 177 verified documents may be used for the
explicitly labelled descriptive preview. Do not train, validate, or promote
the classifier as if this partial subset were the complete 398-paper corpus.

## Rollback

If validation fails, stop writers, restore
`paper-attribution-dev-pre-zotero-20260805` into a replacement database,
redeploy the previous application version, and verify the legacy counts before
reopening service. Restoring only the old database while leaving the Stage 1
application active is not a valid rollback.
