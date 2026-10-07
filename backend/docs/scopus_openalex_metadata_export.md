# Scopus → OpenAlex metadata export

This export treats Scopus as the corpus boundary and OpenAlex as a metadata
enrichment source. OpenAlex results never add papers that were not returned by
the Scopus query.

## Query

The default query is the exact written query supplied for this dataset:

```text
(ALL("self-driving lab*") OR ALL("materials acceleration platform*") OR ALL("autonomous lab*")) AND PUBYEAR > 2016 AND PUBYEAR < 2028
```

The supplied screenshot instead shows `ALL("self-driving lab*")` combined
with an affiliation filter for Toronto. These are different corpora. The
script records the exact query in every CSV row and in the manifest so the two
cannot be silently confused.

## Credentials

Create an Elsevier developer API key. Read secrets without echoing them or
putting their values in shell history, then expose them to the process:

```bash
read -rsp "Elsevier API key: " PAS_ELSEVIER_API_KEY; echo
export PAS_ELSEVIER_API_KEY
read -rsp "Elsevier institutional token (optional): " PAS_ELSEVIER_INSTTOKEN; echo
export PAS_ELSEVIER_INSTTOKEN
read -rsp "OpenAlex API key (optional): " PAS_OPENALEX_API_KEY; echo
export PAS_OPENALEX_API_KEY
export PAS_OPENALEX_MAILTO="you@example.com"
```

Do not put keys on the command line or commit them to the repository.

## Run

From `backend/`:

```bash
python -m app.scripts.fetch_scopus_openalex_metadata
```

If Scopus was exported from an authenticated browser session, the same
OpenAlex enrichment can run without an Elsevier API key:

```bash
python -m app.scripts.fetch_scopus_openalex_metadata \
  --scopus-csv /path/to/scopus.csv \
  --query 'ALL("self-driving lab*") AND AFFIL(Toronto)'
```

English and Simplified Chinese Scopus column labels are both supported. The
input CSV SHA-256 is recorded in the output manifest.

By default, artifacts are written to
`reports/scopus-175-openalex-metadata/`:

- `scopus_results.jsonl`: normalized Scopus identifiers plus the original API entry;
- `openalex_metadata.jsonl`: complete OpenAlex work objects aligned to Scopus rows;
- `merged_metadata.csv`: flattened metadata for analysis;
- `match_audit.csv`: one-row-per-paper DOI/title match audit;
- `manifest.json`: query, counts, match coverage, file sizes, and SHA-256 hashes.

The script warns if Scopus no longer reports exactly 175 results. That warning
is intentional: Scopus is updated continuously, and the written query and the
screenshot query are not equivalent.
