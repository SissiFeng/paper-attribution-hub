# Author paper monitor

Four-hour OpenAlex author monitoring, durable deduplication, direct PAS ingestion,
and a native Slack App. Members of the installed workspace subscribe by opening
AC Papers or running `/papers start`; each receives their own private messages.
Read [MULTIUSER.zh.md](MULTIUSER.zh.md) for colleague onboarding and personal delivery,
and [FRESHNESS.zh.md](FRESHNESS.zh.md) for backfill, alerts and mailbox setup.
`REVIEW_RESULT.zh.md` records the initial pilot.

## Slack pilot

The watchlist contains all 82 AC members: 81 verified profiles are active; Alan
Veerman remains visible as needing identity review. The registry is in DynamoDB;
`config/ac_roster.json` preserves the initial identity evidence. The first 90-day
collection saved 163 unique papers into PAS without announcing historical papers.

Open **AC Papers → Home** to subscribe, see the authors, send a test, or start/pause
your paper updates. The administrator's **Add an author** accepts a name or ORCID, shows real
OpenAlex candidates, and requires an explicit selection. Existing profiles are
not added twice. Author Pause stops that author's collection; Pause updates keeps
four-hour collection, PAS storage and other members' notifications running.

New papers are sent as private cards after PAS storage; a separate Monday recap
contains a thread of papers already sent in the previous week. Cards include links,
publication details, tracked authors, relevance buttons and an incorrect-author
report. Feedback is saved for review, not used as an automatic scientific label.
Optional LLM summaries, Scholar email, images and inferred collaborations are not
enabled in this pilot.

Commands: `/papers test`, `/papers review`, `/papers start`, `/papers pause`, `/papers status`,
`/papers authors`, `/papers add`. `/papers digest` sends another labelled preview;
it does not consume the weekly publication queue.

## Connecting another installation

Deploy `deploy/slack_aws.py --apply`, then open its returned HTTPS endpoint for the
installation guide and manifest. Install the app with `chat:write`, `commands`,
`im:write`; it does not request message-history permissions. Run:

```bash
backend/.venv/bin/python tools/author-paper-monitor/deploy/connect_slack.py
```

The helper reads the bot token and signing secret through hidden prompts, verifies
the bot identity, saves them as an SSM SecureString and prints a short-lived,
single-use connection code. Run `/papers connect CODE` in Slack. The code binds the
requesting operator and opens a private DM, regardless of where the command was
entered. Then `/papers start` enables the operator's subscription. Subscribe to
the `app_home_opened` bot event at the same `/slack` endpoint; it requires no new
OAuth scope. Other members open AC Papers to subscribe without a connection code.
No group channel can be used as the delivery target in personal mode. Each
deployment currently supports one installed workspace; this is not multi-workspace OAuth hosting.

Slack signs every request; API Gateway/Lambda verifies the raw body and timestamp,
then queues slow work in SQS. DynamoDB stores the watchlist, operator settings and
personal subscriptions and feedback. This uses the existing AWS environment without a continuously connected
Socket Mode server. Slack retries are deduplicated; uncertain sends are retained
for inspection rather than replayed blindly.

## Local use

Python 3.10+ for the standalone monitor; the PAS integration uses the backend
runtime (Python 3.12, SQLAlchemy). The production ECS task reuses the running
backend image, pinned by digest, with a checksummed monitor code bundle.

```bash
cp authors.example.csv authors.csv
python -m paper_monitor resolve authors.csv
python -m paper_monitor run --authors authors.csv --db state.db --dry-run
```

Resolve all authors before polling. An ORCID response is accepted only if its
reported name or an alternative name contains the supplied name tokens. Name-only
candidates and mismatches require manual selection. This check catches erroneous
ORCIDs, but is not a substitute for verifying affiliations and namesakes. IDs in
`openalex_ids` are explicit operator choices. The example's Bo Wang is deliberately
unresolved. The optional arXiv query is not enabled by default.

**Local dry-run changes the specified local state database** but does not write to
PAS or Slack. Use a separate database for testing. First successful run establishes
a baseline, including when zero papers are returned. Subsequent new papers become
pending. `--post-backlog` on a fresh database queues the initial window instead.
It does not convert existing seeded rows. Outbox contains at most the current send
limit, while the complete queue remains in SQLite.

## State and deduplication

Strong identifiers (all known DOI aliases, arXiv ID and OpenAlex work ID) precede
title matching. Different journal DOIs or different arXiv IDs are not merged by
title alone. A title fallback requires a shared author; generic editorial/reply
headings are excluded. arXiv-to-journal title matches preserve both DOI aliases.
Changed titles without any shared strong identifier can still cause duplicates.

Standalone Slack states: `seeded`, `pending`, `sending`, `posted`, `irrelevant`.
Subscriber mode retains one shared catalogue (`available` after queuing) and
independent `(paper_id, user_id)` delivery states and weekly recap receipts.
PAS receipts are independent: every newly discovered paper is saved, including
papers that the optional Slack relevance filter rejects. Newly created baseline
rows are imported too, but never notified. Source outages fail the run; any incomplete first collection
aborts before baselining. Unresolved authors also fail before collection.

`PAS_MONITOR_INGEST=1` enables integration inside the backend runtime.
`PAS_MONITOR_MODE=main` inserts into `papers` with source/provenance
`author_monitor`, authors and raw metadata. Existing DOI records are reused,
without overwriting curated data or classification. Both `PAS_SDL_STAGE1_ONLY`
and `PAS_ZOTERO_SOURCE_ONLY` must be false. `inbox` mode uses the existing
`discovery_candidates` queue and preserves strict Zotero corpus policy.

No full text or classification is fabricated. Metadata ingestion does not establish
scientific relevance; normal PAS curation/full-text workflows remain separate.

## Delivery and uncertainty

The Slack App loads its token from SSM and derives each private destination from
the authenticated member's subscription in DynamoDB. Production uses
`SLACK_DELIVERY_MODE=subscribers`: up to 20 new paper cards per member per run,
with a shared budget of 200 new cards and a rotating recipient cursor. Excess
cards remain queued for subsequent four-hour runs. Weekly recaps have separate
receipts and are outside the new-card budget. New subscribers receive discoveries
from their enrollment time; resuming a paused subscription retains its backlog.
See [MULTIUSER.zh.md](MULTIUSER.zh.md) for recipient-specific recovery. The original
`immediate_weekly` mode remains available for single-recipient standalone use.
The legacy weekly-only mode remains available; its uncertain parent uses:

```bash
python -m paper_monitor reconcile-digest --db state.db --thread-ts 1234567890.123456
# Only when the parent was definitely not received:
python -m paper_monitor reconcile-digest --db state.db --retry
```

Use an isolated copy for inspection; cloud state changes must hold the existing
database advisory lock. Do not upload an edited local state over a running task.

The original webhook transport remains available for standalone use:

Set `SLACK_WEBHOOK_URL` to the selected channel's incoming webhook. Only a successful
HTTP response containing `ok` is accepted. HTTP 4xx/429 leaves the paper pending;
transport errors, 5xx, unexpected responses or a crash after beginning a send leave
it `sending`. Webhook POSTs are not transparently retried. Webhooks do not offer
exactly-once delivery; inspect the channel before explicitly reconciling:

```bash
python -m paper_monitor reconcile --db state.db --id 42 --delivered
# Or, only after confirming it was not received:
python -m paper_monitor reconcile --db state.db --id 42 --retry
```

Other pending messages can proceed on later runs; unresolved sending rows keep
the job's exit status non-zero. Messages are limited to 20 per run and spaced 1.1s.

## AWS deployment

Use `deploy/aws.py` with the backend Python environment. It generates a reviewable
CloudFormation template, validates it, and only mutates resources with `--apply`.
The stack provisions an ECS task, least-privilege roles, EventBridge four-hour schedule,
CloudWatch logs, SQS failure queue and a queue alarm. `deploy/health_aws.py --apply`
adds an independent 15-minute watchdog and AWS failure-event routing to private
Slack alerts. No email/SNS subscription is configured. S3 uses the existing versioned private artifacts bucket.

```bash
# From the repository root; inspect deploy/build/stack.json first.
backend/.venv/bin/python tools/author-paper-monitor/deploy/aws.py
# Isolated cloud dry-run; no main-paper inserts or Slack messages:
backend/.venv/bin/python tools/author-paper-monitor/deploy/aws.py --apply \
  --authors /absolute/path/verified-authors.csv \
  --prefix author-monitor/validation --run dry-run
# Production setup with the Slack App registry (Slack may remain paused):
backend/.venv/bin/python tools/author-paper-monitor/deploy/aws.py --apply \
  --authors tools/author-paper-monitor/config/ac_authors.csv \
  --slack-app paper-attribution-dev-slack --jev-shadow --run baseline --enable-schedule
```

`--open-corpus` changes only the two corpus-policy flags on a new revision of the
currently running backend task; it does not deploy unrelated local code. The prior
task ARN is printed for rollback. Do not restore strict mode after inserting mixed
corpus records without first planning a corpus migration. Terraform dev settings
also reflect the open-corpus choice to prevent accidental reversion.

The schedule is disabled unless explicitly enabled with resolved production
authors. Collection can run before Slack is connected or while notifications are
paused. It runs at 00:17, 04:17, 08:17, 12:17, 16:17 and 20:17 UTC
(Toronto local time shifts with daylight saving). Production configuration and state live under
`s3://<bucket>/author-monitor/production/`. Cloud dry-run requires a separate prefix.

A PostgreSQL advisory lock serializes jobs and is released on connection death.
Every SQLite commit is checkpointed to S3, including `sending` before calling Slack.
An S3 failure after sending leaves the remote checkpoint uncertain, requiring
reconciliation rather than automatic duplicate delivery. Each worker is bounded to
25 minutes. Monitor logs are `/ecs/paper-attribution-dev-author-monitor`.

Cloud reconciliation uses an ECS container command override with the deployed
bootstrap followed by `--reconcile-id 42 --recipient U0123456789 --delivered`
(or `--retry`) for the affected subscriber. It must use the
same production prefix. Do not edit state.db while a job holds the advisory lock.

## Configuration

| Environment variable | Default | Purpose |
| --- | --- | --- |
| OPENALEX_API_KEY | unset | Optional API key; recommended for larger lists |
| CONTACT_EMAIL | unset | API contact in query/User-Agent |
| LOOKBACK_DAYS | 90 | Publication-date rescan window |
| MAX_POSTS_PER_RUN | 20 | Standalone send limit; subscriber mode uses 20 per member and 200 total |
| DEEP_LOOKBACK_DAYS | same as LOOKBACK_DAYS locally; 365 in AWS | Weekly wider publication-date rescan |
| SLACK_DELIVERY_MODE | legacy weekly locally; subscribers in AWS | Independent private cards and Monday recap per subscriber |
| SCHOLAR_CONFIG_PARAMETER | set by AWS deployment | Verified encrypted mailbox configuration |
| SLACK_WEBHOOK_URL | unset | Secret incoming webhook |
| SLACK_BOT_TOKEN / SLACK_CHANNEL_ID | unset | Slack App token / private DM target; cloud settings supply these |
| PAS_MONITOR_INGEST | unset | Set to 1 to persist new papers in PAS |
| PAS_MONITOR_MODE | inbox | main or inbox |
| ANTHROPIC_API_KEY | unset | Optional summary/relevance filter |
| ANTHROPIC_MODEL | claude-haiku-4-5 | Optional model alias |
| IMAP_HOST/USER/PASSWORD | unset | Optional Scholar-alert mailbox |
| IMAP_FOLDER | INBOX | Mailbox read without marking messages read |
| JEV_MODE | off | off or shadow; no automatic ranking/filtering mode |
| TYPESAFE_API_KEY | unset | Local TypeSafe key; AWS loads encrypted SSM configuration |
| JEV_MODEL | jev-1.13.0 | Pinned evaluation contract; other versions rejected |
| JEV_FOCUS | AC lab automation / scientific discovery | Public research focus, at most 2,000 characters |
| JEV_CONFIG_PARAMETER | unset | AWS SSM SecureString JSON; set by `--jev-shadow` deployment |

For a dedicated OpenAlex quota, run `deploy/configure_openalex.py`; it validates a
free API key and stores it as an SSM SecureString. The cloud runner loads it without
a redeployment. Anonymous calls worked in AWS, but the local shared IP exhausted
its daily quota during roster research; a dedicated key is recommended.

The LLM fails open. A changed brief/model/enabled setting reconsiders records marked
irrelevant. Unclassified new papers are retained in PAS regardless of Slack filtering.

## Jev shadow evaluation

The first phase proposes a reading priority (0–4) and one next step: initial triage
from metadata, consult the full paper, or human review. Only a bounded title and
abstract plus a public research focus go to TypeSafe. The actual delivery,
paper inclusion, PAS classification and full-text acquisition remain unchanged.
All eight advisory workflows are now integrated: author identity, publication
versions, reading priority, analysis routing, question routing, answer evidence,
human review priority, and graph-relation evidence. See the
[eight-workflow guide](JEV_ALL.zh.md) and [first-phase evaluation guide](JEV_PHASE1.zh.md).

No key is required for normal monitoring. Configure one later from a terminal at
the repository root; the key is entered invisibly, never as a command argument:

```bash
backend/.venv/bin/python tools/author-paper-monitor/deploy/configure_jev.py
# Inspect configuration without making a paid API request:
backend/.venv/bin/python tools/author-paper-monitor/deploy/configure_jev.py --status
# One live API contract check using the saved key:
backend/.venv/bin/python tools/author-paper-monitor/deploy/configure_jev.py --check
```

The helper checks one real catalogue paper before saving the key as SSM
`/paper-attribution-dev-author-monitor/jev`. The next scheduled task loads it without a
redeploy. `--focus-file /path/to/public-focus.txt` sets an optional research focus
during configuration. The collector, PAS backend and Slack author-lookup worker
can read only this exact parameter. Slack messages never contain the credential.
Missing credentials appear as “waiting for an API key” in Home, `/papers status`
and the private `/papers review` response. Regular monitoring continues.

AWS shares a durable cap of 20 attempts per UTC day across all eight workflows,
including the original reading scorer. The collector allows at most 8 reading
calls (45 seconds) plus 8 version/analysis calls (30 seconds) per run; HTTP timeouts
are 8 seconds for the original scorer and 4 seconds for new workflows. Requests
have no redirects or automatic retries. Local journals enforce their own cap. Interrupted/errors wait at least 24 hours before retry.
The independent one-paper configuration check is outside this collector cap.
Cached decisions are keyed by paper ID and a hash of metadata, rubric, focus and
model. Changes create a new decision; results never change delivery state. A
failed shadow evaluation is visible without blocking successful paper delivery.

`/papers review` shows up to three ranked papers from the evaluated subset, in a
private thread labelled experimental. Unscored papers remain visible in the export
and are never assumed irrelevant. Local exports include `jev-shadow.json` and a
blind `jev-labels.csv`. Human labels enable MAE, NDCG, full-text miss rate and Brier
score comparisons. No promotion to automatic decisions happens from these metrics.
Probabilities and API confidence are not evidence of calibration on AC papers.
`/papers decisions` or **Eight Jev workflows** in Home shows the latest decisions
and opens an administrator-only human-feedback form. Read-only suggestions use
the requesting member's own DM.
The protected PAS `/jev` API uses a separate operator credential;
`deploy/jev_admin.py` reads it from SSM without revealing it.

## Limits and validation

- The 90-day window cannot discover works indexed more than 90 days after publication.
  Increase the window or perform a controlled older-date backfill when needed.
- Adding authors/sources after initial baselining can queue their recent backlog.
- Source metadata can be wrong; ORCID, author identity and type still require care.
- Generic/mismatched-title cases favor avoiding false merges; some duplicate versions
  may consequently be announced separately.
- Scholar HTML parsing supports attribute-order changes and common prefixes but has
  only synthetic fixtures; leave IMAP disabled until tested on real alerts.
- arXiv requests are paginated and spaced by at least 3.1 seconds between pages/queries.
- The legacy GitHub Actions example is not the AWS deployment mechanism and was not
  executed. GitHub's inactive-public-repository schedule rule does not affect ECS.

Run `backend/.venv/bin/python -m pytest -q` from this folder using the relative path
`../../backend/.venv/bin/python`. Integration tests use isolated SQLite, never the
production PAS database. `ruff check --select E,F,W,B --ignore E501 .` checks code.
