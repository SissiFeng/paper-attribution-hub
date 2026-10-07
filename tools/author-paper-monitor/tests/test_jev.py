"""Synthetic API contract tests; these are not evidence of model quality."""
import csv
import importlib.util
import io
import json
import sqlite3
import time
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

from paper_monitor import jev, jev_report, registry
from paper_monitor.models import Paper
from paper_monitor.store import Store
from test_monitor import new_work


def wire_result():
    return {'model': jev.MODEL, 'usage': {'input_tokens': 500, 'output_tokens': 40}, 'answers': {
        'priority': {'type': 'score', 'score': 3.3, 'confidence': 0.5,
                     'legend': dict(enumerate(jev.LEVELS)),
                     'probabilities': {'0': 0, '1': 0, '2': 0.1, '3': 0.5, '4': 0.4}},
        'next_step': {'type': 'choice', 'choice': 'fulltext_needed', 'confidence': 0.6,
                      'probabilities': {'metadata_sufficient': 0.1, 'fulltext_needed': 0.8, 'manual_review': 0.1}}}}


@pytest.fixture
def response():
    # A wire roundtrip makes the legend's numeric JSON keys strings.
    return json.loads(json.dumps(wire_result()))


@pytest.fixture(autouse=True)
def config(monkeypatch):
    monkeypatch.setenv('JEV_MODE', 'shadow')
    monkeypatch.setenv('TYPESAFE_API_KEY', 'test-secret-never-persist')
    monkeypatch.delenv('JEV_MODEL', raising=False)
    monkeypatch.delenv('JEV_FOCUS', raising=False)


@pytest.fixture
def store(tmp_path):
    store = Store(tmp_path/'state.db')
    store.insert(Paper('Robotic experimental discovery', abstract='A robot optimizes chemistry.',
                       doi='10.1/one', date='2026-10-01'), 'pending')
    store.insert(Paper('A different scientific paper', doi='10.1/two', date='2026-10-02'), 'seeded')
    store.commit()
    yield store
    store.close()


def test_wire_request_and_typed_response(response, monkeypatch):
    calls = []
    def open_request(request, timeout):
        calls.append((request, timeout))
        return io.BytesIO(json.dumps(response).encode())
    monkeypatch.setattr(jev.urllib.request, 'build_opener', lambda *a: SimpleNamespace(open=open_request))
    paper = Paper('Title', abstract='Evidence', authors=['Private roster note'])
    result = jev.decide(jev.request_for(paper, jev.config()), 'test-secret')
    request, timeout = calls[0]
    assert request.full_url == 'https://api.typesafe.ai/v1/systemone'
    assert request.get_header('Authorization') == 'Bearer test-secret'
    payload = json.loads(request.data)
    assert payload['model'] == jev.MODEL
    assert set(payload['questions']) == {'priority', 'next_step'}
    assert 'Private roster' not in request.data.decode()
    assert timeout <= 8 and result['priority_score'] == 3.3
    assert result['next_step'] == 'fulltext_needed'


@pytest.mark.parametrize('mutation', ['model', 'missing', 'nan', 'sum', 'choice', 'score', 'legend', 'usage'])
def test_rejects_invalid_contract(response, mutation):
    if mutation == 'model':
        response['model'] = 'jev-latest'
    elif mutation == 'missing':
        del response['answers']['next_step']
    elif mutation == 'nan':
        response['answers']['priority']['score'] = float('nan')
    elif mutation == 'sum':
        response['answers']['priority']['probabilities']['0'] = 0.2
    elif mutation == 'choice':
        response['answers']['next_step']['choice'] = 'metadata_sufficient'
    elif mutation == 'score':
        response['answers']['priority']['score'] = 0
    elif mutation == 'legend':
        response['answers']['priority']['legend']['0'] = 'Changed meaning'
    else:
        response['usage']['input_tokens'] = True
    with pytest.raises(ValueError):
        jev.validate(response)


def test_sdk_optional_usage_is_not_fabricated(response):
    response['usage'] = {'input_tokens': None}
    assert jev.validate(response)['usage'] == {'input_tokens': None, 'output_tokens': None}


def test_redirects_do_not_forward_secret(monkeypatch):
    def opener(handler):
        assert handler().redirect_request(None, None, 302, '', {}, 'https://untrusted.example') is None
        raise urllib.error.HTTPError(jev.ENDPOINT, 302, 'redirect', {}, None)
    monkeypatch.setattr(jev.urllib.request, 'build_opener', opener)
    with pytest.raises(urllib.error.HTTPError):
        jev.decide({}, 'secret')


def test_missing_key_and_off_never_call_api(store, monkeypatch):
    monkeypatch.setattr(jev, 'decide', lambda *a, **k: pytest.fail('No API call allowed'))
    monkeypatch.delenv('TYPESAFE_API_KEY')
    assert jev.shadow(store)['status'] == 'needs_configuration'
    assert store.db.execute('SELECT count(*) FROM jev_decisions').fetchone()[0] == 0
    monkeypatch.setenv('JEV_MODE', 'off')
    assert jev.shadow(store)['status'] == 'off'


def test_cache_reuses_results_but_reconsiders_changed_metadata_and_focus(store, monkeypatch, response):
    calls = []
    monkeypatch.setattr(jev, 'decide', lambda *a, **k: calls.append(a) or jev.validate(response))
    before = store.db.execute('SELECT * FROM papers').fetchall()
    assert jev.shadow(store)['succeeded'] == 2
    assert jev.shadow(store)['attempted'] == 0
    assert store.db.execute('SELECT * FROM papers').fetchall() == before
    store.add_ids(2, Paper('A different scientific paper', doi='10.1/two', abstract='New detail'))
    store.commit()
    assert jev.shadow(store)['succeeded'] == 1
    monkeypatch.setenv('JEV_FOCUS', 'Electrochemistry')
    assert jev_report.report(store)['scored'] == 0
    assert jev.shadow(store)['succeeded'] == 2
    assert len(calls) == 5
    records = store.db.execute('SELECT payload,result FROM jev_decisions').fetchall()
    assert 'test-secret' not in json.dumps(records)


def test_failure_is_durable_redacted_and_not_retried_same_day(store, monkeypatch):
    calls = []
    def failure(*args, **kwargs):
        calls.append(1)
        raise urllib.error.HTTPError(jev.ENDPOINT, 429, 'secret-token body', {}, None)
    monkeypatch.setattr(jev, 'decide', failure)
    assert jev.shadow(store)['status'] == 'degraded'
    # Another paper may be tried, but the failed paper is not immediately retried.
    assert jev.shadow(store)['attempted'] == 1
    assert jev.shadow(store)['attempted'] == 0
    assert len(calls) == 2 and store.counts() == {'pending': 1, 'seeded': 1}
    result = store.db.execute('SELECT result FROM jev_decisions').fetchall()
    assert '429' in json.dumps(result) and 'secret-token' not in json.dumps(result)


def test_daily_call_cap_survives_multiple_runs(store, monkeypatch, response):
    for i in range(30):
        store.insert(Paper(f'Paper {i}', doi=f'10.2/{i}'), 'pending')
    store.commit()
    monkeypatch.setattr(jev, 'decide', lambda *a, **k: jev.validate(response))
    assert jev.shadow(store, limit=50)['attempted'] == 20
    assert jev.shadow(store, limit=50)['attempted'] == 0
    assert store.db.execute('SELECT count(*) FROM jev_decisions').fetchone()[0] == 20


def test_zero_time_budget_and_recent_interrupted_request(store, monkeypatch, response):
    monkeypatch.setattr(jev, 'decide', lambda *a, **k: jev.validate(response))
    assert jev.shadow(store, budget_seconds=0)['attempted'] == 0
    payload = jev.request_for(store.rows('SELECT id,data FROM papers WHERE id=1')[0][1], jev.config())
    store.db.execute('INSERT INTO jev_decisions VALUES (?,?,?,?,?,?)', (1, jev.fingerprint(payload), 'started', time.time(), json.dumps(payload), '{}'))
    store.commit()
    assert jev.shadow(store)['succeeded'] == 1
    assert store.db.execute('SELECT status FROM jev_decisions WHERE paper_id=1').fetchone()[0] == 'started'


def test_export_is_blind_keeps_unscored_and_preserves_human_labels(store, monkeypatch, response, tmp_path):
    monkeypatch.setattr(jev, 'decide', lambda *a, **k: jev.validate(response))
    jev.shadow(store, limit=1)
    data = jev_report.export(store, tmp_path/'outbox')
    assert data['papers'] == 2 and data['scored'] == 1 and data['unscored'] == 1
    path = tmp_path/'outbox/jev-labels.csv'
    with path.open() as f:
        labels = list(csv.DictReader(f))
    assert all(not r['priority'] and not r['next_step'] for r in labels)
    assert 'probabilities' not in path.read_text()
    path.write_text('HUMAN WORK')
    jev_report.export(store, tmp_path/'outbox')
    assert path.read_text() == 'HUMAN WORK'
    assert jev_report.csv_safe('=HYPERLINK("evil")').startswith("'=")


def test_evaluation_separates_empty_labels_and_rejects_stale_labels(store, monkeypatch, response):
    monkeypatch.setattr(jev, 'decide', lambda *a, **k: jev.validate(response))
    jev.shadow(store)
    data = jev_report.report(store)
    labels = [{'paper_id': str(i['paper_id']), 'input_hash': i['input_hash'], 'priority': '3', 'next_step': 'fulltext_needed'} for i in data['items']]
    metrics = jev_report.evaluate(data, labels)
    assert metrics['priority_mae'] == pytest.approx(0.3)
    assert metrics['next_step_multiclass_brier'] == pytest.approx(0.06)
    assert metrics['next_step_accuracy'] == 1
    assert metrics['missed_fulltext_rate'] == 0
    assert 'next_step_accuracy' not in jev_report.evaluate(data, [])
    with pytest.raises(ValueError, match='Duplicate'):
        jev_report.evaluate(data, labels+labels)
    labels[0]['input_hash'] = 'stale'
    with pytest.raises(ValueError, match='older input'):
        jev_report.evaluate(data, labels)


def test_ranking_metric_detects_improvement_and_fulltext_misses():
    items, labels = [], []
    for pid, priority, proposed in [('1', 0, 3), ('2', 2, 2), ('3', 4, 1)]:
        items.append({'paper_id': int(pid), 'input_hash': pid, 'baseline_rank': int(pid), 'suggested_rank': proposed,
                      'status': 'ok', 'decision': {'priority_score': priority, 'next_step': 'metadata_sufficient',
                      'next_step_probabilities': {'metadata_sufficient': 0.8, 'fulltext_needed': 0.1, 'manual_review': 0.1}, 'latency_ms': 10}})
        labels.append({'paper_id': pid, 'input_hash': pid, 'priority': str(priority), 'next_step': 'fulltext_needed'})
    metrics = jev_report.evaluate({'items': items, 'scored': 3}, labels)
    assert metrics['suggested_ndcg_at_10'] == 1
    assert metrics['baseline_ndcg_at_10'] < 1
    assert metrics['missed_fulltext_rate'] == 1
    assert metrics['estimated_successful_input_cost_usd'] is None


def test_dry_run_and_optional_failure_leave_delivery_correct(env, monkeypatch):
    from paper_monitor import jev_tasks
    monkeypatch.setattr(jev_tasks, 'evaluate', lambda *a, **k: {'status': 'error'})
    web, run, statuses, _, _, tmp = env
    calls = []
    def failed(*a, **kw):
        calls.append(1)
        raise TimeoutError('Do not expose secret-key')
    monkeypatch.setattr(jev, 'decide', failed)
    assert run('--dry-run') == 0 and not calls
    assert run() == 0  # Baseline still succeeds despite Jev failure.
    monkeypatch.setenv('SLACK_WEBHOOK_URL', 'https://hooks.slack.com/services/T/B/X')
    web.works['results'].append(new_work('New monitored paper', '10.1/new-jev'))
    assert run() == 0
    assert statuses()['new monitored paper'] == 'posted'
    assert len(web.slack_posts) == 1
    report = json.loads((tmp/'outbox/jev-shadow.json').read_text())
    assert report['scored'] == 0


def test_ssm_configuration_is_atomic(monkeypatch):
    monkeypatch.setenv('JEV_CONFIG_PARAMETER', '/test/jev')
    monkeypatch.delenv('TYPESAFE_API_KEY')
    raw = {'api_key': 'secret', 'model': jev.MODEL, 'focus': 10}
    monkeypatch.setattr(registry, 'client', lambda _: SimpleNamespace(get_parameter=lambda **k: {'Parameter': {'Value': json.dumps(raw)}}))
    with pytest.raises(ValueError):
        registry.configure_jev()
    assert not jev.config()['api_key']
    raw['focus'] = jev.DEFAULT_FOCUS
    registry.configure_jev()
    assert jev.config()['api_key'] == 'secret'


def load_setup():
    path = Path(__file__).parents[1]/'deploy/configure_jev.py'
    spec = importlib.util.spec_from_file_location('configure_jev', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_configuration_smoke_checks_before_encrypted_save(monkeypatch, response):
    setup = load_setup()
    writes, calls = [], []
    def download(bucket, key, target):
        with sqlite3.connect(target) as db:
            db.execute('CREATE TABLE papers(data TEXT)')
            db.execute('INSERT INTO papers VALUES (?)', (json.dumps({'title': 'Public real catalogue metadata', 'date': '2026-10-01'}),))
    def client(name):
        return SimpleNamespace(download_file=download, put_parameter=lambda **k: writes.append(k))
    session = SimpleNamespace(client=client)
    cfg = {'api_key': 'secret', 'focus': jev.DEFAULT_FOCUS, 'model': jev.MODEL}
    def fail(*a, **k):
        raise ValueError('bad contract')
    monkeypatch.setattr(jev, 'decide', fail)
    with pytest.raises(ValueError):
        setup.verify_and_save(session, cfg, '/test/jev', 'bucket', save=True)
    assert not writes
    monkeypatch.setattr(jev, 'decide', lambda *a, **k: calls.append(a) or jev.validate(response))
    result = setup.verify_and_save(session, cfg, '/test/jev', 'bucket', save=True)
    assert writes[0]['Type'] == 'SecureString'
    assert result['status'] == 'verified_and_saved' and 'secret' not in json.dumps(result)
    assert calls[0][0]['state']['title'] == 'Public real catalogue metadata'
    setup.verify_and_save(session, cfg, '/test/jev', 'bucket', save=False)
    assert len(writes) == 1
