from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api import jev
from app.db import get_session
from app.models import Paper, PaperChunk
from app.services import jev_advisory_service as service
from app.services.modular_rag_service import ModularRagRequest, routing_module


@pytest.fixture(autouse=True)
def no_paid_calls(monkeypatch, tmp_path):
    monkeypatch.setenv('JEV_MODE', 'shadow')
    monkeypatch.setenv('JEV_ADMIN_KEY', 'operator-test-key')
    monkeypatch.setenv('JEV_STATE_DB', str(tmp_path/'jev.db'))
    for key in ('TYPESAFE_API_KEY', 'JEV_CONFIG_PARAMETER', 'SLACK_TABLE'):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def client(session):
    app = FastAPI()
    app.include_router(jev.router)
    app.dependency_overrides[get_session] = lambda: session
    session.add_all([Paper(id='j1', title='Robot chemistry', abstract='We used a robot.', doi='10.1/a'),
                     Paper(id='j2', title='Different experiment', abstract='Manual chemistry.', doi='10.1/b')])
    session.flush()
    session.add_all([PaperChunk(id='jc1', paper_id='j1', section_type='methods', chunk_text='We used a robot for chemistry.'),
                     PaperChunk(id='jc2', paper_id='j2', section_type='methods', chunk_text='We did not use a robot.')])
    session.commit()
    with TestClient(app) as c:
        yield c


AUTH = {'X-Jev-Key': 'operator-test-key'}


def test_operator_api_is_not_public_and_lists_all_eight(client, monkeypatch):
    assert client.get('/jev/status').status_code == 401
    result = client.get('/jev/status', headers=AUTH).json()
    assert result['key_status'] == 'needs_configuration'
    assert len(result['tasks']) == 8 and result['automatic_actions'] is False
    monkeypatch.delenv('JEV_ADMIN_KEY')
    assert client.get('/jev/status', headers=AUTH).status_code == 503


@pytest.mark.parametrize('task', ['reading_priority', 'analysis_route', 'review_priority', 'version_relation', 'retrieval_route', 'author_identity'])
def test_operator_workflows_run_without_key_using_real_db_context(client, task):
    body = {'task': task, 'paper_id': 'j1', 'other_paper_id': 'j2',
            'context': {'query': 'How many papers?', 'target': {'name': 'A'}, 'candidate': {'name': 'A'}}}
    result = client.post('/jev/evaluate', headers=AUTH, json=body)
    assert result.status_code == 200, result.text
    assert result.json()['status'] == 'needs_configuration'
    assert 'decision' not in result.json()


@pytest.mark.parametrize('task', ['answer_evidence', 'graph_relation'])
def test_evidence_cannot_use_another_papers_chunk_or_fabricated_quote(client, task):
    body = {'task': task, 'paper_id': 'j1', 'chunk_id': 'jc2',
            'context': {'quote': 'We did not use a robot.', 'claim': 'Robot use', 'relation': 'uses', 'object': 'robot'}}
    assert client.post('/jev/evaluate', headers=AUTH, json=body).status_code == 422
    body['chunk_id'] = 'jc1'
    body['context']['source_text'] = 'Fake source pretending to be in the database'
    body['context']['quote'] = 'Fake source'
    assert client.post('/jev/evaluate', headers=AUTH, json=body).status_code == 422
    body['context']['quote'] = 'We used a robot for chemistry.'
    result = client.post('/jev/evaluate', headers=AUTH, json=body)
    assert result.status_code == 200 and result.json()['status'] == 'needs_configuration'


def test_route_shadow_does_not_change_existing_rag_path(monkeypatch):
    calls = []
    monkeypatch.setattr(service, 'advise', lambda *a: calls.append(a) or {'status': 'ok', 'decision': {'choice': 'graph_search'}})
    state = {'request': ModularRagRequest(query='How many papers?', mode='iterative'), 'trace': []}
    routing_module(state)
    assert state['mode'] == 'iterative'
    assert state['generated_queries'] == ['How many papers?']
    assert calls[0][0] == 'retrieval_route'
    assert state['trace'][-1]['module'] == 'jev_route_shadow'


def test_answer_checks_bind_citations_and_keep_answer(monkeypatch):
    calls = []
    monkeypatch.setattr(service, 'advise', lambda *a: calls.append(a) or {'status': 'ok', 'decision': {'choice': 'contradicted'}})
    state = {'answer': 'This study used a robot [1].\nUnsupported citation [99].',
             'sources': [{'text': 'We used a robot.', 'chunk_id': 'jc1', 'paper_id': 'j1'}], 'trace': []}
    original = state['answer']
    service.check_answer(state)
    assert state['answer'] == original
    assert calls[0][1]['source_id'] == 'jc1' and calls[0][1]['paper_id'] == 'j1'
    assert state['trace'][0]['checks'][1]['status'] == 'invalid_citation'
    assert state['trace'][0]['answer_changed'] is False


def test_review_advice_keeps_priorities_and_preserves_resolution(monkeypatch, session):
    contexts = []
    monkeypatch.setattr(service, 'advise', lambda task, ctx: contexts.append(ctx) or {'status': 'needs_configuration'})
    item = SimpleNamespace(paper_id='j1', title='Paper', abstract='Abstract', doi='doi', authors=['A'], reasons=['Conflict'],
                           review_status='COMPLETED', stage1_role=None, priority=0.3, jev_advice=None)
    service.review_advice([item], session)
    assert contexts[0]['human_resolved'] is True
    assert item.priority == 0.3 and item.review_status == 'COMPLETED'


def test_missing_label_manifest_protects_review_without_breaking_endpoint(client, session, monkeypatch):
    from app.services import staged_screening
    def missing(_session):
        raise FileNotFoundError('validation labels missing')
    monkeypatch.setattr(staged_screening, '_screening_boundaries', missing)
    response = client.post('/jev/evaluate', headers=AUTH, json={'task': 'review_priority', 'paper_id': 'j1'})
    assert response.status_code == 200
    assert response.json()['reason'] == 'boundaries_unavailable'
    item = SimpleNamespace(paper_id='j1', jev_advice=None)
    service.review_advice([item], session)
    assert item.jev_advice['status'] == 'protected_record'


def test_open_corpus_still_protects_stage1_assignments(client, session):
    paper = session.get(Paper, 'j1')
    paper.raw_metadata = {'sdl_stage1_split': {'role': 'frozen_test'}}
    session.commit()
    response = client.post('/jev/evaluate', headers=AUTH, json={'task': 'review_priority', 'paper_id': 'j1'})
    assert response.status_code == 200
    assert response.json()['status'] == 'protected_record'


def test_graph_advice_is_bound_to_source_and_never_rewrites_relationship(client, session, monkeypatch):
    contexts = []
    monkeypatch.setattr(service, 'advise', lambda task, ctx: contexts.append(ctx) or {'status': 'ok', 'decision': {'choice': 'mention_only'}})
    row = SimpleNamespace(entity_type='instrument', evidence_chunk_id='jc1', name='robot', normalized_name='robot', usage_snippet=None)
    paper = session.get(Paper, 'j1')
    service.graph_advice(session, paper, [row])
    assert contexts[0]['quote'] in contexts[0]['source_text']
    assert contexts[0]['source_id'] == 'jc1'
    assert paper.raw_metadata['jev_graph_advice'][0]['decision']['choice'] == 'mention_only'
    assert row.entity_type == 'instrument' and row.normalized_name == 'robot'
    row.evidence_chunk_id = 'jc2'
    service.graph_advice(session, paper, [row])
    assert paper.raw_metadata['jev_graph_advice'][0]['status'] == 'source_mismatch'
    assert len(contexts) == 1
