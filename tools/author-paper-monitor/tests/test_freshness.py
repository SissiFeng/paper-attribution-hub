import copy
import datetime as dt
import json
from types import SimpleNamespace

import pytest

from paper_monitor import (
    cli,
    collection_policy,
    health,
    notifications,
    registry,
    scholar_email,
    slack_app,
)
from paper_monitor.models import Paper
from paper_monitor.store import Store


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(scholar_email, "_config", None)
    for key in (
        "DEEP_LOOKBACK_DAYS",
        "SLACK_DELIVERY_MODE",
        "SCHOLAR_CONFIG_ERROR",
        "SCHOLAR_CONFIG_PARAMETER",
    ):
        monkeypatch.delenv(key, raising=False)


def test_initial_deep_baseline_then_late_paper_is_notified(env, monkeypatch):
    now = dt.datetime(2026, 10, 6, 1, tzinfo=dt.timezone.utc)
    original_window = collection_policy.window
    monkeypatch.setattr(collection_policy, 'window', lambda store: original_window(store, now=now))
    _, run, statuses, _, _, path = env
    assert run() == 0
    monkeypatch.setenv("DEEP_LOOKBACK_DAYS", "365")
    old = Paper(
        "Older history",
        doi="10.1/old",
        date="2026-02-01",
        authors=["A"],
        sources=["openalex"],
    )
    recent = Paper(
        "Fresh today",
        doi="10.1/new",
        date=now.date().isoformat(),
        authors=["A"],
        sources=["openalex"],
    )
    calls = []
    monkeypatch.setattr(
        cli, "collect", lambda rows, since: calls.append(since) or ([old, recent], [])
    )
    monkeypatch.setattr(cli.crossref, "enrich", lambda _: None)
    assert run() == 0
    assert (
        statuses()["older history"] == "seeded"
        and statuses()["fresh today"] == "pending"
    )
    with Store(path / "state.db").db as db:
        db.execute(
            "UPDATE metadata SET value=? WHERE key='last_deep_collection'",
            ((now - dt.timedelta(days=8)).isoformat(),),
        )
    old2 = Paper(
        "Late indexed study",
        doi="10.1/late",
        date="2026-02-02",
        authors=["A"],
        sources=["openalex"],
    )
    monkeypatch.setattr(cli, "collect", lambda rows, since: ([old, recent, old2], []))
    assert run() == 0 and statuses()["late indexed study"] == "pending"
    assert calls[0] == '2025-10-06'


def test_failed_deep_scan_keeps_retry_due(env, monkeypatch):
    _, run, _, _, _, path = env
    assert run() == 0
    monkeypatch.setenv("DEEP_LOOKBACK_DAYS", "365")
    monkeypatch.setattr(cli, "collect", lambda *_: ([], ["openalex: unavailable"]))
    assert run() == 1
    store = Store(path / "state.db")
    assert (
        not store.meta("deep_initialized") and collection_policy.window(store)["deep"]
    )
    store.close()


def ready_store(tmp_path):
    store = Store(tmp_path / "s.db")
    row = store.insert(Paper("New study", doi="10.1/new", authors=["A"]), "pending")
    store.mark_synced(row, "pas1")
    return store, row


def test_immediate_delivery_on_tuesday_and_independent_weekly_recap(
    tmp_path, monkeypatch
):
    store, row = ready_store(tmp_path)
    monkeypatch.setenv("SLACK_BOT_TOKEN", "secret")
    monkeypatch.setenv("SLACK_CHANNEL_ID", "D1")
    monkeypatch.setattr(notifications.time, "sleep", lambda _: None)
    calls = []
    monkeypatch.setattr(
        slack_app, "api", lambda *a: calls.append(a[2]) or {"ts": str(len(calls))}
    )
    tuesday = dt.datetime(2026, 10, 6, 12, tzinfo=dt.timezone.utc)
    monkeypatch.setattr(
        "paper_monitor.store._now", lambda: tuesday.isoformat(timespec="seconds")
    )
    assert not notifications.send(store, store.pending(20), set(), now=tuesday)
    assert store.counts() == {"posted": 1} and len(calls) == 1
    assert store.db.execute('SELECT channel,ts FROM notification_receipts WHERE paper_id=?', (row,)).fetchone() == ('D1', '1')
    assert not notifications.send(store, store.pending(20), set(), now=tuesday)
    assert len(calls) == 1
    monday = tuesday + dt.timedelta(days=6)
    assert not notifications.send(store, [], set(), now=monday)
    assert len(calls) == 3 and "already sent privately" in calls[1]["text"]
    assert calls[2]["thread_ts"] == "2"
    assert not notifications.send(store, [], set(), now=monday)
    assert len(calls) == 3 and store.counts() == {"posted": 1}
    store.close()


@pytest.mark.parametrize('page', [None, 0])
@pytest.mark.parametrize('receipt', [None, '1720000000.000001'])
def test_recap_reconciliation_preserves_batch_and_records_receipt(tmp_path, page, receipt):
    store, row = ready_store(tmp_path)
    state = {'week': '2026-10-05', 'status': 'sending' if page is None else 'posted',
             'ids': [row], 'pages': {'0': 'sending'}, 'channel': 'D1'}
    store.set_meta('weekly_recap', json.dumps(state))
    store.commit()
    store.close()
    command = ['reconcile-recap', '--db', str(tmp_path / 's.db')]
    command += ['--thread-ts', receipt] if receipt else ['--retry']
    if page is not None:
        command += ['--page', str(page)]
    assert cli.main(command) == 0
    store = Store(tmp_path / 's.db')
    after = json.loads(store.meta('weekly_recap'))
    assert after['ids'] == [row]
    assert (after['status'] if page is None else after['pages']['0']) == ('posted' if receipt else 'pending')
    if receipt:
        assert (after['ts'] if page is None else after['page_receipts']['0']) == receipt
    store.close()


@pytest.mark.parametrize('argv', [['--dry-run'], ['--verify-ingestion'], ['--reconcile-id', '1', '--retry'], ['--reconcile-recap', '--retry']])
def test_noncollection_operations_do_not_refresh_health(monkeypatch, argv):
    from paper_monitor import aws_runner
    data = fake_registry(monkeypatch)
    monkeypatch.setenv('SLACK_TABLE', 'table')
    monkeypatch.setenv('MONITOR_PREFIX', 'author-monitor/production')
    monkeypatch.setattr(aws_runner, '_run', lambda _: 0)
    assert aws_runner.main(argv) == 0
    assert 'monitor-health' not in data


def test_legacy_uncertain_parent_blocks_mode_transition(tmp_path, monkeypatch):
    store, row = ready_store(tmp_path)
    monkeypatch.setenv('SLACK_CHANNEL_ID', 'D1')
    store.set_meta('weekly_digest', json.dumps({'status': 'sending', 'ids': [row]}))
    monkeypatch.setattr(slack_app, 'api', lambda *_: pytest.fail('must reconcile first'))
    assert notifications.send(store, store.pending(20), set())
    assert store.counts() == {'pending': 1}
    store.close()


def test_immediate_waits_for_ingestion_and_preserves_ambiguous_post(
    tmp_path, monkeypatch
):
    store, row = ready_store(tmp_path)
    monkeypatch.setenv("SLACK_BOT_TOKEN", "secret")
    monkeypatch.setenv("SLACK_CHANNEL_ID", "D1")
    calls = []

    def timeout(*a):
        calls.append(a)
        raise TimeoutError()

    monkeypatch.setattr(slack_app, "api", timeout)
    assert not notifications.send(store, store.pending(20), {row})
    assert not calls
    assert notifications.send(store, store.pending(20), set())
    assert store.counts() == {"sending": 1}
    notifications.send(store, store.pending(20), set())
    assert len(calls) == 1
    store.close()


def test_mail_cursor_commits_with_papers_not_before(env, monkeypatch):
    _, run, _, _, _, path = env
    assert run() == 0
    monkeypatch.setattr(scholar_email, "configured", lambda: True)
    monkeypatch.setattr(cli, "collect", lambda *_: ([], []))
    monkeypatch.setattr(cli.crossref, "enrich", lambda _: None)
    monkeypatch.setattr(
        scholar_email,
        "fetch_pending",
        lambda *_: (
            [Paper("Mail study", doi="10.1/mail")],
            ("scholar_cursor:test", "42"),
        ),
    )
    original = Store.insert
    monkeypatch.setattr(
        Store,
        "insert",
        lambda *_: (_ for _ in ()).throw(RuntimeError("Storage unavailable")),
    )
    with pytest.raises(RuntimeError):
        run()
    store = Store(path / "state.db")
    assert not store.meta("scholar_cursor:test")
    store.close()
    monkeypatch.setattr(Store, "insert", original)
    assert run() == 0
    store = Store(path / "state.db")
    assert store.meta("scholar_cursor:test") == "42"
    store.close()


def fake_registry(monkeypatch):
    data = {
        "settings": {
            "owner_id": "U1",
            "channel_id": "D1",
            "tested_channel": "D1",
            "enabled": True,
        }
    }
    monkeypatch.setattr(registry, "get", lambda k: copy.deepcopy(data.get(k, {})))
    monkeypatch.setattr(
        registry, "put", lambda k, v: data.update({k: copy.deepcopy(v)})
    )

    def change(k, f):
        value = copy.deepcopy(data.get(k, {}))
        f(value)
        data[k] = value
        return value

    monkeypatch.setattr(registry, "change", change)
    monkeypatch.setattr(registry, "credentials", lambda: {"bot_token": "secret"})
    return data


def test_watchdog_checks_failure_staleness_backlog_and_recovery():
    now = 100000
    h = {"last_success_at": now - 60, "last_exit": 0, "summary": {}}
    assert health.problems(h, {"enabled": True}, [], now=now) == {}
    h.update(last_exit=1, failed_task_at=now)
    assert set(health.problems(h, {}, [], now=now)) == {"run_failed", "task_failed"}
    h.update(
        last_exit=0,
        failed_task_at=0,
        last_success_at=now - 20000,
        summary={
            "oldest_pending": now - 20000,
            "unsynced": 2,
            "counts": {"sending": 1},
        },
    )
    assert set(health.problems(h, {"enabled": True}, [], now=now)) == {
        "stale",
        "delivery_backlog",
        "ingestion_pending",
        "delivery_uncertain",
    }


def test_watchdog_dedup_and_recovery_only_to_owner(monkeypatch):
    data = fake_registry(monkeypatch)
    calls = []
    monkeypatch.setattr(
        slack_app, "api", lambda *a: calls.append(a[2]) or {"ts": str(len(calls))}
    )
    assert health.notify({"stale": "No collection"})["sent"]
    assert not health.notify({"stale": "No collection"})["sent"]
    assert health.notify({})["sent"]
    assert not health.notify({})["sent"]
    assert len(calls) == 2 and all(c["channel"] == "D1" for c in calls)
    data["settings"]["channel_id"] = "C1"
    with pytest.raises(ValueError, match="private"):
        health.notify({"stale": "No collection"})


def test_watchdog_does_not_repeat_an_uncertain_alert(monkeypatch):
    fake_registry(monkeypatch)
    calls = []

    def fail(*a):
        calls.append(a)
        raise TimeoutError()

    monkeypatch.setattr(slack_app, "api", fail)
    with pytest.raises(TimeoutError):
        health.notify({"stale": "No collection"})
    assert health.notify({"stale": "No collection"})["status"] == "delivery_uncertain"
    assert len(calls) == 1


def test_infrastructure_has_four_hour_cadence_secret_scope_and_independent_watchdog(
    monkeypatch,
):
    import importlib
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "deploy"))
    deploy = importlib.import_module("aws")
    watchdog = importlib.import_module("health_aws")
    args = SimpleNamespace(
        stack="monitor",
        bucket="bucket",
        region="ca-central-1",
        cluster="cluster",
        slack_app="slack",
        slack_parameter=None,
        jev_shadow=True,
        enable_schedule=True,
        slack_stack="slack",
        monitor_stack="monitor",
    )
    doc = deploy.template(
        args,
        "123",
        {"containerDefinitions": [{}]},
        {"subnets": ["s"], "securityGroups": ["g"], "assignPublicIp": "ENABLED"},
        "image",
        "key",
        "hash",
        "/db",
    )
    assert (
        doc["Resources"]["Schedule"]["Properties"]["ScheduleExpression"]
        == "cron(17 0/4 * * ? *)"
    )
    assert "parameter/monitor/scholar-mailbox" in json.dumps(doc)
    watch = watchdog.template(args, "123", "bundle", ["alarm"])
    assert (
        watch["Resources"]["Schedule"]["Properties"]["ScheduleExpression"]
        == "rate(15 minutes)"
    )
    assert len([k for k in watch["Resources"] if k.endswith("Permission")]) == 3


def test_watchdog_concurrent_claim_does_not_post_twice(monkeypatch):
    data = fake_registry(monkeypatch)
    original = registry.change

    def competing(key, edit):
        data[key] = {'status': 'sending', 'fingerprint': 'other-worker'}
        return original(key, edit)

    monkeypatch.setattr(registry, 'change', competing)
    monkeypatch.setattr(slack_app, 'api', lambda *_: pytest.fail('another worker owns this incident'))
    assert health.notify({'stale': 'No collection'})['status'] == 'claimed_elsewhere'
