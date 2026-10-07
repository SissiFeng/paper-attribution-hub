"""Eight workflow contracts, persistent limits and failure isolation (synthetic)."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import time
from types import SimpleNamespace

import pytest

from paper_monitor import jev, jev_ledger, jev_monitor, jev_tasks, registry
from paper_monitor.models import Paper


@pytest.fixture(autouse=True)
def local_runtime(monkeypatch, tmp_path):
    for name in ('SLACK_TABLE', 'JEV_CONFIG_PARAMETER', 'JEV_FOCUS', 'JEV_MODEL'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('JEV_MODE', 'shadow')
    monkeypatch.setenv('TYPESAFE_API_KEY', 'synthetic-secret')
    monkeypatch.setenv('JEV_STATE_DB', str(tmp_path/'decisions.db'))
    monkeypatch.setenv('JEV_DAILY_CALL_LIMIT', '20')
    monkeypatch.setattr(jev, 'exchange', fake_exchange)


def fake_exchange(payload, *_a, **_k):
    spec = payload['questions']['decision']
    if spec['type'] == 'choice':
        keys = list(spec['criteria'])
        answer = {'type': 'choice', 'choice': keys[0], 'confidence': 0.8,
                  'probabilities': {key: float(i == 0) for i, key in enumerate(keys)}}
    else:
        answer = {'type': 'score', 'score': 3.0, 'confidence': 0.8,
                  'probabilities': {str(i): float(i == 3) for i in range(len(spec['criteria']))},
                  'legend': {str(i): v for i, v in enumerate(spec['criteria'])}}
    return {'model': jev.MODEL, 'answers': {'decision': answer}, 'usage': {'input_tokens': 1000, 'output_tokens': 50}}


def context(task):
    p = {'title': 'A robotic catalyst experiment', 'abstract': 'We used a robot for chemistry.', 'doi': '10.1/a', 'authors': ['A']}
    if task == 'author_identity':
        return {'target': {'name': 'A', 'institution': 'UofT'}, 'candidate': {'name': 'A', 'institution': 'UofT'}}
    if task == 'version_relation':
        return {'left': p, 'right': {**p, 'doi': '10.1/b'}}
    if task in ('reading_priority', 'analysis_route', 'review_priority'):
        return {'paper': p, 'signals': ['Metadata only']}
    if task == 'retrieval_route':
        return {'query': 'How many papers are stored?'}
    return {'claim': 'The study used a robot.', 'quote': 'We used a robot for chemistry.',
            'source_text': 'We used a robot for chemistry.', 'source_id': 'c1', 'paper_id': 'p1',
            'subject': 'This study', 'relation': 'uses instrument', 'object': 'robot'}


@pytest.mark.parametrize('task', list(jev_tasks.SPECS))
def test_eight_contracts_execute_cache_and_record_without_actions(task, monkeypatch):
    calls = []
    monkeypatch.setattr(jev, 'exchange', lambda *a, **k: calls.append(a) or fake_exchange(*a, **k))
    value = context(task)
    value['slack_token'] = 'never-send-this'
    original = copy.deepcopy(value)
    result = jev_tasks.evaluate(task, value)
    assert result['status'] == 'ok' and result['automatic_action'] is False
    assert result['usage']['input_tokens'] == 1000
    assert jev_tasks.evaluate(task, value)['cached'] is True
    assert len(calls) == 1 and value == original
    assert 'never-send-this' not in json.dumps(calls)
    assert 'synthetic-secret' not in json.dumps(jev_ledger.journal().recent())


@pytest.mark.parametrize('task', list(jev_tasks.SPECS))
def test_all_workflows_no_key_make_zero_paid_calls(task, monkeypatch):
    monkeypatch.delenv('TYPESAFE_API_KEY')
    monkeypatch.setattr(jev, 'exchange', lambda *a, **k: pytest.fail('A key is required'))
    result = jev_tasks.evaluate(task, context(task))
    assert result['status'] == 'needs_configuration' and 'decision' not in result


def test_cross_task_cap_is_persistent(monkeypatch):
    monkeypatch.setenv('JEV_DAILY_CALL_LIMIT', '2')
    assert jev_tasks.evaluate('reading_priority', context('reading_priority'))['status'] == 'ok'
    assert jev_tasks.evaluate('retrieval_route', context('retrieval_route'))['status'] == 'ok'
    assert jev_tasks.evaluate('graph_relation', context('graph_relation'))['status'] == 'daily_limit_reached'
    assert jev_tasks.evaluate('reading_priority', context('reading_priority'))['cached']


def test_parallel_identical_requests_only_pay_once(monkeypatch):
    ledger = jev_ledger.journal()
    calls = []
    def slow(*a, **k):
        calls.append(1)
        time.sleep(0.05)
        return fake_exchange(*a, **k)
    monkeypatch.setattr(jev, 'exchange', slow)
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda _: jev_tasks.evaluate('retrieval_route', context('retrieval_route'), ledger=ledger), range(8)))
    assert len(calls) == 1
    assert all(r['status'] in ('ok', 'started') for r in results)
    assert jev_tasks.evaluate('retrieval_route', context('retrieval_route'))['status'] == 'ok'


def test_changed_focus_invalidates_cache(monkeypatch):
    a = jev_tasks.evaluate('retrieval_route', context('retrieval_route'))
    monkeypatch.setenv('JEV_FOCUS', 'Battery materials')
    b = jev_tasks.evaluate('retrieval_route', context('retrieval_route'))
    assert a['decision_id'] != b['decision_id'] and not b.get('cached')


def test_invalid_evidence_and_protected_records_never_call(monkeypatch):
    monkeypatch.setattr(jev, 'exchange', lambda *a, **k: pytest.fail('No model authority here'))
    evidence = context('answer_evidence')
    evidence['quote'] = 'Fabricated passage'
    assert jev_tasks.evaluate('answer_evidence', evidence)['status'] == 'unavailable'
    review = context('review_priority')
    review['human_resolved'] = True
    assert jev_tasks.evaluate('review_priority', review)['status'] == 'protected_record'
    pair = context('version_relation')
    pair['right']['doi'] = pair['left']['doi']
    assert jev_tasks.evaluate('version_relation', pair)['status'] == 'deterministic_identity'
    author = context('author_identity')
    author['target']['orcid'], author['candidate']['orcid'] = '0000-1', '0000-2'
    assert jev_tasks.evaluate('author_identity', author)['status'] == 'identifier_conflict'


def test_malformed_probability_and_timeout_are_redacted(monkeypatch):
    def malformed(*a, **k):
        raw = fake_exchange(*a, **k)
        raw['answers']['decision']['probabilities']['malicious'] = 0.5
        return raw
    monkeypatch.setattr(jev, 'exchange', malformed)
    assert jev_tasks.evaluate('retrieval_route', context('retrieval_route'))['status'] == 'error'
    def fail(*a, **k):
        raise TimeoutError('Credentials should not appear: synthetic-secret')
    monkeypatch.setattr(jev, 'exchange', fail)
    result = jev_tasks.evaluate('analysis_route', context('analysis_route'))
    assert result['error_type'] == 'TimeoutError' and 'synthetic-secret' not in json.dumps(result)
    assert jev_tasks.evaluate('analysis_route', context('analysis_route'))['cached']


def test_version_shortlist_is_non_mutating_and_skips_strong_matches():
    left = Paper('Automated optimization of complex reaction systems', authors=['A'], doi='10.1/a')
    right = Paper('Automated optimization of complex reaction systems with robotics', authors=['A'], doi='10.1/b')
    rows = [(1, left), (2, right), (3, Paper(left.title, authors=['A'], doi=left.doi))]
    pairs = jev_monitor.version_candidates(rows)
    assert any(p[1] == 1 and p[3] == 2 for p in pairs)
    assert not any(p[1] == 1 and p[3] == 3 for p in pairs)
    assert left.doi == '10.1/a' and right.doi == '10.1/b'


def test_dynamo_atomic_allowance_and_cached_response(monkeypatch):
    from botocore.exceptions import ClientError
    values, attempts = {}, []
    def change(key, edit):
        value = copy.deepcopy(values.get(key, {}))
        edit(value)
        values[key] = value
        return value
    def update(**kwargs):
        assert kwargs['ConditionExpression'] == 'attribute_not_exists(attempts) OR attempts < :limit'
        if len(attempts) >= kwargs['ExpressionAttributeValues'][':limit']:
            raise ClientError({'Error': {'Code': 'ConditionalCheckFailedException'}}, 'UpdateItem')
        attempts.append(1)
    monkeypatch.setenv('JEV_DAILY_CALL_LIMIT', '1')
    monkeypatch.setattr(registry, 'change', change)
    monkeypatch.setattr(registry, 'put', lambda k, v: values.update({k: copy.deepcopy(v)}))
    monkeypatch.setattr(registry, 'get', lambda k: copy.deepcopy(values.get(k, {})))
    monkeypatch.setattr(registry, 'table', lambda: SimpleNamespace(update_item=update))
    ledger = jev_ledger.DynamoJournal()
    first = jev_tasks.evaluate('reading_priority', context('reading_priority'), ledger=ledger)
    assert first['status'] == 'ok'
    assert jev_tasks.evaluate('reading_priority', context('reading_priority'), ledger=ledger)['cached']
    assert jev_tasks.evaluate('retrieval_route', context('retrieval_route'), ledger=ledger)['status'] == 'daily_limit_reached'
    assert len(attempts) == 1


def test_eight_task_evaluation_does_not_invent_accuracy_and_preserves_labels(tmp_path):
    from paper_monitor import jev_evaluation
    records = [jev_tasks.evaluate(task, context(task)) for task in jev_tasks.SPECS]
    empty = jev_evaluation.metrics(records)
    assert all(v == {'labelled': 0} for v in empty['tasks'].values())
    records[0]['human_feedback'] = {'label': 'different_person'}
    measured = jev_evaluation.metrics(records)
    assert measured['tasks']['author_identity']['accuracy'] == 0
    assert measured['tasks']['author_identity']['multiclass_brier'] == 2
    jev_evaluation.export(records, tmp_path)
    labels = tmp_path/'jev-workflow-labels.csv'
    assert 'probabilities' not in labels.read_text()
    labels.write_text('Human work')
    jev_evaluation.export(records, tmp_path)
    assert labels.read_text() == 'Human work'


def test_blind_labels_import_validates_all_before_writing(tmp_path):
    import csv
    from paper_monitor import jev_evaluation
    records = [jev_tasks.evaluate(t, context(t)) for t in ('reading_priority', 'retrieval_route')]
    jev_evaluation.export(records, tmp_path)
    path = tmp_path/'jev-workflow-labels.csv'
    with path.open() as f:
        reader = csv.DictReader(f)
        rows, fields = list(reader), reader.fieldnames
    rows[0]['human_label'], rows[1]['human_label'] = '2', 'invalid-route'
    def save():
        with path.open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    save()
    ledger = jev_ledger.journal()
    with pytest.raises(ValueError, match='Invalid label'):
        jev_evaluation.import_labels(ledger, path, 'human')
    assert 'human_feedback' not in ledger.get(records[0]['decision_id'])
    rows[1]['human_label'] = 'fulltext_search'
    save()
    assert jev_evaluation.import_labels(ledger, path, 'human') == 2
    assert ledger.get(records[0]['decision_id'])['human_feedback']['label'] == '2'
