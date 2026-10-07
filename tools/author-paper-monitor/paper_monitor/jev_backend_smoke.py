"""Read-only cloud canary against the actual backend image and PAS records."""
import json
import os


def main():
    from fastapi.testclient import TestClient
    from sqlalchemy import select
    from app.main import app
    from app.db import SessionLocal
    from app.models import Paper, PaperChunk
    from app.services.modular_rag_service import ModularRagRequest, routing_module
    client = TestClient(app)  # No lifespan context: do not run startup ingestion.
    headers = {'X-Jev-Key': os.environ['JEV_ADMIN_KEY']}
    assert client.get('/jev/status').status_code == 401
    status = client.get('/jev/status', headers=headers)
    assert status.status_code == 200, 'Status endpoint failed'
    data = status.json()
    assert len(data['tasks']) == 8 and data['mode'] == 'shadow'
    assert data['key_status'] == 'needs_configuration', 'This canary expects no paid model calls'
    with SessionLocal() as session:
        papers = session.scalars(select(Paper).where(Paper.provenance == 'author_monitor').order_by(Paper.id).limit(2)).all()
        assert len(papers) == 2
        ids = [p.id for p in papers]
        chunk = session.scalar(select(PaperChunk).order_by(PaperChunk.id).limit(1))
        assert chunk is not None
        chunk_id, source_paper, quote = chunk.id, chunk.paper_id, chunk.chunk_text[:500]
    results = {}
    for task in data['tasks']:
        body = {'task': task, 'paper_id': ids[0], 'other_paper_id': ids[1], 'context': {
            'query': 'How many papers are stored?', 'target': {'name': 'Alán Aspuru-Guzik', 'institution': 'University of Toronto'},
            'candidate': {'name': 'Alán Aspuru-Guzik', 'institution': 'University of Toronto'}}}
        if task in ('answer_evidence', 'graph_relation'):
            body.update(paper_id=source_paper, chunk_id=chunk_id)
            body['context'] = {'claim': quote, 'quote': quote, 'relation': 'mentions', 'object': quote[:100]}
        response = client.post('/jev/evaluate', headers=headers, json=body)
        assert response.status_code == 200, f'{task} failed with HTTP {response.status_code}'
        result = response.json()
        assert result['status'] in ('needs_configuration', 'protected_record'), f'{task} unexpectedly performed inference'
        assert result.get('reason') != 'boundaries_unavailable', 'Review boundary files must be packaged for release'
        results[task] = result['status']
    state = {'request': ModularRagRequest(query='How many papers?', mode='iterative'), 'trace': []}
    routing_module(state)
    assert any(t.get('module') == 'jev_route_shadow' for t in state['trace'])
    assert state['mode'] == 'iterative'
    print(json.dumps({'canary': 'passed', 'workflow_status': results, 'rag_hook': 'verified',
                      'source': 'actual PAS papers and indexed passage', 'paid_model_calls': 0}))


if __name__ == '__main__':
    main()
