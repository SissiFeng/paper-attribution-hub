import datetime as dt
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from paper_monitor import health, mailbox_state, scholar_graph, scholar_email, cli
from paper_monitor.models import Paper
from paper_monitor.store import Store
from test_mail_reliability import mock_mail
from test_scholar_graph import CONFIG, item
from test_scholar_mailbox import AUTHORS, message


def test_initial_history_is_ingested_silently_and_new_mail_can_notify(env):
    _, run, statuses, _, mp, path = env
    mp.setenv('MONITOR_SOURCE', 'scholar')
    mp.setattr(scholar_email, '_config', {**CONFIG, 'notify_after': '2026-10-15T13:00:00Z'})
    (path / 'authors.csv').write_text('name\nAnatole von Lilienfeld\n')
    mock_mail(mp, [item()], {'1': message()})
    assert run('--dry-run') == 0
    assert set(statuses().values()) == {'seeded'}
    store = Store(path / 'state.db')
    assert len(store.unsynced()) == 2  # History is still queued for PAS ingestion.
    assert mailbox_state.summary(store)['mail_counts'] == {'processed': 1}
    store.close()
    fresh = item('2')
    fresh['receivedDateTime'] = '2026-10-15T14:00:00Z'
    html = '<h3><a class="gse_alrt_title" href="https://example.org/new">A newly arrived unique paper</a></h3><p>A Author - Nature, 2026</p>'
    mock_mail(mp, [fresh], {'2': message(body=html)})
    assert run('--dry-run') == 0
    assert statuses()['a newly arrived unique paper'] == 'pending'


def test_429_delays_new_requests_but_retained_mail_remains_processable(tmp_path, monkeypatch):
    store = Store(tmp_path / 's.db')
    mock_mail(monkeypatch, [item('1')], {'1': message()})
    papers, cursor = scholar_graph.fetch_pending(store, AUTHORS, CONFIG)
    calls = []
    def fail(url, **kwargs):
        calls.append(url)
        raise scholar_graph.GraphError(429, 120)
    monkeypatch.setattr(scholar_graph, 'request', fail)
    assert len(scholar_graph.fetch_pending(store, AUTHORS, CONFIG)[0]) == len(papers)
    again, report = scholar_graph.fetch_pending(store, AUTHORS, CONFIG)
    assert len(calls) == 1 and len(again) == len(papers)
    assert not json.loads(report[1])['poll_ok']
    store.close()


def test_expired_delta_rescans_without_duplicate_processing(tmp_path, monkeypatch):
    store = Store(tmp_path / 's.db')
    mock_mail(monkeypatch, [item()], {'1': message()})
    _, cursor = scholar_graph.fetch_pending(store, AUTHORS, CONFIG)
    mailbox_state.acknowledge(store, json.loads(cursor[1])['ready_message_ids'])
    store.commit()
    monkeypatch.setattr(scholar_graph, 'request', lambda *_a, **_k: (_ for _ in ()).throw(scholar_graph.GraphError(410)))
    assert not json.loads(scholar_graph.fetch_pending(store, AUTHORS, CONFIG)[1][1])['poll_ok']
    assert store.meta(cursor[0]) == '{}'
    mock_mail(monkeypatch, [item()], {})  # A body fetch would fail: processed immutable IDs are skipped.
    assert not scholar_graph.fetch_pending(store, AUTHORS, CONFIG)[0]
    store.close()


def test_mail_auth_failure_does_not_block_already_captured_work(tmp_path, monkeypatch):
    store = Store(tmp_path / 's.db')
    mock_mail(monkeypatch, [item()], {'1': message()})
    papers, _ = scholar_graph.fetch_pending(store, AUTHORS, CONFIG)
    monkeypatch.setattr(scholar_graph, 'access_token', lambda _: (_ for _ in ()).throw(scholar_graph.GraphError(401)))
    replay, cursor = scholar_graph.fetch_pending(store, AUTHORS, CONFIG)
    assert len(replay) == len(papers) and not json.loads(cursor[1])['poll_ok']
    store.close()


def test_quarantine_retry_command_does_not_send_or_reprocess_delivered_mail(tmp_path, monkeypatch, capsys):
    mock_mail(monkeypatch, [item()], {'1': message(body='Unknown layout')})
    path = tmp_path / 's.db'
    store = Store(path)
    scholar_graph.fetch_pending(store, AUTHORS, CONFIG)
    key = store.db.execute('SELECT id FROM mail_messages').fetchone()[0]
    store.close()
    assert cli.main(['mail', '--db', str(path), '--retry-id', key]) == 0
    assert json.loads(capsys.readouterr().out)['mail_counts'] == {'captured': 1}
    with pytest.raises(ValueError):
        cli.main(['mail', '--db', str(path), '--retry-id', key])


def test_raw_retention_keeps_unprocessed_references(tmp_path):
    store = Store(tmp_path / 's.db')
    first = mailbox_state.capture(store, 'box', item('a'), raw=b'raw')
    second = mailbox_state.capture(store, 'box', item('b'), raw=b'raw')
    digest = store.db.execute('SELECT content_hash FROM mail_messages LIMIT 1').fetchone()[0]
    store.db.execute("UPDATE mail_messages SET status='processed',processed_at='2026-01-01T00:00:00+00:00' WHERE id=?", (first,))
    now = dt.datetime(2026, 10, 16, tzinfo=dt.timezone.utc)
    assert mailbox_state.prune_processed(store, now=now) == 0
    assert store.read_mail(digest) == b'raw'
    store.db.execute("UPDATE mail_messages SET status='processed',processed_at='2026-01-01T00:00:00+00:00' WHERE id=?", (second,))
    assert mailbox_state.prune_processed(store, now=now) == 1
    assert not store.db.execute('SELECT 1 FROM mail_messages WHERE content_hash IS NOT NULL').fetchone()
    assert mailbox_state.prune_processed(store, now=now) == 0
    store.close()


def test_mail_poll_and_delivery_failures_have_separate_health():
    settings = {'monitoring': {'source': 'scholar', 'state': 'active'}}
    state = {'last_success_at': 1, 'last_exit': 1, 'summary': {
        'last_mailbox_poll_ok_at': 9999, 'delivery_counts': {'sending': 1}, 'errors': ['slack']}}
    problems = health.problems(state, settings, [], now=10000)
    assert 'stale' not in problems and 'delivery_uncertain' in problems
    state['summary'].update(mail_quarantined=1, secret_expires_at=10001)
    problems = health.problems(state, settings, [], now=10000)
    assert 'mail_review' in problems and 'mail_credential_expiry' in problems


def test_storage_rules_preserve_nonruntime_policy_and_never_expire_current_state(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / 'deploy'))
    module = importlib.import_module('storage_policy')
    preserved = {'ID': 'unrelated-policy', 'Status': 'Enabled', 'Filter': {'Prefix': 'other/'}, 'Expiration': {'Days': 300}}
    result = module.rules([preserved, {'ID': 'transition-to-glacier', 'Filter': {'Prefix': ''}}])
    assert preserved in result and module.rules(result) == result
    for key in ('author-monitor/releases/current.zip', 'author-monitor/health-releases/current.zip', 'author-monitor/production/state.db'):
        matching = [r for r in result if key.startswith(r['Filter']['Prefix'])]
        assert all('Transitions' not in r and 'Expiration' not in r for r in matching)
    state = next(r for r in result if r['ID'] == 'monitor-state-versions')
    assert state['NoncurrentVersionExpiration'] == {'NoncurrentDays': 7, 'NewerNoncurrentVersions': 10}


def test_coverage_import_cannot_claim_confirmation_without_profile(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / 'deploy'))
    coverage = importlib.import_module('scholar_coverage')
    path = tmp_path / 'authors.csv'
    path.write_text('person_id,name,profile_url,alert_created,subscription_confirmed\na,A,,true,true\n')
    with pytest.raises(ValueError, match='profile'):
        coverage.changes(path, [{'person_id': 'a', 'name': 'A'}])
    path.write_text('person_id,name,profile_url,alert_created,subscription_confirmed\na,A,https://scholar.google.com/citations?user=EXAMPLE,true,true\n')
    assert coverage.changes(path, [{'person_id': 'a', 'name': 'A'}])[0][1]['subscription_confirmed']


def test_independent_alert_does_not_depend_on_slack_lambda(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / 'deploy'))
    module = importlib.import_module('health_aws')
    args = SimpleNamespace(stack='health', slack_stack='slack', monitor_stack='monitor', region='ca-central-1', bucket='bucket')
    doc = module.template(args, '123', 'key', ['alarm'])
    resources = doc['Resources']
    assert resources['WatchdogAlarm']['Properties']['AlarmActions'] == [{'Ref': 'Alerts'}]
    assert {'Id': 'independent-alert', 'Arn': {'Ref': 'Alerts'}} in resources['AlarmEvents']['Properties']['Targets']
    assert resources['EmailAlerts']['Condition'] == 'HasAlertEmail'
    statements = resources['AlertPolicy']['Properties']['PolicyDocument']['Statement']
    assert len({s['Sid'] for s in statements}) == len(statements)
