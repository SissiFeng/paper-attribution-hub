"""Entry points.

  python -m paper_monitor resolve authors.csv
  python -m paper_monitor run --authors authors.csv --db state.db [--dry-run]
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import contextlib
import json
import os
import sys
import time
import urllib.error
from pathlib import Path

from . import arxiv, authors as authors_mod, collection_policy, crossref, openalex, relevance, scholar_email, slack, pas
from .models import Paper
from .store import Store

MAX_POSTS_PER_RUN = int(os.environ.get("MAX_POSTS_PER_RUN", "20"))


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def source_mode():
    mode = os.environ.get('MONITOR_SOURCE', 'openalex')
    if mode not in ('openalex', 'scholar'):
        raise ValueError('MONITOR_SOURCE must be openalex or scholar')
    return mode


def collect(authors: list[authors_mod.Author], since: str) -> tuple[list[Paper], list[str]]:
    """Run every configured source; a failing source is reported, not fatal."""
    if source_mode() == 'scholar':
        return [], []
    id_to_name = {i: a.name for a in authors for i in a.openalex_ids}
    arxiv_q = {a.name: a.arxiv_query for a in authors if a.arxiv_query}
    sources = [("openalex", lambda: openalex.recent_works(id_to_name, since))]
    if arxiv_q:
        sources.append(("arxiv", lambda: arxiv.recent_preprints(arxiv_q, since)))

    papers, errors = [], []
    for name, fetch in sources:
        try:
            got = list(fetch())
            log(f"[{name}] {len(got)} papers since {since}")
            papers.extend(got)
        except Exception as e:  # noqa: BLE001 - one source down must not stop the others
            errors.append(f"{name}: {e}")
            log(f"[{name}] FAILED: {e}")
    return papers, errors


def dedup_batch(papers: list[Paper]) -> list[Paper]:
    """Merge duplicates within one run (same paper via two authors/sources)."""
    with contextlib.closing(Store(Path(":memory:"))) as batch:
        for p in papers:
            hit = batch.find(p)
            if hit is None:
                batch.insert(p, "seeded")
            else:
                batch.add_ids(hit, p)
        return [p for _, p in batch.rows("SELECT id,data FROM papers ORDER BY id")]


def cmd_resolve(args) -> int:
    path = Path(args.authors)
    rows = authors_mod.load(path)
    for line in authors_mod.resolve(rows):
        print(line)
    authors_mod.save(path, rows)
    missing = [a.name for a in rows if not a.openalex_ids]
    print(f"\n{len(rows) - len(missing)}/{len(rows)} authors have OpenAlex ids.")
    return 1 if missing else 0


def cmd_run(args) -> int:
    rows = authors_mod.load(Path(args.authors))
    unresolved = [a.name for a in rows if not a.openalex_ids] if source_mode() == 'openalex' else []
    if not rows or unresolved:
        log(f"ERROR empty/unresolved author list; run resolve first: {', '.join(unresolved)}")
        return 1
    path = Path(args.db)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path) + ".lock", "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("ERROR another monitor run holds the state lock")
            return 1
        with contextlib.closing(Store(path)) as store:
            return run_locked(args, rows, store)


def run_locked(args, rows, store) -> int:
    policy_window = collection_policy.window(store)
    since = policy_window['since']
    mode = source_mode()
    # Mail alerts are queued discoveries, not a historical API baseline.
    seeding = mode != 'scholar' and not store.meta("initialized") and not args.post_backlog
    papers, errors = collect(rows, since)
    mail_cursor = None
    if scholar_email.configured():
        try:
            mail_papers, mail_cursor = scholar_email.fetch_pending(store, rows)
            papers.extend(mail_papers)
        except Exception as exc:
            errors.append('scholar_alert: '+(str(exc) if isinstance(exc, scholar_email.MailboxError) else type(exc).__name__))
    if os.environ.get("SCHOLAR_CONFIG_ERROR"):
        errors.append("scholar_alert: mailbox configuration could not be loaded")
    elif mode == 'scholar' and not scholar_email.configured():
        errors.append('scholar_alert: verified mailbox configuration is required')
    collection_ok = not errors
    if not store.meta("initialized") and errors:
        log("First run aborted: a source failed; baseline must be complete.")
        return 1
    papers = dedup_batch(papers)
    brief = Path(args.brief).read_text().strip() if args.brief and Path(args.brief).exists() else None
    policy = hashlib.sha256(f"{brief}|{relevance.MODEL}|{relevance.enabled()}".encode()).hexdigest()
    if store.meta("relevance_policy") not in (None, policy):
        for i, p in store.rows("SELECT id,data FROM papers WHERE status='irrelevant'"):
            if not relevance.enabled() or relevance.judge(p, brief):
                store.add_ids(i, p)
                store.set_status(i, "pending")
    store.set_meta("relevance_policy", policy)
    new, historical = 0, 0
    for p in papers:
        row_id = store.find(p)
        if row_id is not None:
            store.add_ids(row_id, p)
            continue
        old_history = collection_policy.silent_history(p, policy_window)
        if not seeding and not old_history:
            crossref.enrich(p)
            # Enrichment may canonicalize a title into an already stored record.
            row_id = store.find(p)
            if row_id is not None:
                store.add_ids(row_id, p)
                continue
        new += 1
        if seeding or old_history:
            store.insert(p, "seeded")
            historical += 1
        else:
            keep = relevance.judge(p, brief) if relevance.enabled() else True
            store.insert(p, "pending" if keep else "irrelevant")
    store.set_meta("initialized", "1")
    if mail_cursor:
        store.set_meta(*mail_cursor)
    if policy_window['deep'] and collection_ok:
        store.set_meta('deep_initialized', '1')
        store.set_meta('last_deep_collection', policy_window['at'])
    store.commit()
    if seeding:
        log(f"First run: recorded {new} existing papers as baseline, posted nothing.")

    # Every newly discovered paper is ingested, even if Slack relevance rejects it.
    # Each receipt is independent of Slack status and safe to replay by stable key.
    if not args.dry_run and pas.configured():
        for row_id, p in store.unsynced():
            try:
                receipt = pas.ingest(p)
                store.mark_synced(row_id, receipt)
            except Exception as e:
                errors.append(f"pas: {type(e).__name__}: {e}")
                break
    unsynced = {i for i, _ in store.unsynced()} if pas.configured() else set()
    queue = store.pending(MAX_POSTS_PER_RUN)
    if not args.dry_run and os.environ.get('SLACK_DELIVERY_MODE') == 'subscribers':
        from . import fanout
        errors.extend(fanout.send_all(store))
    elif args.dry_run or not slack.configured():
        outbox = Path(args.db).parent / "outbox"
        outbox.mkdir(exist_ok=True)
        (outbox / "pending.json").write_text(json.dumps(
            [slack.format_message(p) for _, p in queue], indent=2, ensure_ascii=False))
        log(f"Outbox: {len(queue)} message(s); kept pending.")
    elif os.environ.get("SLACK_BOT_TOKEN"):
        from . import digest, notifications
        sender = notifications if os.environ.get('SLACK_DELIVERY_MODE') == 'immediate_weekly' else digest
        errors.extend(sender.send(store, queue, unsynced))
    else:
        for row_id, p in queue:
            if row_id in unsynced:
                continue  # Slack only announces papers with durable PAS receipts.
            store.set_status(row_id, "sending")
            try:
                slack.post(p)
            except urllib.error.HTTPError as e:
                # A timeout/5xx can occur after acceptance. Never blindly replay.
                if e.code < 500:
                    store.set_status(row_id, "pending")
                errors.append(f"slack: HTTP {e.code}; inspect delivery before retrying")
                break
            except (OSError, ValueError) as e:
                errors.append(f"slack: {type(e).__name__}; delivery uncertain, reconcile required")
                break
            store.mark_posted(row_id)
            time.sleep(1.1)
    if store.counts().get("sending"):
        errors.append("Uncertain Slack delivery: use reconcile after checking the channel")
    # Shadow evaluation follows delivery and is never allowed to alter its outcome.
    if not args.dry_run and os.environ.get('JEV_MODE', 'off') != 'off':
        from . import jev, jev_monitor, jev_report
        try:
            outcome = jev.shadow(store, limit=8)
            jev_report.export(store, Path(args.db).parent / 'outbox')
            jev_monitor.run(store, Path(args.db).parent / 'outbox')
            log('Jev shadow: ' + json.dumps(outcome))
        except Exception as exc:
            log('Jev shadow unavailable: ' + type(exc).__name__)
            store.set_meta('jev_shadow_status', json.dumps({'mode': 'shadow', 'status': 'degraded', 'error_type': type(exc).__name__}))
            store.commit()
    log(f"new={new} status={store.counts()}")
    oldest = store.db.execute("SELECT min(first_seen) FROM papers WHERE status='pending'").fetchone()[0]
    distribution = json.loads(store.meta('fanout_summary') or '{}') if os.environ.get('SLACK_DELIVERY_MODE') == 'subscribers' else {}
    store.set_meta('last_run_summary', json.dumps({'collected_at': policy_window['at'], 'collection_ok': collection_ok,
        'source': mode, 'mailbox_provider': (scholar_email.configuration() or {}).get('provider', 'imap'),
        'mailbox_poll_ok': bool(mail_cursor) and not any(e.startswith('scholar_alert:') for e in errors),
        'deep_scan': policy_window['deep'], 'since': since, 'new_records': new, 'historical_seeded': historical,
        'counts': store.counts(), 'unsynced': len(store.unsynced()), 'oldest_pending': oldest, **distribution,
        'mailbox': 'enabled' if scholar_email.configured() else 'needs_configuration',
        'errors': [e.split(':', 1)[0] for e in errors]}))
    store.commit()
    for e in errors:
        log(f"ERROR {e}")
    return 1 if errors else 0


def cmd_reconcile(args) -> int:
    with open(str(args.db) + ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with contextlib.closing(Store(Path(args.db))) as store:
            if args.recipient:
                from .fanout import RecipientStore
                row = store.db.execute('SELECT status FROM deliveries WHERE paper_id=? AND user_id=?', (args.id, args.recipient)).fetchone()
                target = RecipientStore(store, args.recipient)
            else:
                row = store.db.execute("SELECT status FROM papers WHERE id=?", (args.id,)).fetchone()
                target = store
            if not row or row[0] != "sending":
                raise ValueError("Only uncertain ('sending') rows can be reconciled")
            if args.delivered:
                target.mark_posted(args.id)
            else:
                target.set_status(args.id, "pending")
    return 0


def cmd_reconcile_digest(args) -> int:
    import re
    with open(str(args.db) + ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with contextlib.closing(Store(Path(args.db))) as store:
            state = json.loads(store.meta("weekly_digest") or "{}")
            if state.get("status") != "sending":
                raise ValueError("Only an uncertain digest parent can be reconciled")
            if args.thread_ts:
                if not re.fullmatch(r"[0-9]+\.[0-9]+", args.thread_ts):
                    raise ValueError("Expected Slack thread timestamp, for example 1720000000.000001")
                state.update(status="posted", ts=args.thread_ts)
            else:
                state = {}
            store.set_meta("weekly_digest", json.dumps(state))
            store.commit()
    return 0


def cmd_reconcile_recap(args) -> int:
    import re
    if args.thread_ts and not re.fullmatch(r"[0-9]+\.[0-9]+", args.thread_ts):
        raise ValueError("Expected the existing Slack message timestamp")
    with open(str(args.db) + ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with contextlib.closing(Store(Path(args.db))) as store:
            if args.recipient:
                from .fanout import RecipientStore
                store = RecipientStore(store, args.recipient)
            state = json.loads(store.meta("weekly_recap") or "{}")
            if args.page is None:
                if state.get("status") != "sending":
                    raise ValueError("Only an uncertain recap parent can be reconciled")
                state["status"] = "posted" if args.thread_ts else "pending"
                if args.thread_ts:
                    state["ts"] = args.thread_ts
            else:
                key = str(args.page)
                if state.get("pages", {}).get(key) != "sending":
                    raise ValueError("Only an uncertain recap page can be reconciled")
                state["pages"][key] = "posted" if args.thread_ts else "pending"
                if args.thread_ts:
                    state.setdefault("page_receipts", {})[key] = args.thread_ts
            store.set_meta("weekly_recap", json.dumps(state))
            store.commit()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="paper_monitor")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("resolve", help="fill OpenAlex ids in authors.csv")
    r.add_argument("authors")
    r.set_defaults(func=cmd_resolve)
    u = sub.add_parser("run", help="poll sources, dedup, post to Slack")
    u.add_argument("--authors", default="authors.csv")
    u.add_argument("--db", default="state.db")
    u.add_argument("--brief", default="relevance_brief.txt",
                   help="team-focus text for the optional LLM relevance filter")
    u.add_argument("--dry-run", action="store_true", help="never post; write outbox/pending.json")
    u.add_argument("--post-backlog", action="store_true",
                   help="on first run, post the lookback window instead of silently seeding")
    u.set_defaults(func=cmd_run)
    recover = sub.add_parser("reconcile", help="resolve uncertain Slack delivery after checking the channel")
    recover.add_argument("--db", required=True)
    recover.add_argument("--id", required=True, type=int)
    recover.add_argument("--recipient", help="Slack user ID for a personal delivery")
    decision = recover.add_mutually_exclusive_group(required=True)
    decision.add_argument("--delivered", action="store_true")
    decision.add_argument("--retry", action="store_true")
    recover.set_defaults(func=cmd_reconcile)
    recover_digest = sub.add_parser("reconcile-digest", help="resolve uncertain weekly parent delivery")
    recover_digest.add_argument("--db", required=True)
    choice = recover_digest.add_mutually_exclusive_group(required=True)
    choice.add_argument("--thread-ts", help="timestamp of the existing parent, after inspecting Slack")
    choice.add_argument("--retry", action="store_true")
    recover_digest.set_defaults(func=cmd_reconcile_digest)
    recover_recap = sub.add_parser("reconcile-recap", help="resolve uncertain recap delivery after inspecting Slack")
    recover_recap.add_argument("--db", required=True)
    recover_recap.add_argument("--page", type=int, help="zero-based thread page; omit for parent")
    recover_recap.add_argument("--recipient", help="Slack user ID for a personal recap")
    choice = recover_recap.add_mutually_exclusive_group(required=True)
    choice.add_argument("--thread-ts", help="existing parent or page message timestamp")
    choice.add_argument("--retry", action="store_true")
    recover_recap.set_defaults(func=cmd_reconcile_recap)
    args = ap.parse_args(argv)
    return args.func(args)
