# TDM compliance checklist (U of T Libraries guide + publisher policies)

Source: https://guides.library.utoronto.ca/c.php?g=744383&p=5384621

## Before you run anything

1. You (or the project) must be a U of T researcher/student — the U of T
   institutional subscription is what grants TDM rights.
2. Purpose must be non-commercial research only.
3. Do not share licensed materials with anyone outside U of T.
4. Do not publish the materials to the web; no public database derived from
   them.
5. Do **not** upload licensed content to third-party AI platforms (ChatGPT,
   Claude web, Gemini, etc.). LLM analysis, where the publisher allows it,
   must run on a locally hosted, backend-facing model.
6. Cite material appropriately; keep DOIs in outputs.
7. Delete the data at the end of the project (per publisher retention terms).

## Per-publisher notes (from the guide / librarian notes)

| Publisher | Allowed | Route | Gotchas |
| --- | --- | --- | --- |
| Elsevier | Yes (TDM XML) | Article Retrieval API, insttoken | Data must stay on a secure Canadian server |
| ACS | Yes (XML) | ACS XML endpoint + addendum | **No AI use**; keep only for project duration |
| Springer | Yes | Springer Nature API; full TDM needs contacting them | Sign up with U of T email |
| Wiley | Yes | Wiley API | **LAN only** (on-campus) |
| IEEE | Yes | IEEE full-text API | Notify IEEE first; full-text key |
| RSC | Yes (scraping) | publisher site | Notify `ejournals@rsc.org` 2 weeks ahead; UA `TDMCrawler`; 10–20s delay |
| SPIE | Yes | publisher site | Manual-download expectations; contact to raise IP limits |
| MDPI | Yes (bulk) | publisher site | Open access |
| PLOS | Yes | publisher site | Open access |
| ACS/SPIE etc. | — | — | **AI training not allowed** for ACS/SPIE |

## Practical operating rules for this tool

- Always run with `--dry-run` first and review the manifest.
- Set API keys via environment variables (see README).
- Keep the cache dir (`/tmp/pas_tdm_cache`) out of version control.
- Do not commit downloaded PDFs/XML to the repo.
- Prefer the publisher route over the generic OpenAlex fallback: OpenAlex only
  returns open-access PDFs and should not be used to bypass paywalls.
- RSC/SPIE scraping is only for articles U of T is licensed to access; keep
  delays and volume low enough to be clearly "manual-style".
