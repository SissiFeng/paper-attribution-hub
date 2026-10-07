import json
from fastapi.testclient import TestClient
from app.models import Paper, PaperSection
from tests.test_private_reading import clients


def test_public_catalogue_never_serializes_personal_or_internal_fields(clients, session):
    from app.main import app
    member, _, _ = clients
    paper = session.get(Paper, 'P1')
    paper.doi = '10.1234/public'; paper.keywords = ['Catalysis']
    paper.raw_metadata = {'secret': 'internal-only'}
    paper.funding_text = 'internal-only'; paper.query_string = 'internal-only'
    session.add(PaperSection(id='private-fulltext', paper_id='P1', section_type='methods', content='licensed-fulltext', order_index=0))
    session.add(Paper(id='upload', title='Unpublished private draft', doi='10.1234/upload', provenance='manual_upload'))
    session.commit()
    member.put('/reading/saved/P1', json={'note': 'private-note'})
    anon = TestClient(app)
    response = anon.get('/catalog/papers/P1')
    assert response.status_code == 200
    assert set(response.json()) == {'id','title','abstract','doi','year','venue','authors','keywords','full_text_available'}
    assert response.json()['keywords'] == ['Catalysis']
    assert all(secret not in response.text for secret in ['private-note', 'internal-only', 'licensed-fulltext'])
    assert anon.get('/catalog/papers/upload').status_code == 404
    assert anon.get('/catalog/papers/P2').status_code == 404  # no published identifier or API provenance
    assert anon.get('/catalog/resolve', params={'doi':'HTTPS://DOI.ORG/10.1234/PUBLIC'}).json() == {'id':'P1'}
    listing = anon.get('/catalog/papers').json()
    assert [p['id'] for p in listing['items']] == ['P1']
    assert 'private-note' not in json.dumps(listing)
    for path in ['/reading/papers/P1', '/reading/papers/P1/markdown', '/research/projects', '/chat/sessions', '/papers', '/access/check-admin']:
        assert anon.get(path).status_code == 401
    assert member.get('/access/check-admin').status_code == 403


def test_monitor_records_without_doi_and_literal_search(clients, session):
    from app.main import app
    session.add(Paper(id='monitor_preprint', title='100% robotic screening', source='author_monitor', provenance='author_monitor'))
    session.commit()
    anon = TestClient(app)
    assert anon.get('/catalog/papers/monitor_preprint').status_code == 200
    assert [p['id'] for p in anon.get('/catalog/papers',params={'q':'%'}).json()['items']] == ['monitor_preprint']
    assert anon.get('/catalog/papers',params={'offset':-1}).status_code == 422
    assert anon.get('/catalog/resolve',params={'doi':'10.1234/missing'}).status_code == 404


def test_shared_original_paper_view_and_wiki_are_read_only_and_private_safe(clients, session):
    from app.main import app
    from app.models import HumanReview, PaperClassification, PaperProposition, WikiPage
    from sqlalchemy import select, func
    member, other, _ = clients
    row = session.get(Paper, 'P1')
    row.doi = '10.1234/wiki'; row.abstract = 'Published robotic synthesis result.'
    row.query_string = 'secret-query'; row.funding_text = 'secret-funding'
    session.add(PaperClassification(id='class-P1', paper_id='P1', label='CORE_RELEVANT', confidence=.9,
        reasons=['Published author match'], future_rule_update='secret-rule',
        graph_signals={'internal': 'secret-graph'}))
    session.add(HumanReview(id='review-P1', paper_id='P1', human_label='INCLUDE', reviewer='secret-reviewer', notes='secret-review'))
    session.add(PaperProposition(id='method', paper_id='P1', predicate='uses_method',
        object_value='Robotic synthesis', confidence=.8, claim_text='Published method.'))
    session.add(WikiPage(id='private-wiki', entity_type='synthesis', entity_id='private-chat',
        title='secret-chat', sections=[{'key':'identity','body':'secret-synthesis'}]))
    session.add(Paper(id='upload',title='secret-upload',doi='10.1234/upload',provenance='manual_upload'))
    session.commit()
    member.put('/reading/saved/P1', json={'note':'secret-personal'})
    before = session.scalar(select(func.count()).select_from(WikiPage))
    for client in (TestClient(app), member, other):
        listing = client.get('/catalog/paper-view')
        assert listing.status_code == 200, listing.text
        assert [p['id'] for p in listing.json()] == ['P1']
        response = client.get('/catalog/papers/P1/view')
        assert response.status_code == 200, response.text
        assert response.json()['classification']['label'] == 'CORE_RELEVANT'
        assert response.json()['review'] is None
        assert response.json()['classification']['graph_signals'] is None
        wiki = client.get('/catalog/papers/P1/wiki')
        assert wiki.status_code == 200, wiki.text
        assert 'Robotic synthesis' in wiki.text
        assert {'identity','abstract_summary','methods','classification'} <= {p['key'] for p in wiki.json()['sections']}
        assert all('secret-' not in r.text for r in (listing, response, wiki))
        assert client.get('/catalog/papers/upload/view').status_code == 404
        assert client.get('/catalog/papers/upload/wiki').status_code == 404
        assert client.get('/catalog/papers/missing/wiki').status_code == 404
    assert session.scalar(select(func.count()).select_from(WikiPage)) == before
    assert member.get('/wiki/syntheses').status_code == 403
    assert member.post('/wiki/paper/P1/compile').status_code == 403
    assert member.post('/reviews/P1',json={'human_label':'EXCLUDE'}).status_code == 403
    assert member.get('/papers/P1/graph-explanation').status_code == 403


def test_shared_list_filters_pagination_and_unclassified_monitor_records(clients, session):
    from app.main import app
    from app.models import PaperClassification
    row=session.get(Paper,'P1'); row.doi='10.1234/one';row.year=2024;row.abstract='A catalyst method.'
    session.add(PaperClassification(id='class-P1', paper_id='P1',label='CORE_RELEVANT',confidence=.9))
    session.add(Paper(id='monitor',title='New preprint',source='author_monitor',provenance='author_monitor',year=2026))
    session.commit()
    anon=TestClient(app)
    def ids(**params):
        r=anon.get('/catalog/paper-view',params=params);assert r.status_code==200,r.text
        return [p['id'] for p in r.json()]
    assert set(ids())=={'P1','monitor'}
    assert ids(search='catalyst')==['P1']
    assert ids(year_from=2025)==['monitor']
    assert ids(labels='CORE_RELEVANT')==['P1']
    assert ids(min_confidence=.8)==['P1']
    assert 'SDL assessment has not been recorded' in anon.get('/catalog/papers/monitor/wiki').text
    assert len(ids(limit=1))==1 and set(ids(limit=1)+ids(limit=1,offset=1))=={'P1','monitor'}
    for params in [{'limit':101},{'offset':-1},{'year_from':2026,'year_to':2024},{'labels':'SECRET'},{'min_confidence':.9,'max_confidence':.1}]:
        assert anon.get('/catalog/paper-view',params=params).status_code==422


def test_shared_wiki_supports_the_deployed_legacy_compiler(clients, session, monkeypatch):
    from app.main import app
    from app.services import wiki_compiler
    session.get(Paper, 'P1').doi='10.1234/legacy'; session.commit()
    monkeypatch.delattr(wiki_compiler, 'WIKI_COMPILER_VERSION')
    response=TestClient(app).get('/catalog/papers/P1/wiki')
    assert response.status_code==200, response.text
    assert response.json()['model_version']=='template-v0.1'
    assert 'identity' in {part['key'] for part in response.json()['sections']}
