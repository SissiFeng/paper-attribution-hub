import copy
import importlib
import json
import urllib.error
from pathlib import Path

import pytest

from paper_monitor import cli, health, registry, scholar_email, scholar_graph, slack_app
from paper_monitor.store import Store
from test_scholar_mailbox import AUTHORS, message

CONFIG = {'provider': 'graph', 'tenant_id': '78aac226-2f03-4b4d-9037-b46d56c55210',
    'client_id': '11111111-2222-3333-4444-555555555555', 'client_secret': 'never-print-me',
    'mailbox': 'comms.acceleration@utoronto.ca', 'folder': 'Google Scholar Alerts',
    'folder_id': 'folder/with+base64=', 'verified_at': '2026-10-14T00:00:00+00:00'}


def item(id='1', subject='Anatole von Lilienfeld - new articles', sender=scholar_email.SENDER):
    return {'id': id, 'subject': subject, 'from': {'emailAddress': {'address': sender}}}


def graph(monkeypatch, pages, *, body=None):
    calls = []
    def request(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith('/$value'):
            return message(body=body).as_bytes()
        return pages.pop(0)
    monkeypatch.setattr(scholar_graph, 'request', request)
    monkeypatch.setattr(scholar_graph, 'access_token', lambda _: 'private-token')
    return calls


def test_confirmation_ignored_without_parsing_body():
    assert not scholar_email.parse_message(message(subject='Confirm your Scholar alert', body='Confirm'), AUTHORS)


def test_graph_pages_replay_and_atomic_cursor(tmp_path, monkeypatch):
    base = scholar_graph.delta_url(CONFIG)
    pages = [{'value': [item(), item('control', 'Confirm your Scholar alert'),
                        item('other', sender='unrelated@example.org')], '@odata.nextLink': base + '?page=2'},
             {'value': [item(), {'id': 'deleted', '@removed': {'reason': 'deleted'}}],
              '@odata.deltaLink': base + '?delta=3'}]
    calls = graph(monkeypatch, copy.deepcopy(pages))
    store = Store(tmp_path / 's.db')
    papers, cursor = scholar_graph.fetch_pending(store, AUTHORS, CONFIG)
    assert len(papers) == 2 and store.meta(cursor[0]) is None
    assert json.loads(cursor[1])['ignored'] == 2
    assert len([url for url, _ in calls if url.endswith('/$value')]) == 1
    assert all(call[1]['token'] == 'private-token' for call in calls)
    # Crash before commit replays all papers without losing the cursor boundary.
    graph(monkeypatch, copy.deepcopy(pages))
    again, same = scholar_graph.fetch_pending(store, AUTHORS, CONFIG)
    assert same == cursor and len(again) == 2
    for paper in papers:
        store.insert(paper, 'pending')
    store.set_meta(*cursor)
    store.commit()
    calls = graph(monkeypatch, [{'value': [], '@odata.deltaLink': base + '?delta=4'}])
    assert not scholar_graph.fetch_pending(store, AUTHORS, {**CONFIG, 'client_secret': 'rotated'})[0]
    assert calls[0][0] == base + '?delta=3'
    store.close()


@pytest.mark.parametrize('url', [
    'https://evil.example/v1.0/users/x/mailFolders/y/messages/delta',
    'http://graph.microsoft.com/v1.0/users/x/mailFolders/y/messages/delta',
    'https://graph.microsoft.com@evil.example/x',
    'https://graph.microsoft.com/v1.0/users/sissi.feng%40utoronto.ca/mailFolders/x/messages/delta',
    scholar_graph.delta_url(CONFIG) + '/../other',
])
def test_delta_cannot_escape_folder(tmp_path, monkeypatch, url):
    graph(monkeypatch, [{'value': [], '@odata.nextLink': url}])
    store = Store(tmp_path / 's.db')
    with pytest.raises(scholar_email.MailboxError, match='escaped'):
        scholar_graph.fetch_pending(store, AUTHORS, CONFIG)
    assert not store.db.execute("SELECT 1 FROM metadata WHERE key LIKE 'scholar_graph_cursor:%'").fetchone()
    store.close()


@pytest.mark.parametrize('page', [
    {'value': []}, {'value': [], '@odata.nextLink': 'x', '@odata.deltaLink': 'y'},
    {'value': {}}, {'value': [{}]},
])
def test_bad_graph_page_does_not_advance(tmp_path, monkeypatch, page):
    graph(monkeypatch, [page])
    store = Store(tmp_path / 's.db')
    with pytest.raises(scholar_email.MailboxError):
        scholar_graph.fetch_pending(store, AUTHORS, CONFIG)
    assert not store.meta('initialized')
    store.close()


def test_later_malformed_mail_rolls_back_entire_batch(tmp_path, monkeypatch):
    base = scholar_graph.delta_url(CONFIG)
    graph(monkeypatch, [{'value': [item()], '@odata.deltaLink': base + '?delta=1'}], body='<html>Changed</html>')
    store = Store(tmp_path / 's.db')
    with pytest.raises(scholar_email.MailboxError, match='layout'):
        scholar_graph.fetch_pending(store, AUTHORS, CONFIG)
    assert not store.db.execute("SELECT 1 FROM metadata WHERE key LIKE 'scholar_graph_cursor:%'").fetchone()
    store.close()


@pytest.mark.parametrize('status', [401, 403, 410, 429, 503])
def test_graph_errors_never_expose_tokens(monkeypatch, status):
    from types import SimpleNamespace
    def fail(*a, **kw):
        raise urllib.error.HTTPError('https://private-cursor', status, 'never-print-me', {}, None)
    monkeypatch.setattr(scholar_graph.urllib.request, 'build_opener', lambda *a: SimpleNamespace(open=fail))
    with pytest.raises(scholar_email.MailboxError) as got:
        scholar_graph.request('https://graph.microsoft.com/v1.0/test', token='private-token')
    assert 'never-print-me' not in str(got.value) and 'private' not in str(got.value)
    assert ('expired' if status == 410 else str(status)) in str(got.value)
    assert scholar_graph.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil') is None


def test_scholar_only_name_watchlist_and_first_alert_is_pending(env):
    _, run, statuses, _, mp, path = env
    mp.setenv('MONITOR_SOURCE', 'scholar')
    mp.setenv('DEEP_LOOKBACK_DAYS', '365')
    (path / 'authors.csv').write_text('name\nAnatole von Lilienfeld\n')
    mp.setattr(cli.openalex, 'recent_works', lambda *a: pytest.fail('OpenAlex must stay disabled'))
    mp.setattr(cli.arxiv, 'recent_preprints', lambda *a: pytest.fail('arXiv polling must stay disabled'))
    mp.setattr(scholar_email, '_config', CONFIG)
    graph(mp, [{'value': [item()], '@odata.deltaLink': scholar_graph.delta_url(CONFIG) + '?delta=1'},
               {'value': [item()], '@odata.deltaLink': scholar_graph.delta_url(CONFIG) + '?delta=2'}])
    assert run('--dry-run') == 0
    assert len(statuses()) == 2 and set(statuses().values()) == {'pending'}
    assert run('--dry-run') == 0 and len(statuses()) == 2
    store = Store(path / 'state.db')
    summary = json.loads(store.meta('last_run_summary'))
    assert summary['source'] == 'scholar' and summary['mailbox_poll_ok'] and not summary['deep_scan']
    store.close()


def test_scholar_missing_config_cannot_seed_or_succeed(env):
    _, run, _, _, mp, path = env
    mp.setenv('MONITOR_SOURCE', 'scholar')
    mp.setattr(scholar_email, '_config', None)
    assert run('--dry-run') == 1
    store = Store(path / 'state.db')
    assert not store.meta('initialized') and store.counts() == {}
    store.close()


def test_waiting_is_not_recovery_and_delivery_errors_stay_visible(monkeypatch):
    settings = {'monitoring': {'source': 'scholar', 'state': 'awaiting_mailbox'}}
    h = {'last_success_at': 1, 'failed_task_at': 2, 'last_exit': 1, 'summary': {'errors': ['openalex']}}
    monkeypatch.setenv('MONITOR_COLLECTOR_ALARM_PREFIX', 'collector-')
    alarms = [{'AlarmName': 'collector-fail', 'StateValue': 'ALARM'}]
    assert health.problems(h, settings, alarms, now=100000) == {}
    h['summary'].update(delivery_counts={'sending': 1}, errors=['slack'])
    assert set(health.problems(h, settings, alarms, now=100000)) == {'delivery_uncertain', 'run_failed'}
    assert 'alarm:slack-fail' in health.problems(h, settings, [{'AlarmName': 'slack-fail', 'StateValue': 'ALARM'}])
    h['summary'] = {'errors': ['openalex']}
    saved = {}
    monkeypatch.setattr(registry, 'get', lambda k: settings if k == 'settings' else h)
    monkeypatch.setattr(registry, 'put', lambda k, v: saved.update({k: v}))
    monkeypatch.setattr(health, 'notify', lambda *_: pytest.fail('Pause must not send recovery'))
    monkeypatch.setenv('MONITOR_ALARMS', '[]')
    assert health.handler({}, None)['status'] == 'awaiting_mailbox'
    assert saved['monitor-watchdog']['sent'] is False
    assert 'OpenAlex polling is disabled' in slack_app.monitor_status(settings)


def test_scholar_stale_after_three_missed_polls():
    settings = {'monitoring': {'source': 'scholar', 'state': 'active'}}
    assert not health.problems({'last_success_at': 10000}, settings, [], now=12000)
    assert health.problems({'last_success_at': 10000}, settings, [], now=13000) == {
        'stale': 'No complete successful collection in the last 45 minutes.'}


def test_setup_empty_folder_is_not_real_publication_acceptance(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / 'deploy'))
    setup = importlib.import_module('configure_scholar_graph')
    graph(monkeypatch, [{'displayName': CONFIG['folder']},
        {'value': [item('control', 'Confirm your Scholar alert')],
         '@odata.deltaLink': scholar_graph.delta_url(CONFIG) + '?delta=1'}])
    config, report = setup.verify(CONFIG, AUTHORS)
    assert config['verified_at'] and not config['publication_sample_verified']
    assert report['mailbox_access_verified'] and not report['schedule_enabled']
    assert 'delta_link' not in config


def test_graph_registry_accepts_only_verified_config(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setenv('SCHOLAR_CONFIG_PARAMETER', '/config')
    monkeypatch.setattr(scholar_email, '_config', None)
    monkeypatch.setattr(registry, 'client', lambda _: SimpleNamespace(
        get_parameter=lambda **kw: {'Parameter': {'Value': json.dumps(CONFIG)}}))
    registry.configure_scholar()
    assert scholar_email.configuration()['provider'] == 'graph'
    with pytest.raises(scholar_email.MailboxError):
        scholar_graph.validate_config({**CONFIG, 'verified_at': None})
