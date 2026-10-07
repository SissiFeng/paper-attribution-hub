import copy
import datetime
import hashlib
import hmac
import io
import json
import time
import urllib.error
import urllib.parse
from pathlib import Path

import pytest

from paper_monitor import digest, http, registry, slack_app, slack_handler, slack_worker
from paper_monitor.models import Paper
from paper_monitor.store import Store


@pytest.fixture
def state(monkeypatch):
    data = {'settings': {'owner_id': 'U1', 'channel_id': 'D1', 'enabled': False}}
    jobs = []
    monkeypatch.setattr(registry, 'get', lambda k: copy.deepcopy(data.get(k, {})))
    def put(k, v, **kw):
        data[k] = copy.deepcopy(v)
    monkeypatch.setattr(registry, 'put', put)
    def change(k, fn):
        value = copy.deepcopy(data.get(k, {}))
        fn(value)
        data[k] = value
        return value
    monkeypatch.setattr(registry, 'change', change)
    monkeypatch.setattr(registry, 'authors', lambda: [v for k, v in data.items() if k.startswith('author:')])
    monkeypatch.setattr(registry, 'credentials', lambda: {'team_id': 'T1', 'bot_token': 'secret-token', 'signing_secret': 'signing'})
    monkeypatch.setattr(slack_handler, 'enqueue', lambda *args: jobs.append(args))
    monkeypatch.setattr(time, 'sleep', lambda _: None)
    return data, jobs


def event(text, *, user='U1', channel='D1', stamp=None, team='T1'):
    stamp = str(stamp or int(time.time()))
    body = urllib.parse.urlencode({'text': text, 'command': '/papers', 'user_id': user, 'channel_id': channel, 'team_id': team, 'trigger_id': 'trigger'})
    sig = 'v0=' + hmac.new(b'signing', f'v0:{stamp}:{body}'.encode(), hashlib.sha256).hexdigest()
    return {'rawPath': '/slack', 'requestContext': {'http': {'method': 'POST'}}, 'body': body,
            'headers': {'X-Slack-Request-Timestamp': stamp, 'X-Slack-Signature': sig, 'Content-Type': 'application/x-www-form-urlencoded'}}


def test_signature_timestamp_raw_body(state):
    original = event('status')
    assert slack_handler.handler(original, None)['statusCode'] == 200
    original['body'] += 'x'
    assert slack_handler.handler(original, None)['statusCode'] == 401
    assert slack_handler.handler(event('status', stamp=int(time.time())-301), None)['statusCode'] == 401
    assert slack_handler.handler(event('status', team='T2'), None)['statusCode'] == 403


def test_duplicate_command_acks_once(state):
    request = event('test')
    assert slack_handler.handler(request, None) == slack_handler.handler(request, None)
    assert len(state[1]) == 1


def test_connection_code_binds_once_and_disables_delivery(state):
    data, _ = state
    data['settings'] = {'connect_hash': hashlib.sha256(b'CODE').hexdigest(), 'connect_expires': time.time()+60}
    result = slack_handler.handler(event('connect CODE'), None)
    assert 'private conversation' in result['body']
    assert data['settings']['owner_id'] == 'U1'
    assert data['settings']['connect_hash'] == ''
    assert data['settings']['enabled'] is False
    assert 'another operator' in slack_handler.handler(event('connect CODE', user='U2'), None)['body']


def test_start_enables_only_requesting_members_subscription(state):
    data, _ = state
    slack_handler.handler(event('start'), None)
    assert data['subscriber:U1']['enabled'] is True
    assert data['settings']['enabled'] is False


def test_non_operator_cannot_change_shared_watchlist(state):
    assert 'Only the connected operator' in slack_handler.handler(event('add', user='U2'), None)['body']
    assert not state[1]


@pytest.mark.parametrize('command', ['start', 'pause', 'test', 'digest', 'review', 'decisions'])
def test_members_can_manage_only_their_own_delivery(state, command):
    data, jobs = state
    before = copy.deepcopy(data['settings'])
    result = slack_handler.handler(event(command, user='U2', channel='C_GROUP'), None)
    assert 'Only the connected operator' not in result['body']
    assert data['subscriber:U2']['enabled'] == (command != 'pause')
    assert jobs[0][1]['user'] == 'U2' and 'channel' not in jobs[0][1]
    assert data['settings'] == before


def test_add_opens_modal_without_external_search(state, monkeypatch):
    calls = []
    monkeypatch.setattr(slack_app, 'api', lambda *a, **kw: calls.append((a, kw)) or {'ok': True})
    slack_handler.handler(event('add'), None)
    assert calls[0][0][1] == 'views.open'
    assert calls[0][1]['timeout'] < 2


def test_expired_candidate_cannot_be_added(state):
    payload = {'type': 'view_submission', 'team': {'id': 'T1'}, 'user': {'id': 'U1'}, 'view': {
        'callback_id': 'author_choose', 'private_metadata': 'old', 'state': {'values': {'author': {'value': {'selected_option': {'value': 'A123'}}}}}}}
    result = json.loads(slack_handler.handle(payload, {'team_id': 'T1'}, 'key')['body'])
    assert result['response_action'] == 'errors'
    assert not any(k.startswith('author:') for k in state[0])


def test_confirm_candidate_adds_active_author(state):
    data, _ = state
    data['lookup:key'] = {'user': 'U1', 'expires': time.time()+60, 'candidates': [
        {'id': 'A123', 'name': 'Researcher', 'orcid': '', 'institution': 'Toronto', 'works_count': 2}]}
    payload = {'type': 'view_submission', 'team': {'id': 'T1'}, 'user': {'id': 'U1'}, 'view': {
        'callback_id': 'author_choose', 'private_metadata': 'key', 'state': {'values': {'author': {'value': {'selected_option': {'value': 'A123'}}}}}}}
    slack_handler.handle(payload, {'team_id': 'T1'}, 'job')
    assert data['author:custom_A123']['openalex_ids'] == ['A123']
    assert data['author:custom_A123']['confirmed_by'] == 'U1'


def test_feedback_does_not_change_paper_relevance(state, monkeypatch):
    monkeypatch.setattr(slack_app, 'api', lambda *a, **kw: {'ok': True})
    slack_worker.process('feedback', {'paper': 'a'*32, 'user': 'U2', 'vote': 'feedback_no', 'channel': 'D1'}, 'key', {'bot_token': 'x'})
    assert state[0]['feedback:'+'a'*32+':U2']['vote'] == 'feedback_no'
    assert not state[0]['settings']['enabled']


def test_preview_marks_tested_only_after_all_thread_posts(state, monkeypatch):
    monkeypatch.setattr(slack_worker, 'preview_papers', lambda: [Paper(title='Real paper', doi='10.1/a')])
    calls = []
    def api(*args):
        calls.append(args)
        if len(calls) == 2:
            raise TimeoutError()
        return {'ts': '123.1'}
    monkeypatch.setattr(slack_app, 'api', api)
    with pytest.raises(TimeoutError):
        slack_worker.process('preview', {'user': 'U1', 'channel': 'D1'}, 'key', {'bot_token': 'x'})
    assert not state[0]['settings'].get('tested_channel')


def test_api_200_ok_false_is_failure_and_never_retried(monkeypatch):
    calls = []
    def open_(req, **kw):
        calls.append(req)
        return io.BytesIO(b'{"ok":false,"error":"not_in_channel"}')
    monkeypatch.setattr('urllib.request.urlopen', open_)
    with pytest.raises(slack_app.SlackRejected, match='not_in_channel'):
        slack_app.api('secret', 'chat.postMessage', {})
    assert len(calls) == 1


def seeded_store(tmp_path):
    store = Store(tmp_path/'state.db')
    store.set_meta('initialized', '1')
    p = Paper(title='New paper', doi='10.1/a', tracked_authors=['Author'])
    i = store.insert(p, 'pending')
    store.mark_synced(i, 'pas_1')
    return store, i


def test_digest_parent_and_thread_rerun_no_duplicate(tmp_path, monkeypatch):
    store, row = seeded_store(tmp_path)
    monkeypatch.setenv('SLACK_BOT_TOKEN', 'x')
    monkeypatch.setenv('SLACK_CHANNEL_ID', 'D1')
    monkeypatch.setattr(time, 'sleep', lambda _: None)
    calls = []
    monkeypatch.setattr(slack_app, 'api', lambda *a: calls.append(a) or {'ts': str(len(calls))})
    monday = datetime.datetime(2026, 10, 5, tzinfo=datetime.timezone.utc)
    assert not digest.send(store, store.pending(20), set(), now=monday)
    assert not digest.send(store, store.pending(20), set(), now=monday)
    assert len(calls) == 2
    assert calls[1][2]['thread_ts'] == '1'
    assert store.counts() == {'posted': 1}
    store.close()


def test_digest_uncertain_parent_not_replayed(tmp_path, monkeypatch):
    store, _ = seeded_store(tmp_path)
    monkeypatch.setenv('SLACK_BOT_TOKEN', 'x')
    monkeypatch.setenv('SLACK_CHANNEL_ID', 'D1')
    calls = []
    def api(*a):
        calls.append(a)
        raise TimeoutError()
    monkeypatch.setattr(slack_app, 'api', api)
    monday = datetime.datetime(2026, 10, 5, tzinfo=datetime.timezone.utc)
    assert digest.send(store, [], set(), now=monday)
    assert digest.send(store, [], set(), now=monday)
    assert len(calls) == 1
    assert store.counts() == {'pending': 1}
    store.close()


def test_digest_waits_for_monday_and_pas_receipts(tmp_path, monkeypatch):
    store, row = seeded_store(tmp_path)
    monkeypatch.setenv('SLACK_BOT_TOKEN', 'x')
    monkeypatch.setenv('SLACK_CHANNEL_ID', 'D1')
    monkeypatch.setattr(slack_app, 'api', lambda *a: pytest.fail('Must not post'))
    assert not digest.send(store, [], set(), now=datetime.datetime(2026, 10, 6))
    assert not digest.send(store, [], {row}, now=datetime.datetime(2026, 10, 5))
    store.close()


def test_roster_has_all_82_and_does_not_activate_unknown():
    rows = json.loads((Path(__file__).parents[1]/'config/ac_roster.json').read_text())
    assert len(rows) == 82
    assert len({r['person_id'] for r in rows}) == 82
    assert all(r['openalex_ids'] and r['representative_works'] for r in rows if r['status'] == 'active')
    assert next(r for r in rows if r['person_id'] == 'A061')['status'] == 'needs_review'
    assert next(r for r in rows if r['person_id'] == 'A002')['openalex_ids'][0] == 'A5088793872'


def test_block_limits_and_minimal_scopes():
    rows = json.loads((Path(__file__).parents[1]/'config/ac_roster.json').read_text())
    assert len(slack_app.home({}, rows)['blocks']) < 100
    assert len(slack_app.card(Paper(title='x'*4000, authors=['<@channel>']))['blocks']) < 50
    assert slack_app.manifest('https://example.com')['oauth_config']['scopes']['bot'] == ['chat:write', 'commands', 'im:write']
    assert '&lt;@channel&gt;' in json.dumps(slack_app.card(Paper(title='paper', tracked_authors=['<@channel>'])))


def test_home_action_ids_are_unique_within_each_block():
    rows = json.loads((Path(__file__).parents[1]/'config/ac_roster.json').read_text())
    for block in slack_app.home({}, rows)['blocks']:
        actions = [item['action_id'] for item in block.get('elements', []) if 'action_id' in item]
        assert len(actions) == len(set(actions))


def test_home_start_and_pause_are_personal(state):
    data, _ = state
    for user in ('U1', 'U2'):
        payload = {'type': 'block_actions', 'team': {'id': 'T1'}, 'user': {'id': user},
                   'actions': [{'action_id': 'notifications_start', 'value': 'U1'}]}
        slack_handler.handle(payload, {'team_id': 'T1'}, 'start-' + user)
    payload['actions'][0]['action_id'] = 'notifications_pause'
    slack_handler.handle(payload, {'team_id': 'T1'}, 'pause-U2')
    assert data['subscriber:U1']['enabled'] and not data['subscriber:U2']['enabled']
    assert not data['settings']['enabled']


def test_daily_rate_limit_exits_without_sleep(monkeypatch):
    def exhausted(*a, **kw):
        raise urllib.error.HTTPError('https://api.openalex.org', 429, 'budget', {'Retry-After': '7200'}, None)
    monkeypatch.setattr('urllib.request.urlopen', exhausted)
    monkeypatch.setattr(time, 'sleep', lambda _: pytest.fail('Daily budget cannot recover by sleeping'))
    with pytest.raises(urllib.error.HTTPError):
        http.get_json('https://api.openalex.org')


def test_personal_digest_rejects_group_channel(tmp_path, monkeypatch):
    store, _ = seeded_store(tmp_path)
    monkeypatch.setenv('SLACK_CHANNEL_ID', 'C_GROUP')
    monkeypatch.setattr(slack_app, 'api', lambda *a: pytest.fail('Group posts forbidden'))
    assert 'refusing a group' in digest.send(store, [], set())[0]
    store.close()


def test_connection_opens_only_requesting_users_dm(state, monkeypatch):
    data, _ = state
    data['settings'] = {'owner_id': 'U1', 'connection_key': 'key'}
    calls = []
    def api(token, method, payload):
        calls.append((method, payload))
        return {'channel': {'id': 'D_PRIVATE'}, 'ok': True}
    monkeypatch.setattr(slack_app, 'api', api)
    slack_worker.process('connect_dm', {'user': 'U1'}, 'key', {'bot_token': 'x'})
    assert calls[0] == ('conversations.open', {'users': 'U1'})
    assert calls[1][1]['channel'] == 'D_PRIVATE'
    assert data['settings']['channel_id'] == 'D_PRIVATE'


def test_baseline_is_ingested_but_not_notified(tmp_path):
    store = Store(tmp_path/'baseline.db')
    store.insert(Paper('Existing publication', doi='10.1/b'), 'seeded')
    assert len(store.unsynced()) == 1
    assert store.pending(20) == []
    store.close()


def test_dataset_excluded_from_paper_notifications(monkeypatch):
    from paper_monitor import openalex
    works = [{'id': 'https://openalex.org/W1', 'title': 'Software release', 'type': 'dataset'},
             {'id': 'https://openalex.org/W2', 'title': 'Research paper', 'type': 'article'}]
    params = []
    monkeypatch.setattr(http, 'get_json', lambda u, p: params.append(p) or {'results': works, 'meta': {'next_cursor': None}})
    papers = list(openalex.recent_works({'A1': 'Author'}, '2026-07-01'))
    assert [p.title for p in papers] == ['Research paper']
    assert 'to_publication_date:' in params[0]['filter']
    assert 'type:article|review|preprint|book-chapter' in params[0]['filter']


def test_jev_review_command_from_channel_targets_only_owner_dm(state):
    slack_handler.handler(event('review', channel='C_GROUP'), None)
    kind, payload, _ = state[1][0]
    assert kind == 'jev_review' and payload == {'user': 'U1'}


def test_jev_review_without_key_is_explicit_and_does_not_enable_updates(state, monkeypatch):
    data, _ = state
    data['settings']['jev_shadow'] = {'status': 'needs_configuration'}
    calls = []
    monkeypatch.setattr(slack_worker, 'shadow_report', lambda: {'scored': 0, 'items': []})
    monkeypatch.setattr(slack_app, 'api', lambda *a, **k: calls.append(a) or {'ok': True})
    slack_worker.process('jev_review', {'user': 'U1', 'channel': 'D1'}, 'test', {'bot_token': 'test'})
    assert len(calls) == 1 and calls[0][2]['channel'] == 'D1'
    assert 'waiting for an API key' in calls[0][2]['text']
    assert data['settings']['enabled'] is False


def test_jev_review_refuses_changed_owner_or_group_destination(state, monkeypatch):
    monkeypatch.setattr(slack_worker, 'shadow_report', lambda: pytest.fail('Must reject before reading data'))
    for user, channel in [('U2', 'D1'), ('U1', 'C_GROUP')]:
        with pytest.raises(ValueError, match='Connection changed'):
            slack_worker.process('jev_review', {'user': user, 'channel': channel}, 'key', {'bot_token': 'test'})


def test_jev_review_threads_scored_subset_and_retains_delivery_state(state, monkeypatch):
    from dataclasses import asdict
    data, _ = state
    before = copy.deepcopy(data['settings'])
    decision = {'priority_score': 3.2, 'next_step': 'fulltext_needed'}
    items = [dict(asdict(Paper('Paper ' + str(i), doi=f'10.1/{i}')), status='ok', suggested_rank=i+1, decision=decision) for i in range(4)]
    monkeypatch.setattr(slack_worker, 'shadow_report', lambda: {'papers': 10, 'scored': 4, 'items': items})
    calls = []
    monkeypatch.setattr(slack_app, 'api', lambda *a, **k: calls.append(a[2]) or {'ok': True, 'ts': '123.456'})
    slack_worker.process('jev_review', {'user': 'U1', 'channel': 'D1'}, 'test', {'bot_token': 'test'})
    assert len(calls) == 4 and all(p['channel'] == 'D1' for p in calls)
    assert '4 of 10' in calls[0]['text'] and 'evaluated subset' in calls[0]['text']
    assert all(p['thread_ts'] == '123.456' for p in calls[1:])
    assert 'No full paper was read' in json.dumps(calls[1])
    assert data['settings'] == before
    assert data['jev-preview:test']['status'] == 'posted'


def test_eight_workflow_overview_has_no_fabricated_scores():
    message = slack_app.decisions_message([])
    assert sum('Not evaluated yet' in str(b) for b in message['blocks']) == 8
    assert len(message['blocks']) < 50


def test_jev_feedback_only_saves_valid_label_for_operator(state, monkeypatch):
    from types import SimpleNamespace
    from paper_monitor import jev_ledger
    saved = []
    entry = {'task': 'graph_relation', 'status': 'ok', 'decision_id': 'a'*64}
    monkeypatch.setattr(jev_ledger, 'journal', lambda: SimpleNamespace(get=lambda _: entry, feedback=lambda *a: saved.append(a)))
    payload = {'type': 'view_submission', 'team': {'id': 'T1'}, 'user': {'id': 'U1'}, 'view': {
        'callback_id': 'jev_feedback', 'private_metadata': 'a'*64,
        'state': {'values': {'label': {'value': {'selected_option': {'value': 'mention_only'}}}}}}}
    assert json.loads(slack_handler.handle(payload, {'team_id': 'T1'}, 'key')['body'])['response_action'] == 'clear'
    assert saved == [('a'*64, 'mention_only', 'U1')]
    payload['user']['id'] = 'U2'
    with pytest.raises(ValueError, match='Only the connected'):
        slack_handler.handle(payload, {'team_id': 'T1'}, 'key')
    assert len(saved) == 1


def test_pas_login_only_signed_same_workspace_private_command(state):
    data, _ = state
    code = 'ABCD-1234-EF56'
    key = 'pas-login:' + hashlib.sha256(code.encode()).hexdigest()
    pending = {'expires': time.time()+120, 'browser_hash':'bound-browser', 'status':'pending'}
    data[key] = copy.deepcopy(pending)
    assert slack_handler.handler(event('login '+code,team='OTHER'),None)['statusCode']==403
    assert data[key] == pending
    assert 'private' in slack_handler.handler(event('login '+code,channel='C_GROUP'),None)['body'].lower()
    assert data[key] == pending
    result=slack_handler.handler(event('login '+code,user='U2'),None)
    assert result['statusCode']==200
    assert data[key]['user_id']=='U2' and data[key]['team_id']=='T1'
    from paper_monitor.pas_login import confirm
    with pytest.raises(ValueError): confirm(code,'U3','T1','Another person')
    assert data[key]['user_id']=='U2'
    data[key]['expires']=0
    with pytest.raises(ValueError): confirm(code,'U2','T1','Someone')


def test_pas_paper_card_deep_link_and_action_limit(monkeypatch):
    monkeypatch.setenv('PAS_PUBLIC_URL','https://pas.test')
    paper=Paper(title='Test paper',doi='10.1/test&x=1')
    blocks=slack_app.card(paper)['blocks']
    actions=next(block for block in blocks if block['type']=='actions')['elements']
    assert len(actions)<=5
    assert len({a['action_id'] for a in actions})==len(actions)
    target=next(a['url'] for a in actions if a.get('text',{}).get('text','').startswith('Open in PAS'))
    assert urllib.parse.parse_qs(urllib.parse.urlparse(target).query)['doi']==[paper.doi]
    assert urllib.parse.urlparse(target).path == '/papers'



def test_pas_card_uses_ingestion_receipt_for_aliases(monkeypatch):
    monkeypatch.setenv('PAS_PUBLIC_URL','https://pas.test')
    p=Paper(title='Already in PAS under another DOI',doi='10.1/alias',url='https://doi.org/10.1/alias')
    elements=slack_app.card(p,pas_id='DOI:10.1_canonical')['blocks'][-1]['elements']
    assert len({b['action_id'] for b in elements})==len(elements)==5
    target=next(b['url'] for b in elements if b['action_id']=='open_pas')
    assert target == 'https://pas.test/papers/DOI%3A10.1_canonical'
