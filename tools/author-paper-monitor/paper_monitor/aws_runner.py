"""ECS entry point: S3 checkpoints and a PostgreSQL advisory lock.

The lock is held by a dedicated connection for the whole run. PostgreSQL releases
it on worker death. Every external write is preceded by a lock-connection check.
S3 checkpoints are written on every state commit, including BEFORE Slack POST.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import sqlite3
import tempfile
from pathlib import Path


def _run(argv=None):
    import boto3
    from sqlalchemy import text
    from app.db import engine
    from . import cli, slack, slack_app
    from .store import Store

    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--post-backlog", action="store_true")
    ap.add_argument("--verify-ingestion", action="store_true")
    ap.add_argument("--reconcile-id", type=int)
    ap.add_argument("--reconcile-digest", action="store_true")
    ap.add_argument("--reconcile-recap", action="store_true")
    ap.add_argument("--page", type=int)
    ap.add_argument("--recipient")
    ap.add_argument("--thread-ts")
    ap.add_argument("--delivered", action="store_true")
    ap.add_argument("--retry", action="store_true")
    args = ap.parse_args(argv)
    bucket = os.environ["MONITOR_BUCKET"]
    prefix = os.environ.get("MONITOR_PREFIX", "author-monitor/production").strip("/")
    if (args.dry_run or args.verify_ingestion) and prefix == "author-monitor/production":
        raise ValueError("Cloud dry-run requires a separate MONITOR_PREFIX")
    os.environ["PAS_MONITOR_INGEST"] = "1"
    os.environ.setdefault("PAS_MONITOR_MODE", "main")
    os.environ.setdefault("CONTACT_EMAIL", os.environ.get("PAS_OPENALEX_MAILTO", ""))
    signal.alarm(1500)  # Bound crashed/slow runs; interrupted sends remain 'sending'.
    s3 = boto3.client("s3")
    from . import registry
    registry.configure_openalex()
    os.environ.pop('SCHOLAR_CONFIG_ERROR', None)
    try:
        registry.configure_scholar()
    except Exception as exc:
        os.environ['SCHOLAR_CONFIG_ERROR'] = type(exc).__name__
    try:
        registry.configure_jev()
    except Exception as exc:
        os.environ.pop('TYPESAFE_API_KEY', None)
        print('Jev configuration unavailable: ' + type(exc).__name__)
    use_registry = bool(os.environ.get("SLACK_TABLE")) and prefix == "author-monitor/production"
    if use_registry:
        from . import registry
        settings = registry.get("settings")
        config = registry.credentials()
        if config and (settings.get("enabled") or os.environ.get('SLACK_DELIVERY_MODE') == 'subscribers'):
            os.environ["SLACK_BOT_TOKEN"] = config["bot_token"]
            os.environ["SLACK_CHANNEL_ID"] = settings["channel_id"]
    # One lock for all monitor states in this PAS database prevents double imports.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as lock:
        acquired = lock.scalar(text("SELECT pg_try_advisory_lock(741930, 1)"))
        if not acquired:
            raise RuntimeError("Another author monitor holds the database lock")
        def check_lock():
            # Do not reconnect on disconnect: a replacement connection no longer owns the lock.
            if lock.invalidated or lock.closed:
                raise RuntimeError("Lost author monitor lock")
            lock.execute(text("SELECT 1"))

        with tempfile.TemporaryDirectory(prefix="author-monitor-") as tmp:
            root = Path(tmp)
            db = root / "state.db"
            for name in ("authors.csv", "state.db", "relevance_brief.txt"):
                key = f"{prefix}/{name}"
                found = s3.list_objects_v2(Bucket=bucket, Prefix=key, MaxKeys=1)
                if any(obj["Key"] == key for obj in found.get("Contents", [])):
                    s3.download_file(bucket, key, str(root / name))
                elif name == "authors.csv":
                    raise ValueError("Production author configuration is missing")

            if use_registry:
                from .authors import Author, save
                active = [r for r in registry.authors() if r.get("status") == "active"]
                save(root / "authors.csv", [Author(name=r["name"], orcid=r.get("orcid", ""),
                    openalex_ids=r["openalex_ids"]) for r in active])

            if args.verify_ingestion:
                from .verify_pas import verify
                verify(db)
                return 0

            class CheckpointStore(Store):
                def __init__(self, path):
                    self.checkpoint_enabled = str(path) != ":memory:"
                    super().__init__(path)

                def commit(self):
                    check_lock()
                    super().commit()
                    if self.checkpoint_enabled:
                        s3.upload_file(str(db), bucket, f"{prefix}/state.db")

            original_store, original_post = cli.Store, slack.post
            original_api = slack_app.api
            cli.Store = CheckpointStore
            def guarded_post(p):
                check_lock()
                original_post(p)
            slack.post = guarded_post
            def guarded_api(*args, **kwargs):
                check_lock()
                return original_api(*args, **kwargs)
            slack_app.api = guarded_api
            try:
                if args.reconcile_digest or args.reconcile_recap:
                    if bool(args.thread_ts) == args.retry:
                        raise ValueError("Choose --thread-ts or --retry after checking Slack")
                    decision = ["--thread-ts", args.thread_ts] if args.thread_ts else ["--retry"]
                    operation = "reconcile-recap" if args.reconcile_recap else "reconcile-digest"
                    if args.page is not None:
                        decision.extend(["--page", str(args.page)])
                    if args.recipient:
                        decision.extend(["--recipient", args.recipient])
                    result = cli.main([operation, "--db", str(db), *decision])
                elif args.reconcile_id:
                    if args.delivered == args.retry:
                        raise ValueError("Choose --delivered or --retry after checking Slack")
                    result = cli.main(["reconcile", "--db", str(db), "--id", str(args.reconcile_id),
                                       "--delivered" if args.delivered else "--retry", *(["--recipient", args.recipient] if args.recipient else [])])
                else:
                    command = ["run", "--authors", str(root / "authors.csv"), "--db", str(db),
                               "--brief", str(root / "relevance_brief.txt")]
                    if args.dry_run:
                        command.append("--dry-run")
                    if args.post_backlog:
                        command.append("--post-backlog")
                    result = cli.main(command)
                outbox = root / "outbox" / "pending.json"
                if outbox.exists():
                    s3.upload_file(str(outbox), bucket, f"{prefix}/outbox/pending.json")
                for name in ('jev-shadow.json', 'jev-labels.csv', 'jev-workflows.json'):
                    artifact = root / 'outbox' / name
                    if artifact.exists():
                        s3.upload_file(str(artifact), bucket, f'{prefix}/outbox/{name}')
                if use_registry and not (args.reconcile_id or args.reconcile_digest or args.reconcile_recap):
                    import datetime
                    with contextlib.closing(sqlite3.connect(f'file:{db}?mode=ro', uri=True)) as state:
                        row = state.execute("SELECT value FROM metadata WHERE key='jev_shadow_status'").fetchone()
                        shadow_status = json.loads(row[0]) if row else {}
                        summary_row = state.execute("SELECT value FROM metadata WHERE key='last_run_summary'").fetchone()
                        summary = json.loads(summary_row[0]) if summary_row else {}
                    if os.environ.get('JEV_MODE', 'off') == 'off':
                        shadow_status = {'status': 'off', 'mode': 'off'}
                    def record_run(current):
                        current["last_run_exit"] = result
                        current["monitor_summary"] = summary
                        if result == 0:
                            current["last_collection"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                        current['jev_shadow'] = shadow_status
                    registry.change("settings", record_run)
                    registry.change('monitor-health', lambda current: current.update(summary=summary))
                return result
            finally:
                cli.Store, slack.post = original_store, original_post
                slack_app.api = original_api
                with contextlib.suppress(Exception):
                    lock.execute(text("SELECT pg_advisory_unlock(741930, 1)"))


def main(argv=None):
    import sys
    import time
    from . import registry
    argv = list(sys.argv[1:] if argv is None else argv)
    collection = not any(a.split('=')[0] in {'--dry-run', '--verify-ingestion', '--reconcile-id', '--reconcile-digest', '--reconcile-recap'} for a in argv)
    live = collection and bool(os.environ.get('SLACK_TABLE')) and os.environ.get('MONITOR_PREFIX', 'author-monitor/production').strip('/') == 'author-monitor/production'
    if live:
        registry.change('monitor-health', lambda h: h.update(last_started_at=int(time.time())))
    result, failure = 1, None
    try:
        result = _run(argv)
        return result
    except Exception as exc:
        failure = type(exc).__name__
        raise
    finally:
        if live:
            def finish(health):
                health.update(last_finished_at=int(time.time()), last_exit=result, error_type=failure)
                if result == 0:
                    health['last_success_at'] = int(time.time())
            registry.change('monitor-health', finish)


if __name__ == "__main__":
    raise SystemExit(main())
