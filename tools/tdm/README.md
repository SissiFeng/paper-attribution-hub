# TDM Publisher Adapters

Download full-text PDFs (or XML for Elsevier/ACS) for papers that lack PDFs,
publisher by publisher, using the sanctioned TDM routes described on the
[U of T Libraries TDM guide](https://guides.library.utoronto.ca/c.php?g=744383&p=5384621).

## Compliance reminder (from the U of T guide)

- Non-commercial research only; no sharing with third parties; no publishing.
- Do **not** upload licensed content to third-party AI platforms (e.g. ChatGPT).
- LLM analysis, where allowed, must be locally hosted / backend-facing.
- Delete data at the end of the project; cite appropriately.
- Publisher-specific notes are in each adapter's docstring and COMPLIANCE.md.

## Quick start

```bash
cd tools/tdm
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Dry run: show what each paper maps to, no downloads
python -m tdm_fetch --csv /Users/sissifeng/Downloads/lack_of_pdf_0806.csv --dry-run

# Real run — keyless publishers first (RSC + MDPI + SPIE + OA fallback, 112 papers)
python -m tdm_fetch --csv /Users/sissifeng/Downloads/lack_of_pdf_0806.csv \
    --keyless --out /tmp/pdfs
```

## API keys

Set these env vars before running so the adapters that need keys don't skip:

| Publisher | Env var | How to get |
| --- | --- | --- |
| Elsevier | `PAS_ELSEVIER_API_KEY`, `PAS_ELSEVIER_INSTTOKEN` | dev.elsevier.com (SciVal/Article Retrieval, institutional token for TDM) |
| Springer | `PAS_SPRINGER_API_KEY` | dev.springernature.com (U of T email) |
| IEEE | `PAS_IEEE_API_KEY` | IEEE contact form (full-text key) |
| Wiley | `PAS_WILEY_API_KEY` | Wiley API (LAN only) |
| ACS | `PAS_ACS_API_KEY` | contact U of T library TDM team |

All adapters cache responses in `<out>/.pas_tdm_cache/` so re-runs don't re-hit APIs.

## What it downloads per publisher

| Publisher | Route | Format |
| --- | --- | --- |
| Elsevier | Article Retrieval API | XML (TDM XML) |
| ACS | article-level XML endpoint (with API key) | XML |
| Wiley | Wiley Online Library API | PDF |
| IEEE | IEEE Xplore full-text API | PDF |
| Springer | Springer Nature Meta / full-text | PDF |
| RSC | Publisher site scrape (10-20s delay, TDMCrawler UA) | PDF (resolved from landing page) |
| SPIE | Publisher site scrape (manual-download expectations, polite) | PDF (resolved from landing page) |
| MDPI | Publisher site (bulk download allowed) | PDF (resolved from landing page) |
| PLOS | PLOS site (open access) | PDF (resolved from landing page) |
| arXiv | arXiv OA | PDF |
| OpenAlex/Unpaywall | OA fallback for any DOI | PDF |

## CLI options

```
--dry-run          plan only
--keyless          only publishers that need no API key (RSC, MDPI, SPIE, PLOS, OA)
--keyed-only       only publishers that need API keys (Elsevier, ACS, Wiley, IEEE, Springer)
--publisher rsc    one publisher only
--limit N          stop after N successful downloads
--force            ignore cache
--out DIR          output dir (default ./tdm_downloads)
```

## Output

```
<out>/
  <doi_slug>.pdf|.xml|.html   # downloaded files (one per paper)
  manifest.csv                # DOI, publisher, status, source, local file
  .pas_tdm_cache/             # HTTP cache (safe to delete)
```

## Ingest into PAS

```bash
python ingest_to_pas.py \
    --manifest /tmp/pdfs/manifest.csv \
    --downloads /tmp/pdfs \
    --fulltexts /path/to/paper-attribution-system/data/fulltexts
```

This copies each downloaded file to `data/fulltexts/<zotero_key>.<ext>` and
runs the existing ingest + embedding pipeline. Add `--no-ingest` to only copy.
