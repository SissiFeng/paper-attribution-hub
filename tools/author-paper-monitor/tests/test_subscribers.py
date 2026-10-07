import copy
import datetime as dt
import hashlib
import hmac
import json
import time

import pytest

from paper_monitor import cli, fanout, registry, slack_app, slack_handler, slack_worker, subscriptions
from paper_monitor.models import Paper
from paper_monitor.store import Store
from test_slack_app import state as state, event


def signed_json(payload):
    stamp = str(int(time.time()))
    body = json.dumps(payload)
    signature = 'v0=' + hmac.new(b'signing', f'v0:{stamp}:{body}'.encode(), hashlib.sha256).hexdigest()
    return {'rawPath': '/slack', 'requestContext': {'http': {'method': 'POST'}}, 'body': body,
            'headers': {'X-Slack-Request-Timestamp': stamp, 'X-Slack-Signature': signature, 'Content-Type': 'application/json'}}


def test_home_event_enrolls_member_once_without_resuming_paused_subscription(state):
    data, jobs = state
    payload = {'type': 'event_callback', 'team_id': 'T1', 'event_id': 'Ev1',
               'event': {'type': 'app_home_opened', 'user': 'U2', 'tab': 'home'}}
    request = signed_json(payload)
    assert slack_handler.handler(request, None)['statusCode'] == 200
    assert data['subscriber:U2']['enabled'] and len(jobs) == 1
    slack_handler.handler(request, None)
    assert len(jobs) == 1
    slack_handler.handler(event('pause', user='U2'), None)
    payload['event_id'] = 'Ev2'
    slack_handler.handler(signed_json(payload), None)
    assert not data['subscriber:U2']['enabled']
    assert data['settings']['owner_id'] == 'U1'


def test_events_require_signature_and_installed_workspace(state):
    challenge = signed_json({'type': 'url_verification', 'challenge': 'test-challenge'})
    assert json.loads(slack_handler.handler(challenge, None)['body']) == {'challenge': 'test-challenge'}
    challenge['headers']['X-Slack-Signature'] = 'bad'
    assert slack_handler.handler(challenge, None)['statusCode'] == 401
    other = signed_json({'type': 'event_callback', 'team_id': 'T2', 'event_id': 'Ev2',
                         'event': {'type': 'app_home_opened', 'user': 'U2'}})
    assert slack_handler.handler(other, None)['statusCode'] == 403
    assert 'subscriber:U2' not in state[0]


def test_home_test_button_is_available_to_nonowner_and_ignores_supplied_channel(state):
    data, jobs = state
    before = copy.deepcopy(data['settings'])
    payload = {'type': 'block_actions', 'team': {'id': 'T1'}, 'user': {'id': 'U2'},
               'channel': {'id': 'CUNRELATED'}, 'actions': [{'action_id': 'test'}]}
    result = slack_handler.handler(signed_json(payload), None)
    assert 'own private conversation' in result['body']
    assert jobs[0][:2] == ('preview', {'user': 'U2'})
    assert data['subscriber:U2']['enabled']
    assert data['settings'] == before


def test_welcome_and_preview_are_bound_to_the_requesting_member(state, monkeypatch):
    data, _ = state
    before = copy.deepcopy(data['settings'])
    calls = []

    def api(token, method, payload):
        calls.append((method, payload))
        return {'channel': {'id': 'D2'}, 'ts': '123.1'}

    monkeypatch.setattr(slack_app, 'api', api)
    monkeypatch.setattr(slack_worker, 'preview_papers', lambda: [Paper('Real catalogue paper')])
    subscriptions.request('U2')
    slack_worker.process('home', {'user': 'U2'}, 'home1', {'bot_token': 'x'})
    slack_worker.process('home', {'user': 'U2'}, 'home2', {'bot_token': 'x'})
    assert len([m for m, _ in calls if m == 'chat.postMessage']) == 1
    assert calls[0] == ('conversations.open', {'users': 'U2'})
    slack_worker.process('preview', {'user': 'U2'}, 'preview', {'bot_token': 'x'})
    assert all(p['channel'] == 'D2' for m, p in calls if m == 'chat.postMessage')
    assert data['subscriber:U2']['tested_channel'] == 'D2'
    assert data['settings'] == before
    home = next(p['view'] for m, p in calls if m == 'views.publish')
    assert 'Add an author' not in json.dumps(home)


@pytest.fixture
def delivery(tmp_path, monkeypatch):
    now = dt.datetime(2026, 10, 6, 12, tzinfo=dt.timezone.utc)
    stamp = now.isoformat(timespec='seconds')
    monkeypatch.setattr('paper_monitor.store._now', lambda: stamp)
    monkeypatch.setattr(fanout, '_now', lambda: stamp)
    monkeypatch.setattr(time, 'sleep', lambda _: None)
    monkeypatch.setenv('SLACK_BOT_TOKEN', 'test')
    store = Store(tmp_path/'state.db')
    members = [{'user_id': u, 'channel_id': d, 'since': stamp, 'enabled': True} for u, d in [('U1', 'D1'), ('U2', 'D2')]]
    fanout.initialize(store, members, 'U1')
    row = store.insert(Paper('New paper', doi='10.1/new'), 'pending')
    store.mark_synced(row, 'pas1')
    calls = []
    monkeypatch.setattr(slack_app, 'api', lambda *a: calls.append(a[2]) or {'ts': f'{len(calls)}.001'})
    yield store, row, members, calls, now
    store.close()


def test_two_members_each_receive_once_and_have_separate_weekly_threads(delivery):
    store, row, members, calls, now = delivery
    assert not fanout.send_all(store, members=members, owner='U1', refresh=False, now=now)
    assert [p['channel'] for p in calls] == ['D1', 'D2']
    assert store.counts() == {'available': 1}
    assert store.db.execute('SELECT COUNT(*) FROM ingestion WHERE pas_id IS NOT NULL').fetchone()[0] == 1
    assert not fanout.send_all(store, members=members, refresh=False, now=now)
    assert len(calls) == 2
    assert not fanout.send_all(store, members=members, refresh=False, now=now+dt.timedelta(days=6))
    assert len(calls) == 6
    for user in ('U1', 'U2'):
        state = json.loads(fanout.RecipientStore(store, user).meta('weekly_recap'))
        assert state['status'] == 'complete' and state['page_receipts']['0']
    assert not fanout.send_all(store, members=members, refresh=False, now=now+dt.timedelta(days=6))
    assert len(calls) == 6


def test_pausing_one_member_does_not_pause_other_and_resume_retains_backlog(delivery):
    store, row, members, calls, now = delivery
    members[0]['enabled'] = False
    assert not fanout.send_all(store, members=members, refresh=False, now=now)
    assert [p['channel'] for p in calls] == ['D2']
    members[0]['enabled'] = True
    assert not fanout.send_all(store, members=members, refresh=False, now=now)
    assert [p['channel'] for p in calls] == ['D2', 'D1']


def test_later_subscriber_does_not_get_historical_papers(delivery):
    store, row, members, calls, now = delivery
    fanout.send_all(store, members=members, refresh=False, now=now)
    members.append({'user_id': 'U3', 'channel_id': 'D3', 'enabled': True, 'since': (now+dt.timedelta(seconds=1)).isoformat()})
    fanout.send_all(store, members=members, refresh=False, now=now)
    assert len(calls) == 2
    assert not store.db.execute("SELECT 1 FROM deliveries WHERE user_id='U3'").fetchone()


def test_one_uncertain_delivery_does_not_block_others_and_reconciles_separately(delivery, monkeypatch, tmp_path):
    store, row, members, calls, now = delivery

    def api(*args):
        calls.append(args[2])
        if args[2]['channel'] == 'D1':
            raise TimeoutError()
        return {'ts': '2.001'}

    monkeypatch.setattr(slack_app, 'api', api)
    assert fanout.send_all(store, members=members, refresh=False, now=now)
    assert store.db.execute('SELECT user_id,status FROM deliveries ORDER BY user_id').fetchall() == [('U1', 'sending'), ('U2', 'posted')]
    fanout.send_all(store, members=members, refresh=False, now=now)
    assert len(calls) == 2
    assert cli.main(['reconcile', '--db', str(tmp_path/'state.db'), '--id', str(row), '--recipient', 'U1', '--delivered']) == 0
    assert not fanout.send_all(store, members=members, refresh=False, now=now)
    assert len(calls) == 2


def test_storage_receipt_required_for_every_recipient(delivery):
    store, row, members, calls, now = delivery
    store.db.execute('UPDATE ingestion SET pas_id=NULL')
    store.commit()
    fanout.send_all(store, members=members, refresh=False, now=now)
    assert calls == []
    store.mark_synced(row, 'pas1')
    assert not fanout.send_all(store, members=members, refresh=False, now=now)
    assert len(calls) == 2


def test_legacy_migration_preserves_operator_receipts_and_uncertainty(tmp_path):
    store = Store(tmp_path/'s.db')
    for status in ('seeded', 'posted', 'sending', 'pending'):
        store.insert(Paper(status, doi='10.1/'+status), status)
    old = {'week': '2026-10-05', 'status': 'sending', 'ids': [2], 'channel': 'D1', 'pages': {}}
    store.set_meta('weekly_recap', json.dumps(old))
    members = [{'user_id': 'U1', 'channel_id': 'D1'}, {'user_id': 'U2', 'channel_id': 'D2'}]
    fanout.initialize(store, members, 'U1')
    assert store.db.execute('SELECT user_id,status FROM deliveries ORDER BY paper_id').fetchall() == [('U1', 'posted'), ('U1', 'sending'), ('U1', 'pending')]
    assert json.loads(fanout.RecipientStore(store, 'U1').meta('weekly_recap')) == old
    assert not fanout.RecipientStore(store, 'U2').meta('weekly_recap')
    fanout.initialize(store, members, 'U1')
    assert store.db.execute('SELECT COUNT(*) FROM deliveries').fetchone()[0] == 3
    store.close()


def test_pause_is_rechecked_before_each_member_batch(delivery, monkeypatch):
    store, row, members, calls, now = delivery
    monkeypatch.setattr(registry, 'get', lambda k: {**members[0], 'enabled': False} if k.endswith('U1') else members[1])
    assert not fanout.send_all(store, members=members, refresh=True, now=now)
    assert [p['channel'] for p in calls] == ['D2']


def test_checkpoint_loss_after_acceptance_does_not_replay_or_block_other_member(tmp_path, monkeypatch):
    replica = {'fail': False}
    path = tmp_path/'replica.db'

    class Checkpoint(Store):
        def commit(self):
            super().commit()
            if replica['fail'] and self.db.execute("SELECT 1 FROM deliveries WHERE status='posted'").fetchone():
                raise OSError('Cloud checkpoint unavailable after accepted delivery')
            replica['bytes'] = self.db.serialize()

    store = Checkpoint(path)
    members = [{'user_id': u, 'channel_id': d, 'enabled': True, 'since': '2020-01-01'} for u, d in [('U1', 'D1'), ('U2', 'D2')]]
    fanout.initialize(store, members, 'U1')
    row = store.insert(Paper('Real paper', doi='10.1/x'), 'pending')
    store.mark_synced(row, 'pas1')
    calls = []
    monkeypatch.setenv('SLACK_BOT_TOKEN', 'test')
    monkeypatch.setattr(time, 'sleep', lambda _: None)
    monkeypatch.setattr(slack_app, 'api', lambda *a: calls.append(a[2]) or {'ts': '1.001'})
    replica['fail'] = True
    with pytest.raises(OSError, match='checkpoint unavailable'):
        fanout.send_all(store, members=members, refresh=False)
    store.close()
    path.write_bytes(replica['bytes'])
    replica['fail'] = False
    store = Checkpoint(path)
    assert fanout.send_all(store, members=members, refresh=False)
    assert [p['channel'] for p in calls] == ['D1', 'D2']
    assert store.db.execute('SELECT user_id,status FROM deliveries ORDER BY user_id').fetchall() == [('U1', 'sending'), ('U2', 'posted')]
    store.close()


def test_recipient_recap_reconciliation_does_not_touch_another_member(delivery, tmp_path):
    store, row, members, calls, now = delivery
    original = {'status': 'sending', 'week': '2026-10-05', 'ids': [row], 'pages': {}}
    for user in ('U1', 'U2'):
        fanout.RecipientStore(store, user).set_meta('weekly_recap', json.dumps(original))
    store.commit()
    assert cli.main(['reconcile-recap', '--db', str(tmp_path/'state.db'), '--recipient', 'U2', '--thread-ts', '123.456']) == 0
    assert json.loads(fanout.RecipientStore(store, 'U1').meta('weekly_recap')) == original
    assert json.loads(fanout.RecipientStore(store, 'U2').meta('weekly_recap'))['ts'] == '123.456'


def test_global_delivery_budget_rotates_recipients_fairly(delivery):
    store, row, members, calls, now = delivery
    for i in range(3, 12):
        members.append({**members[0], 'user_id': f'U{i}', 'channel_id': f'D{i}'})
    for i in range(20):
        added = store.insert(Paper(f'Paper {i}', doi=f'10.1/{i}'), 'pending')
        store.mark_synced(added, f'pas{i+2}')
    fanout.send_all(store, members=members, refresh=False, now=now)
    assert len(calls) == 200
    missed = ({m['channel_id'] for m in members} - {p['channel'] for p in calls}).pop()
    fanout.send_all(store, members=members, refresh=False, now=now)
    assert calls[200]['channel'] == missed
